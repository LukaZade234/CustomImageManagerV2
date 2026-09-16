#!/usr/bin/env python3
"""Mirror the thumbnails already on disk to R2.

Thumbnails are generated on demand and mirrored as they are generated
(`routes/media.py`), so this only sweeps up what was written before that existed:
the WebP files under `THUMB_DIR` whose row has no key yet. Rows with no local
thumbnail are left alone -- they have never been viewed, and the serve endpoint
mirrors them on the first request.

Safe to interrupt and re-run: it only looks at rows still missing a key, and a
failure leaves the row NULL so the next run tries again.

    uv run python scripts/backfill_thumbnails_to_r2.py --dry-run
    R2_BUCKET=imgmanager-assets uv run python scripts/backfill_thumbnails_to_r2.py
"""

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import thumbnails  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Mirror at most N (0 = all)")
    parser.add_argument(
        "--batch", type=int, default=1000, help="Rows examined per pass (default 1000)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without uploading")
    args = parser.parse_args()

    if not args.dry_run and not shutil.which("rclone"):
        print("error: rclone not found on PATH", file=sys.stderr)
        return 1

    directory = thumbnails.cache_dir()
    print(f"database: {db.database_path()}")
    print(f"thumbnails: {directory}")
    if not directory.is_dir():
        print(f"nothing to do: {directory} does not exist")
        return 0

    mirrored = 0
    missing = 0
    seen: set[int] = set()
    while True:
        rows = db.images_missing_thumb_key(limit=args.batch, exclude_ids=seen)
        if not rows:
            break
        for row in rows:
            seen.add(row["id"])
            path = thumbnails.cache_path(row["id"])
            if not path.is_file():
                missing += 1
                continue

            data = path.read_bytes()
            key = (
                thumbnails.object_key(row["id"], data)
                if args.dry_run
                else thumbnails.mirror(row["id"], data)
            )
            if key:
                if not args.dry_run:
                    db.set_thumb_key(row["id"], key)
                mirrored += 1
            if args.limit and mirrored >= args.limit:
                break

        print(f"mirrored {mirrored} (no local file: {missing})", flush=True)
        if args.dry_run or (args.limit and mirrored >= args.limit):
            break

    verb = "would mirror" if args.dry_run else "mirrored"
    print(f"\n{verb} {mirrored}; no local thumbnail for {missing}")
    if missing:
        print("Those are mirrored on first view; nothing to do here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
