"""Scratch files for uploads in flight.

Every upload lands on disk before it is validated, converted and sent to
ImgChest. Those files used to be written next to the code, as
`./temp_custom_<name>`, which works from a checkout and fails on the server:
the unit sets `ProtectSystem=strict` with `ReadWritePaths=/var/lib/imgmanager`,
so `/opt/imgmanager` -- the working directory -- is read-only, and every upload
died with `[Errno 30] Read-only file system`.

The temp directory is the right place for this regardless of hardening. The unit
also sets `PrivateTmp=true`, so the service gets its own `/tmp` that no other
process on the box can see and that is emptied when the service stops.

Using `mkstemp` also fixes a collision the old scheme had: the filename came
from the uploaded file, so two people adding `image.png` at the same moment
wrote to the same path and one of them got the other's picture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def upload_dir() -> str:
    """Where in-flight uploads are written.

    `UPLOAD_TMP_DIR` overrides it, for a deployment that would rather put the
    churn on a specific volume than in /tmp.
    """
    configured = os.environ.get("UPLOAD_TMP_DIR", "").strip()
    if configured:
        Path(configured).mkdir(parents=True, exist_ok=True)
        return configured
    return tempfile.gettempdir()


def reserve(prefix: str, original_filename: str = "") -> str:
    """Create an empty file and return its path. The caller owns deleting it.

    The path is unique even when two uploads share a filename. The original
    extension is preserved because the conversion step names its output from it.
    """
    suffix = Path(original_filename or "").suffix[:16]
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=suffix, dir=upload_dir())
    os.close(fd)
    return path


def discard(path: str | None) -> None:
    """Delete a scratch file, ignoring the case where it is already gone."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass
