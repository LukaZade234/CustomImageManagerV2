"""WebP thumbnails for the gallery.

The images themselves must stay on ImgChest as PNGs — Mudae's `$ai` command
accepts nothing else, and that is the entire point of the app. But nothing
requires the *browser* to download those PNGs to draw a 220px-tall row, and it
was: `convert_to_png()` makes every upload a lossless RGBA PNG averaging 1.9 MB,
so a character with 256 images was a 488 MB page.

A 600px WebP of the same image is about 53 KB. The ImgChest URL stays canonical
in the database and is what every command, download and lightbox uses; only the
gallery grid renders these.

Generated on demand rather than in a batch. Backfilling would mean pulling ~16 GB
out of ImgChest in one go for images nobody may look at, whereas on demand each
one is fetched once, ever, and Cloudflare caches the result at the edge from then
on. Lazy loading in the gallery paces the requests naturally.

Each one is also uploaded to R2 as it is generated, and the key is recorded on the
row, so the grid can load from the CDN instead of through the origin and the
mirror is a backup of data that was previously origin-only. `scripts/backfill_thumbnails_to_r2.py`
does the same for the thumbnails already on disk.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image

import r2_storage

# Enough for a 220px row on a 2x display with room to spare, and the point at
# which the size curve flattens: 400px saves 20 KB and looks soft, 800px costs
# 24 KB more for detail nothing displays.
MAX_EDGE = 600
QUALITY = 82

# Objects live under the same custom domain as the character images, in their own
# prefix. The API stores this whole key ("thumbs/<file>"), so the client only has
# to prefix the image base.
PREFIX = "thumbs"

# Animated GIFs are excluded. Pillow can write animated WebP but slowly and with
# visible loss, and an animation is usually the reason the image was chosen.
SKIP_SUFFIXES = (".gif",)


def cache_dir() -> Path:
    return Path(os.environ.get("THUMB_DIR", "data/thumbs"))


def cache_path(image_id: int) -> Path:
    return cache_dir() / f"{image_id}.webp"


def is_thumbnailable(url: str) -> bool:
    return not (url or "").lower().split("?")[0].endswith(SKIP_SUFFIXES)


def thumb_url(image_id: int, source_url: str, thumb_key: str | None = None) -> str | None:
    """Where the gallery should look, or None if this image has no thumbnail.

    Two forms, deliberately. A mirrored thumbnail is the R2 key ("thumbs/…", no
    leading slash) and the client loads it from the image base; an unmirrored one
    is the API path ("/thumbs/…") that renders, mirrors and serves on the way
    through. The leading slash is what tells the two apart.

    Keyed by row id rather than a hash of the URL, which means the endpoint can
    only ever be asked for images already in the database — there is no way to
    hand it an arbitrary URL to fetch.
    """
    if not is_thumbnailable(source_url):
        return None
    return thumb_key or f"/thumbs/{image_id}.webp"


def object_key(image_id: int, data: bytes) -> str:
    """The R2 key for a thumbnail, with a short content hash.

    The hash is what makes a changed thumbnail a new object: the URL is served
    `immutable`, so overwriting the same key would leave the edge serving the old
    bytes for a year.
    """
    digest = hashlib.sha1(data).hexdigest()[:8]
    return f"{PREFIX}/{image_id}-{digest}.webp"


def mirror(image_id: int, data: bytes) -> str | None:
    """Upload a rendered thumbnail to R2. Returns its key, or None if it did not.

    Best effort, exactly like the portraits: rclone or its config may be absent
    in a dev checkout, in which case the local cache still serves every request
    and the backfill fills the mirror in later.
    """
    key = object_key(image_id, data)
    return key if r2_storage.upload_object(data, key) else None


def delete_mirror(key: str) -> bool:
    """Remove a mirrored thumbnail, for when its row is permanently deleted."""
    return r2_storage.delete_object(key)


def render(raw: bytes) -> bytes:
    """Encode a WebP thumbnail from original image bytes. Raises on bad input."""
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        # WebP has no palette mode and RGBA costs size for images that do not
        # use it; anything with real transparency keeps it.
        target = "RGBA" if img.mode in ("RGBA", "LA", "PA") else "RGB"
        thumbnail = img.convert(target)
        thumbnail.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        out = io.BytesIO()
        thumbnail.save(out, "WEBP", quality=QUALITY, method=5)
        return out.getvalue()


def store(image_id: int, data: bytes) -> Path:
    """Write a thumbnail into the cache atomically.

    Two requests for the same missing thumbnail can race. Writing to a temporary
    file and renaming means the loser wastes an encode rather than serving a
    half-written file.
    """
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = cache_path(image_id)
    fd, temp_name = tempfile.mkstemp(dir=directory, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path
