#!/usr/bin/env python3
"""Backfill duplicate fingerprints for images added before they existed.

`content_hash` is what the add path checks before an upload reaches ImgChest,
and what the duplicate review groups by. Rows created before either existed are
NULL, so the add-time gate cannot see them and the review has nothing to group.
This walks them and fills the field in.

It downloads each image from its stored URL — the only place those bytes still
exist — and hashes them exactly as an upload does: the file as stored, not the
raw upload. That is why the backfill can work at all; see `DECISIONS.md`,
"Uploading the same picture twice".

Expect it to be slow and to move real bandwidth: the library is thousands of
images. Safe to interrupt and re-run — it only looks at rows still NULL, and a
failure leaves the row NULL so the next run tries again.

    uv run python scripts/backfill_content_hashes.py --dry-run
    uv run python scripts/backfill_content_hashes.py
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import image_utils  # noqa: E402
import tempfiles  # noqa: E402
from remote_images import _fetch_image_from_url_for_import  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Hash at most N (0 = all)")
    parser.add_argument("--batch", type=int, default=200, help="Rows fetched per pass")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report the backlog without downloading"
    )
    args = parser.parse_args()

    print(f"database: {db.database_path()}")
    pending = db.images_missing_content_hash(limit=10**9)
    print(f"missing a fingerprint: {len(pending)}")
    if args.dry_run:
        return 0

    hashed = 0
    failed = 0
    cursor = 0
    while True:
        rows = db.images_missing_content_hash(limit=args.batch, after_id=cursor)
        if not rows:
            break
        for row in rows:
            cursor = row["id"]
            if args.limit and hashed >= args.limit:
                break
            temp_path = None
            try:
                temp_path, _ = _fetch_image_from_url_for_import(row["url"])
                digest = image_utils.content_hash(temp_path)
            except Exception as e:
                failed += 1
                print(f"  ! {row['character']} {row['url']}: {e}", file=sys.stderr)
                continue
            finally:
                tempfiles.discard(temp_path)
            if not digest or not db.set_content_hash(row["id"], digest):
                failed += 1
                continue
            hashed += 1
        print(f"hashed {hashed} (failed {failed})", flush=True)
        if args.limit and hashed >= args.limit:
            break

    print(f"\nfingerprinted {hashed}; failed {failed}")
    if failed:
        print("Failures are usually dead links; re-run to retry them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
