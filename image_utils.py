import os

from PIL import Image, ImageOps

import logs

# Pillow 9.1+ exposes LANCZOS on Image.Resampling (preferred for type checkers).
# Older Pillow used Image.LANCZOS.
try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    _RESAMPLE = Image.LANCZOS  # type: ignore[attr-defined]

# Max dimension (width or height) to reduce memory usage on small instances.
# Large images (e.g. 4000x4000) can use 64MB+ in RGBA; 2048 keeps it ~16MB.
MAX_DIMENSION = 2048
# Reject images larger than this (avoids loading huge images into memory at all).
# 4096x4096 RGBA ≈ 64MB; 7500x7500 ≈ 225MB causes OOM on 1GB instances.
MAX_DIMENSION_REJECT = 4096
# If file is under this size, skip the hard reject for dimensions above MAX_DIMENSION_REJECT.
# JPEGs under this size can still decode to huge PNGs — we always resize by MAX_DIMENSION below.
# Should match MAX_FILE_SIZE in upload_imgchest.py.
MAX_FILE_SIZE_SKIP_DIM_CHECK = 30 * 1024 * 1024  # 30MB
# Output must fit ImgChest upload limit (same as upload_imgchest.MAX_FILE_SIZE).
MAX_OUTPUT_BYTES = 30 * 1024 * 1024

# Uploads are stored as WebP, under a .png name.
#
# Mudae's $ai command will not accept a URL that does not end in .png, but it
# renders whatever bytes arrive — verified against a real card. So the extension
# is a compatibility requirement and the format underneath is ours to choose.
#
# WebP at 90 is both smaller and faster than the PNG this replaced: measured on a
# real upload, 121 KB against 958 KB, and 39ms to encode against 76ms. It is
# also what keeps images at full resolution — the shrink loop below exists
# because a PNG often would not fit ImgChest's limit, and at an eighth the size
# it now almost never runs.
WEBP_QUALITY = 90
UPLOAD_SUFFIX = ".png"

# Read from the file's own bytes rather than its name. Deciding by extension is
# how WebP files came to be stored under .png names without anyone noticing, and
# how an uploaded file could skip the checks below entirely.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
    (b"\xff\xd8\xff", "JPEG"),
)


def detect_format(file_path):
    """The real format of a file, from its magic bytes. None if unrecognised."""
    try:
        with open(file_path, "rb") as handle:
            head = handle.read(16)
    except OSError:
        return None
    for magic, name in _MAGIC:
        if head.startswith(magic):
            return name
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return None


def is_animated(file_path):
    """True for a GIF or WebP carrying more than one frame."""
    try:
        with Image.open(file_path) as img:
            return getattr(img, "n_frames", 1) > 1
    except Exception:
        return False


_logger = logs.get(__name__)


def _log(msg):
    """Prose, deliberately.

    These messages describe one step of a retry loop or a conversion, where the
    useful thing is the running commentary rather than a queryable event. They
    go through the logger so they carry a level and a timestamp and land in the
    same stream as everything else.
    """
    _logger.info(msg)


def validate_image_file(file_path):
    """Returns (True, None) if valid image, else (False, error_message)."""
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, None
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"


def _output_path_for(input_path):
    """A path distinct from the input.

    Writing the encoded image over the file Pillow is reading works only as long
    as every branch happens to have forced the pixels into memory first. That is
    an easy thing to break and a hard thing to notice, so the output always gets
    its own name and the caller cleans both up.
    """
    base, _ = os.path.splitext(input_path)
    return f"{base}.prepared{UPLOAD_SUFFIX}"


def prepare_for_upload(input_path):
    """Normalise an image for ImgChest. Returns (path, None) or (None, error).

    Output is WebP bytes with a .png name — see UPLOAD_SUFFIX above for why both
    halves of that are deliberate.

    Re-encoding is not only about size. It is also what caps the dimensions,
    applies EXIF rotation and, by rewriting the pixels, strips metadata: a photo
    straight off a phone carries GPS coordinates, and this library is public.
    Passing a file through untouched skips all of that, which is what the old
    `.png` fast path did — and why there are images in the library 11,036px
    across.
    """
    file_size = os.path.getsize(input_path)
    file_size_mb = file_size / (1024 * 1024)
    source_format = detect_format(input_path)
    _log(f"prepare start: {input_path} ({file_size_mb:.2f} MB, detected {source_format})")
    skip_dim_check = file_size <= MAX_FILE_SIZE_SKIP_DIM_CHECK

    try:
        with Image.open(input_path) as img:
            w, h = img.size
            _log(f"opened image: {w}x{h} px, format={img.format}")

            if not skip_dim_check and (w > MAX_DIMENSION_REJECT or h > MAX_DIMENSION_REJECT):
                _log(f"REJECT: dimensions {w}x{h} exceed max {MAX_DIMENSION_REJECT}px")
                return None, f"Image too large ({w}×{h}px, max {MAX_DIMENSION_REJECT}px)"

            # Already a still WebP within limits: re-encoding lossy to lossy
            # compounds artefacts for no gain, so pass it through. This is the
            # one case where skipping genuinely protects quality.
            if (
                source_format == "WEBP"
                and not is_animated(input_path)
                and w <= MAX_DIMENSION
                and h <= MAX_DIMENSION
                and file_size <= MAX_OUTPUT_BYTES
            ):
                _log("already a still WebP within limits, keeping as-is")
                output_path = _output_path_for(input_path)
                os.replace(input_path, output_path)
                return output_path, None

            img = ImageOps.exif_transpose(img)
            w, h = img.size

            if w > MAX_DIMENSION or h > MAX_DIMENSION:
                ratio = min(MAX_DIMENSION / w, MAX_DIMENSION / h)
                new_size = (int(w * ratio), int(h * ratio))
                _log(f"resizing {w}x{h} -> {new_size[0]}x{new_size[1]} (ratio={ratio:.3f})")
                img = img.resize(new_size, _RESAMPLE)

            # WebP has no palette mode, and alpha costs bytes for images that do
            # not use it.
            img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "PA") else "RGB")

            output_path = _output_path_for(input_path)
            _log(f"encoding WebP q{WEBP_QUALITY} to {output_path}")
            img.save(output_path, "WEBP", quality=WEBP_QUALITY, method=4)
            out_size = os.path.getsize(output_path)

            # Retained for the pathological case. At an eighth of PNG's size this
            # should now be unreachable in practice.
            quality = WEBP_QUALITY
            guard = 0
            while out_size > MAX_OUTPUT_BYTES and guard < 8:
                guard += 1
                quality = max(60, quality - 10)
                w0, h0 = img.size
                img = img.resize((max(32, int(w0 * 0.85)), max(32, int(h0 * 0.85))), _RESAMPLE)
                _log(f"{out_size / (1024 * 1024):.2f} MB over limit, retrying at q{quality}")
                img.save(output_path, "WEBP", quality=quality, method=4)
                out_size = os.path.getsize(output_path)

            if out_size > MAX_OUTPUT_BYTES:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                return None, (
                    f"Still {out_size / (1024 * 1024):.2f} MB after scaling; ImgChest allows at "
                    f"most {MAX_OUTPUT_BYTES // (1024 * 1024)} MB."
                )

            _log(f"prepare done: {output_path} ({out_size / 1024:.0f} KB)")
            return output_path, None

    except Exception as e:
        _log(f"prepare FAILED: {input_path}: {type(e).__name__}: {e}")
        return None, f"Could not process image: {e}"


def read_image_dimensions(path):
    """(width, height) for an image on disk, or None if it cannot be read.

    Opening with Pillow only parses the header, so this costs a few hundred
    bytes of I/O rather than decoding the whole image. Never raises: a missing
    size is a degraded gallery, not a failed upload.
    """
    try:
        with Image.open(path) as img:
            width, height = img.size
        if width > 0 and height > 0:
            return width, height
    except Exception as e:
        _log(f"read_image_dimensions failed for {path}: {type(e).__name__}: {e}")
    return None
