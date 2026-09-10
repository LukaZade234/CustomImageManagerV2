#!/usr/bin/env python3
"""Measure the images migrated from v1, which have no stored dimensions.

The gallery lays images out in justified rows and needs each image's shape before
it can size a row. Without dimensions the browser has to download an image to
find out, so every arrival reflows the row it lands in — a visible cascade of
warping on a character with hundreds of images.

Only the header is fetched, not the image. Pillow can report a size from the
first few kilobytes of a PNG, JPEG or GIF, so this costs a fraction of the
~1.9 MB an image actually weighs. A ranged request is tried first; hosts that
ignore Range simply stream until enough has arrived and the connection is
dropped.

Safe to interrupt and re-run: it only ever looks at rows still missing a size,
and it never modifies the image itself.

    uv run python scripts/backfill_image_dimensions.py --dry-run
    uv run python scripts/backfill_image_dimensions.py
    uv run python scripts/backfill_image_dimensions.py --workers 16
"""

import argparse
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402

# Enough for a PNG/JPEG/GIF header in every case observed; a handful of
# progressive JPEGs need the second attempt.
FIRST_CHUNK = 32 * 1024
SECOND_CHUNK = 256 * 1024
TIMEOUT = 20
USER_AGENT = "imgmanager-backfill/1.0"


def _measure(url: str, byte_count: int) -> tuple[int, int] | None:
    headers = {"User-Agent": USER_AGENT, "Range": f"bytes=0-{byte_count - 1}"}
    with requests.get(url, headers=headers, timeout=TIMEOUT, stream=True) as response:
        if response.status_code not in (200, 206):
            return None
        buffer = io.BytesIO()
        for chunk in response.iter_content(8192):
            buffer.write(chunk)
            if buffer.tell() >= byte_count:
                break
    buffer.seek(0)
    try:
        with Image.open(buffer) as img:
            width, height = img.size
    except Exception:
        return None
    return (width, height) if width > 0 and height > 0 else None


def measure(url: str) -> tuple[int, int] | None:
    """Dimensions from the image header, or None if it cannot be determined."""
    for byte_count in (FIRST_CHUNK, SECOND_CHUNK):
        try:
            size = _measure(url, byte_count)
        except requests.RequestException:
            return None
        if size:
            return size
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8, help="Concurrent fetches (default 8)")
    parser.add_argument("--batch", type=int, default=500, help="Rows per pass (default 500)")
    parser.add_argument("--dry-run", action="store_true", help="Measure but do not write")
    args = parser.parse_args()

    print(f"database: {db.database_path()}")
    measured = failed = 0

    while True:
        rows = db.images_missing_dimensions(limit=args.batch)
        if not rows:
            break

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            sizes = list(pool.map(lambda row: measure(row["url"]), rows))

        found = {}
        for row, size in zip(rows, sizes, strict=True):
            if size:
                found[row["id"]] = size
            else:
                failed += 1
                print(f"  could not measure: {row['url'][:100]}")

        measured += len(found)
        if args.dry_run:
            print(f"[dry run] would record {len(found)} of {len(rows)}")
            break

        db.set_image_dimensions(found)
        print(f"recorded {len(found)} of {len(rows)}  (total {measured}, unreadable {failed})")

        if not found:
            # Every row in this batch failed; another pass would fetch the same
            # rows forever, since nothing was written.
            print("no progress in this batch, stopping")
            break

    print(f"\ndone. measured {measured}, unreadable {failed}")
    if failed:
        print("Unreadable rows keep NULL dimensions; the gallery measures those in the browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
