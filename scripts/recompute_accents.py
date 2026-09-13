"""Backfill the per-character accent seeds.

The accent is recomputed on demand whenever a gallery changes (see
accent_extract.ensure_accent), but the library existed long before the column
did, and waiting for every character to be visited again would leave most of
it on the system accent for months. This walks the whole library once.

Thumbnails that are not on disk are left alone rather than fetched: pulling
every gallery original out of ImgChest in one pass is exactly the ~16 GB batch
download thumbnails.py was designed to avoid. Characters whose thumbnails have
not been rendered yet are stored with accent_partial set, and the listing
endpoint upgrades them the first time somebody actually opens the page and the
gallery renders its images.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import accent_extract
import db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="character name to recompute instead of the whole library",
    )
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help="skip characters whose stored fingerprint already matches",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="parallel recompute workers; the cost is remote portrait fetches,"
        " which overlap well, and database connections are per-thread",
    )
    args = parser.parse_args()

    conn = db.get_connection()
    if args.only:
        names = list(args.only)
    else:
        names = [r["name"] for r in conn.execute("SELECT name FROM characters ORDER BY id")]

    def work(name):
        if args.stale_only:
            state = accent_extract.accent_state(name)
            if state and state["accent_updated_at"]:
                count, latest, _ = accent_extract.gallery_fingerprint(name)
                portrait = db.get_character_portrait(name)
                portrait_url = portrait[1] if portrait else None
                if (
                    state["accent_gallery_count"] == count
                    and state["accent_gallery_latest"] == latest
                    and (state["accent_portrait_url"] or None) == (portrait_url or None)
                    and not state["accent_partial"]
                ):
                    return False
        return accent_extract.recompute_accent(name) is not None

    started = time.monotonic()
    done = 0
    seeded = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, name): name for name in names}
        for future in as_completed(futures):
            try:
                if future.result():
                    seeded += 1
            except Exception as e:
                print(f"{futures[future]}: {type(e).__name__}: {e}", flush=True)
            done += 1
            if done % 100 == 0:
                elapsed = time.monotonic() - started
                print(f"{done}/{len(names)} characters, {seeded} seeded, {elapsed:.0f}s", flush=True)

    print(f"done: {done} characters, {seeded} with a seed, {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
