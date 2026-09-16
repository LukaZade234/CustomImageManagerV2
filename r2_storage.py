"""Writing single objects to the R2 asset bucket via `rclone`.

Two callers mirror derived images to the same bucket under different prefixes:
portrait mirroring (`portrait_mirror.py`, the Mudae portraits) and thumbnail
mirroring (`thumbnails.py`, the 600px gallery WebPs). The rclone invocation, the
object caching header and the "degrade rather than raise" contract live here so
the two cannot drift.

Objects are always served `immutable` for a year, so a value that can change must
be written under a key that changes with it -- the content-hash-in-the-key rule
in the callers. Overwriting a key would leave the edge serving the old bytes.
"""

from __future__ import annotations

import os
import shutil
import subprocess

IMMUTABLE = "public, max-age=31536000, immutable"


def remote_and_bucket() -> tuple[str, str]:
    return os.environ.get("RCLONE_REMOTE", "r2"), os.environ.get("R2_BUCKET", "imgmanager-assets")


def upload_object(
    data: bytes, key: str, *, remote: str | None = None, bucket: str | None = None
) -> bool:
    """Stream one object to `<remote>:<bucket>/<key>`. True on success.

    Uses `rclone rcat`, which reads the object from stdin, so no temporary file
    is needed. Returns False -- never raises -- if rclone or its config is missing
    or the upload fails, so a caller can fall back to serving from the origin.
    """
    default_remote, default_bucket = remote_and_bucket()
    remote = remote or default_remote
    bucket = bucket or default_bucket
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


def delete_object(key: str, *, remote: str | None = None, bucket: str | None = None) -> bool:
    """Remove one object from `<remote>:<bucket>/<key>`. True on success.

    Best effort for the same reason as the upload: a permanent delete must not
    fail because the CDN copy could not be reached, and a leftover object with no
    row pointing at it is inert.
    """
    default_remote, default_bucket = remote_and_bucket()
    remote = remote or default_remote
    bucket = bucket or default_bucket
    if not shutil.which("rclone"):
        return False
    try:
        subprocess.run(
            [
                "rclone",
                "deletefile",
                f"{remote}:{bucket}/{key}",
                "--s3-no-check-bucket",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        return False
