#!/usr/bin/env python3
"""Fill `custom_images.imgchest_post_id` for images uploaded before we kept it.

Permanent delete deletes the ImgChest *post*, because the API refuses to delete
the only image in a post ("You can't delete the only image on a post"). The
create-post response always carried the post id; the app just never stored it, so
the whole pre-existing library has none and cannot be purged.

This recovers it from the API with no session and nothing risky:

    GET /v1/user/{username}/posts

lists every post -- hidden ones included -- with its `slug` and its first image's
file id (`thumbnail.id`). Every URL in the library is
`https://cdn.imgchest.com/files/{id}.{ext}`, so the file id maps straight back to
a post. The app only ever uploaded one image per post, so the first image is the
only image and the mapping is exact.

    uv run python scripts/backfill_imgchest_post_ids.py --username NAME --dry-run
    uv run python scripts/backfill_imgchest_post_ids.py --username NAME

A post with more than one image -- possible only if posts were merged by hand --
maps only its first image here; the rest stay NULL. Deletion is image-count-aware
either way, so a mapped image in such a post still deletes only itself.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import imgchest_utils  # noqa: E402

_BASE = "https://api.imgchest.com/v1"
_PER_PAGE = 100
# The API allows 60 requests a minute; a page a second keeps clear of it.
_PAGE_DELAY = 1.05


def list_posts(username, token):
    """Yield (slug, file_id) for every post, page by page."""
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    while True:
        response = requests.get(
            f"{_BASE}/user/{username}/posts",
            headers=headers,
            params={"page": page, "per_page": _PER_PAGE},
            timeout=(30, 120),
        )
        if response.status_code == 429:
            wait = float(response.headers.get("Retry-After") or 60)
            time.sleep(wait)
            continue
        response.raise_for_status()
        body = response.json()
        for post in body.get("data", []):
            thumbnail = post.get("thumbnail") or {}
            yield post.get("slug"), thumbnail.get("id")
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page") or 1):
            break
        page += 1
        time.sleep(_PAGE_DELAY)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="the ImgChest account's username")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    token = os.environ.get("IMGCHEST_API_KEY", "").strip()
    if not token:
        sys.exit("IMGCHEST_API_KEY is not set.")

    print(f"Listing posts for {args.username} ...")
    file_to_slug = {}
    listed = 0
    for slug, file_id in list_posts(args.username, token):
        listed += 1
        if slug and file_id:
            file_to_slug.setdefault(file_id, slug)
    print(f"  {listed} posts listed, {len(file_to_slug)} with a usable first image")

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT id, url FROM custom_images WHERE imgchest_post_id IS NULL"
    ).fetchall()
    updates = []
    unmatched = 0
    for row in rows:
        file_id = imgchest_utils.file_id_from_url(row["url"])
        slug = file_to_slug.get(file_id) if file_id else None
        if slug:
            updates.append((slug, row["id"]))
        else:
            unmatched += 1

    print(f"  {len(rows)} rows with no post id: {len(updates)} matched, {unmatched} unmatched")
    if args.dry_run:
        print("dry run: nothing written")
        return

    with db.transaction() as transaction:
        transaction.executemany(
            "UPDATE custom_images SET imgchest_post_id = ? WHERE id = ?",
            updates,
        )
    print(f"wrote {len(updates)} post ids")


if __name__ == "__main__":
    main()
