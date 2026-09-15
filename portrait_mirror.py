"""Shared portrait mirroring: encode a Mudae portrait as WebP and put it on R2.

Used both by the batch CLI (`scripts/mirror_portraits_to_r2.py`, which stages a
directory and `rclone copy`s it) and, for a single freshly fetched portrait, by
the "update main from Mudae" web flow (which `rclone rcat`s one object). The
object-key rule and the WebP encoding live here so the two can never drift.

R2 is written with `rclone`, the tool already configured for the bucket. The web
flow degrades gracefully when rclone or its config is not present in the runtime
(`upload_object` returns False): the caller then leaves the row needing a mirror
and the next batch run fills it, rather than the request failing.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

import thumbnails

# Objects live under the same custom domain as the character images, in their own
# prefix. The database stores this whole key ("portraits/<file>"), so the frontend
# only has to prefix the image base.
PREFIX = "portraits"

IMMUTABLE = "public, max-age=31536000, immutable"


def remote_and_bucket() -> tuple[str, str]:
    return os.environ.get("RCLONE_REMOTE", "r2"), os.environ.get("R2_BUCKET", "imgmanager-assets")


def object_key(image_id: int, data: bytes) -> str:
    """The R2 key for a portrait, with a short content hash.

    The hash is what makes a changed portrait a new object: the URL is served
    `immutable`, so overwriting the same key would leave the edge serving the old
    bytes for a year.
    """
    digest = hashlib.sha1(data).hexdigest()[:8]
    return f"{PREFIX}/{image_id}-{digest}.webp"


def render(raw: bytes) -> bytes | None:
    """WebP bytes for a fetched portrait, or None if it cannot be decoded."""
    try:
        return thumbnails.render(raw)
    except Exception:
        return None


def upload_object(
    data: bytes, key: str, *, remote: str | None = None, bucket: str | None = None
) -> bool:
    """Stream one object to `<remote>:<bucket>/<key>`. True on success.

    Uses `rclone rcat`, which reads the object from stdin, so no temporary file
    is needed. Returns False -- never raises -- if rclone or its config is missing
    or the upload fails, so a caller can fall back to deferring the mirror.
    """
    remote, bucket = remote or remote_and_bucket()[0], bucket or remote_and_bucket()[1]
    if not shutil.which("rclone"):
        return False
    try:
        subprocess.run(
            [
                "rclone",
                "rcat",
                f"{remote}:{bucket}/{key}",
                "--s3-no-check-bucket",
                "--header-upload",
                f"Cache-Control: {IMMUTABLE}",
            ],
            input=data,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        return False


def mirror(
    image_id: int, raw: bytes, *, remote: str | None = None, bucket: str | None = None
) -> str | None:
    """Encode `raw` and, if rclone is wired up, upload it. Returns the key or None."""
    webp = render(raw)
    if not webp:
        return None
    key = object_key(image_id, webp)
    return key if upload_object(webp, key, remote=remote, bucket=bucket) else None
