from PIL import Image, ImageOps
import os

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

def _log(msg):
    print(f"[IMG] {msg}", flush=True)


def validate_image_file(file_path):
    """Returns (True, None) if valid image, else (False, error_message)."""
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, None
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"

def convert_to_png(input_path):
    """
    Converts an image at input_path to PNG format.
    Resizes large images to reduce memory usage and avoid OOM on constrained instances.
    Returns (path, None) on success, or (None, error_message) on failure.
    """
    file_size = os.path.getsize(input_path)
    file_size_mb = file_size / (1024 * 1024)
    _log(f"convert_to_png start: {input_path} ({file_size_mb:.2f} MB)")
    skip_dim_check = file_size <= MAX_FILE_SIZE_SKIP_DIM_CHECK

    try:
        # Open the image (does not load full pixel data yet)
        with Image.open(input_path) as img:
            w, h = img.size
            _log(f"opened image: {w}x{h} px, format={img.format}")

            if not skip_dim_check:
                if w > MAX_DIMENSION_REJECT or h > MAX_DIMENSION_REJECT:
                    _log(f"REJECT: dimensions {w}x{h} exceed max {MAX_DIMENSION_REJECT}px")
                    return None, f"Image too large ({w}×{h}px, max {MAX_DIMENSION_REJECT}px)"

            # Apply EXIF rotation if present (fixes orientation issues)
            img = ImageOps.exif_transpose(img)
            w, h = img.size
            _log(f"after exif_transpose: {w}x{h} px")

            # Always cap longest edge — small JPEGs can decode to very tall/wide bitmaps whose
            # uncompressed PNG exceeds ImgChest's 30MB limit (e.g. 2700×5400 → 30.76 MB PNG).
            if w > MAX_DIMENSION or h > MAX_DIMENSION:
                ratio = min(MAX_DIMENSION / w, MAX_DIMENSION / h)
                new_size = (int(w * ratio), int(h * ratio))
                _log(f"resizing {w}x{h} -> {new_size[0]}x{new_size[1]} (ratio={ratio:.3f})")
                img = img.resize(new_size, _RESAMPLE)
                w, h = img.size

            # Convert to RGBA to handle transparency and ensure compatibility
            _log("converting to RGBA")
            img = img.convert('RGBA')

            # Create new filename
            base, _ = os.path.splitext(input_path)
            output_path = base + ".png"

            # Save as PNG; if still over host limit, scale down until it fits (rare: complex art)
            _log(f"saving to {output_path}")
            img.save(output_path, 'PNG')
            out_size = os.path.getsize(output_path)
            guard = 0
            while out_size > MAX_OUTPUT_BYTES and guard < 14:
                guard += 1
                w0, h0 = img.size
                factor = (MAX_OUTPUT_BYTES / out_size) ** 0.5 * 0.92
                new_w = max(32, int(w0 * factor))
                new_h = max(32, int(h0 * factor))
                if new_w >= w0 and new_h >= h0:
                    new_w, new_h = max(32, int(w0 * 0.88)), max(32, int(h0 * 0.88))
                _log(
                    f"PNG {out_size / (1024 * 1024):.2f} MB exceeds {MAX_OUTPUT_BYTES // (1024 * 1024)} MB limit, "
                    f"scaling {w0}x{h0} -> {new_w}x{new_h}"
                )
                img = img.resize((new_w, new_h), _RESAMPLE)
                img.save(output_path, 'PNG')
                out_size = os.path.getsize(output_path)

            out_size_mb = out_size / (1024 * 1024)
            if out_size > MAX_OUTPUT_BYTES:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                return (
                    None,
                    f"PNG is still {out_size_mb:.2f} MB after scaling; ImgChest allows at most "
                    f"{MAX_OUTPUT_BYTES // (1024 * 1024)} MB — simplify or export a smaller image.",
                )

            _log(f"convert_to_png done: {output_path} ({out_size_mb:.2f} MB)")
            return output_path, None

    except Exception as e:
        _log(f"convert_to_png FAILED: {input_path}: {type(e).__name__}: {e}")
        return None, f"Conversion failed: {str(e)}"
