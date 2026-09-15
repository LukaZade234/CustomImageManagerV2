#!/usr/bin/env python3
"""Mirror the Mudae catalog portraits to R2 as WebP.

Every catalog portrait is a hotlink to `mudae.net`. Portraits are display-only
-- never part of a `$ai` command -- so serving them from our own CDN removes a
dependency on someone else's host, puts them behind a cache we control, and
shrinks them (WebP is a fraction of the source PNG). The working rows that share
a catalog portrait pick up the mirror automatically.

The object key includes a hash of the encoded bytes, so a portrait that changes
is a new object rather than an overwrite of one Cloudflare has cached
`immutable`: the row is repointed, and the old object simply stops being
referenced.

Upload is one `rclone copy` per batch, the same tool the committed character
images use. A batch is fetched, uploaded and recorded before the next starts, so
an interrupted run resumes where it stopped (the next run only asks for rows that
still have no key) and a failure never leaves rows pointing at objects that are
not there.

    # What would be mirrored, without fetching anything.
    uv run python scripts/mirror_portraits_to_r2.py --dry-run

    # Fetch and encode into a directory, but stop before uploading.
    uv run python scripts/mirror_portraits_to_r2.py --no-upload --out /tmp/portraits

    # The whole thing: fetch, encode, upload, record. Needs rclone configured.
    R2_BUCKET=imgmanager-assets uv run python scripts/mirror_portraits_to_r2.py
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import portrait_mirror  # noqa: E402
from accent_extract import fetch_portrait_bytes  # noqa: E402

# The object-key rule and WebP encoding are shared with the "update main from
# Mudae" web flow, so the two can never drift.
PREFIX = portrait_mirror.PREFIX
object_key = portrait_mirror.object_key
render_portrait = portrait_mirror.render

# How many portraits to fetch, upload and record before moving on. Small enough
# that an interrupted run keeps most of its work, large enough that the upload
# listing overhead is negligible.
DEFAULT_BATCH = 500


def mirror_row(row: dict, staging: Path) -> tuple[str, str] | None:
    """Fetch and encode one row into `staging`. Returns (name_key, key) or None."""
    raw = fetch_portrait_bytes(row["mudae_image_url"])
    if not raw:
        return None
    webp = render_portrait(raw)
    if not webp:
        return None
    key = object_key(row["id"], webp)
    try:
        (staging / Path(key).name).write_bytes(webp)
    except OSError:
        return None
    return row["name_key"], key


def mirror_batch(rows: list[dict], staging: Path, workers: int) -> tuple[list, int]:
    """Fetch and encode `rows` into `staging`, reporting progress as it goes.

    Returns (results, failures). A failure is a row that could not be fetched or
    encoded; it is left unmirrored so the next run retries it.
    """
    results: list[tuple[str, str]] = []
    failures = 0
    total = len(rows)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(mirror_row, row, staging) for row in rows]
        for future in as_completed(futures):
            done += 1
            outcome = future.result()
            if outcome is None:
                failures += 1
            else:
                results.append(outcome)
            if done % 25 == 0 or done == total:
                print(f"  fetched {done}/{total} (failed {failures})", flush=True)
    return results, failures


def upload(staging: Path, remote: str, bucket: str, prefix: str) -> None:
    """Send the staging directory to `<remote>:<bucket>/<prefix>`."""
    subprocess.run(
        [
            "rclone",
            "copy",
            str(staging),
            f"{remote}:{bucket}/{prefix}",
            "--transfers",
            "16",
            "--checkers",
            "32",
            "--s3-no-check-bucket",
            "--progress",
            "--header-upload",
            "Cache-Control: public, max-age=31536000, immutable",
        ],
        check=True,
    )


def clear_dir(path: Path) -> None:
    for name in os.listdir(path):
        target = path / name
        if target.is_file():
            target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Mirror at most N portraits (0 = all)")
    parser.add_argument(
        "--redo", action="store_true", help="Re-mirror portraits that already have a key"
    )
    parser.add_argument("--out", type=Path, default=None, help="Staging dir (default: a temp dir)")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Fetch and encode into --out, then print the rclone command instead of running it",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would be mirrored, fetching nothing"
    )
    parser.add_argument(
        "--resync-thumbs",
        action="store_true",
        help="Skip fetching/uploading; just repoint working rows at the catalog mirrors that already exist",
    )
    parser.add_argument("--workers", type=int, default=8, help="Concurrent portrait fetches")
    parser.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_BATCH,
        help=f"Portraits per fetch/upload/record cycle (default {DEFAULT_BATCH}; 0 = all at once)",
    )
    parser.add_argument("--bucket", default=None, help="R2 bucket (default $R2_BUCKET)")
    parser.add_argument(
        "--remote", default=None, help="rclone remote (default $RCLONE_REMOTE or r2)"
    )
    args = parser.parse_args()

    bucket = args.bucket or os.environ.get("R2_BUCKET", "imgmanager-assets")
    remote = args.remote or os.environ.get("RCLONE_REMOTE", "r2")

    if args.resync_thumbs:
        updated = db.sync_character_thumbs_from_catalog()
        print(f"database: {db.database_path()}")
        print(f"working rows repointed at their catalog mirror: {updated}")
        return 0

    rows = db.catalog_portraits_to_mirror(limit=args.limit, redo=args.redo)
    print(f"database: {db.database_path()}")
    print(f"portraits to mirror: {len(rows)}")
    if not rows:
        synced = db.sync_character_thumbs_from_catalog()
        print(f"nothing to mirror; working rows repointed: {synced}")
        return 0

    if args.dry_run:
        for row in rows[:20]:
            print(f"  {row['name']}: {row['mudae_image_url']}")
        if len(rows) > 20:
            print(f"  … and {len(rows) - 20} more")
        return 0

    own_staging = args.out is None
    staging = args.out or Path(tempfile.mkdtemp(prefix="portraits-"))
    staging.mkdir(parents=True, exist_ok=True)
    print(f"staging: {staging}")

    if args.no_upload:
        results, failures = mirror_batch(rows, staging, args.workers)
        print(f"encoded {len(results)}, failed {failures}")
        print("not uploading; run this to send the objects:")
        print(
            f"  rclone copy {staging} {remote}:{bucket}/{PREFIX}"
            " --transfers 16 --checkers 32 --s3-no-check-bucket --progress"
            ' --header-upload "Cache-Control: public, max-age=31536000, immutable"'
        )
        return 0

    if not shutil.which("rclone"):
        print("error: rclone not found on PATH", file=sys.stderr)
        return 1

    size = args.batch if args.batch > 0 else len(rows)
    recorded = 0
    total = len(rows)
    for start in range(0, total, size):
        chunk = rows[start : start + size]
        print(f"batch {start // size + 1}: {len(chunk)} portraits", flush=True)
        results, failures = mirror_batch(chunk, staging, args.workers)
        if not results:
            print("  nothing encoded; skipping upload", flush=True)
            continue
        try:
            upload(staging, remote, bucket, PREFIX)
        except subprocess.CalledProcessError as exc:
            print(f"error: rclone upload failed (exit {exc.returncode})", file=sys.stderr)
            return 1
        recorded += db.record_catalog_portrait_mirrors(results)
        print(f"  uploaded and recorded {len(results)} (failed {failures})", flush=True)
        clear_dir(staging)

    print(f"recorded {recorded} mirrored portraits")
    synced = db.sync_character_thumbs_from_catalog()
    print(f"working rows repointed at their catalog mirror: {synced}")
    if own_staging:
        shutil.rmtree(staging, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
