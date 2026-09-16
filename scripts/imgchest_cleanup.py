#!/usr/bin/env python3
"""One-time cut-over reconciliation of the ImgChest account.

Nothing was ever deleted from ImgChest, so the account still holds every upload
the app and v1 ever made -- including images no database references any more and
griefed or otherwise inappropriate uploads made before moderation existed. This
is the one moment to reconcile the account against what is actually used.

Two keep sets:

- **in use** -- present in a Discord export of the URLs named in Mudae's `$ai`
  lists (ground truth from the operator).
- **on site** -- present in `custom_images`, in *any* state. That matters: an
  image removed on the site but still used in Discord must not be deleted.

Everything in neither set is a deletion candidate. In-use images the site does
not have are re-added in the `removed` state so they surface in the Removed
drawer and can be restored -- they land with `added_by IS NULL`, like every other
migrated row, so staff restore them.

Deletion is per *post*: ImgChest refuses to delete the only image in a post, so a
single-image post is deleted whole and one with siblings loses only the file. A
post with any keeper is never deleted -- only its non-keeper files are.

The preview is the gate. Nothing is deleted without `--execute`, and the operator
reviews the preview (also rendered in the owner-only Cut-over tab) first.

    uv run python scripts/imgchest_cleanup.py \\
        --username NAME --export discord-export.txt --preview preview.json
    uv run python scripts/imgchest_cleanup.py ... --limit 5 --execute
    uv run python scripts/imgchest_cleanup.py ... --execute

The script is rate-limit aware (60 requests a minute), and safe to re-run: a file
already gone reads as gone, and already-present rows are skipped on re-add.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import imgchest_utils  # noqa: E402
from imgchest_utils import ImgChestError  # noqa: E402

_BASE = "https://api.imgchest.com/v1"
_PER_PAGE = 100
# The API allows 60 requests a minute; a page a second keeps clear of it.
_PAGE_DELAY = 1.05
# Between file/post deletes, to stay inside the same window.
_DELETE_DELAY = 1.05

# The recovery rows are created by staff hand on the operator's behalf.
_RECOVER_REASON = "recovered at cut-over"


# --- The Discord export ---------------------------------------------------


def parse_export(text: str) -> tuple[dict[str, str], list[str]]:
    """Parse `Character - URL` lines into {url: character}, plus malformed lines.

    The export comes from several servers, so the same URL appears more than
    once, under whatever name that server used. The first name wins and later
    duplicates are dropped -- the URL, not the label, is what identifies the
    image. Malformed lines are returned rather than ignored so the preview can
    show them.
    """
    in_use: dict[str, str] = {}
    malformed: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Character names can contain ' - ', so split on the *last* separator,
        # which is the one before the URL.
        sep = line.rfind(" - ")
        if sep == -1:
            malformed.append(line)
            continue
        character = line[:sep].strip()
        url = line[sep + 3 :].strip()
        if not character or not url.lower().startswith(("http://", "https://")):
            malformed.append(line)
            continue
        in_use.setdefault(url, character)
    return in_use, malformed


# --- The ImgChest account -------------------------------------------------


def list_posts(username: str, token: str) -> list[dict]:
    """Every post on the account, with its slug and first image's file id.

    Returns `[{slug, file_id, post_id, image_count}]`. `post_id` is the slug (the
    app stores the same value the create response called the id). The listing
    exposes a post's *first* image only, so a hand-merged post shows an
    `image_count` above one and is surfaced as a warning rather than guessed at.
    """
    headers = {"Authorization": f"Bearer {token}"}
    posts: list[dict] = []
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
            print(f"  rate limited listing posts, sleeping {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
        response.raise_for_status()
        body = response.json()
        for post in body.get("data", []):
            thumbnail = post.get("thumbnail") or {}
            posts.append(
                {
                    "slug": post.get("slug"),
                    "file_id": thumbnail.get("id"),
                    "post_id": post.get("id") or post.get("slug"),
                    "image_count": post.get("image_count") or len(post.get("images") or []) or 1,
                }
            )
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page") or 1):
            break
        page += 1
        time.sleep(_PAGE_DELAY)
    return posts


# --- Bucketing ------------------------------------------------------------


def build_plan(
    posts: list[dict],
    in_use: dict[str, str],
    on_site_file_ids: set[str],
    on_site_urls: set[str],
) -> dict:
    """The four buckets, from the post listing and the two keep sets.

    `on_site_file_ids` is matched against the listing to decide what to *delete*,
    because a stored URL's extension is not assumed to read back cleanly from the
    listing and the file id is the stable key. `on_site_urls` is what decides
    what to *recover*, by exact string, because the export gave exact URLs and an
    in-use URL already present in the database (in any state) is not missing.

    A post is *kept* as a unit when its file is a keeper, so a post with siblings
    loses only the files that are not. What we can address is bounded by the
    listing: it exposes a post's first image id, which -- because the app uploads
    one image per post -- is the file we know about.
    """
    in_use_file_ids = {fid for fid in (imgchest_utils.file_id_from_url(u) for u in in_use) if fid}
    keepers: set[str] = set()
    for post in posts:
        file_id = post["file_id"]
        if not file_id:
            continue
        if file_id in on_site_file_ids or file_id in in_use_file_ids:
            keepers.add(file_id)

    delete: list[dict] = []
    warnings: list[dict] = []
    for post in posts:
        file_id = post["file_id"]
        if post["image_count"] > 1:
            warnings.append(
                {
                    "kind": "multi_image_post",
                    "post_id": post["post_id"],
                    "detail": f"post has {post['image_count']} images; the listing exposes "
                    "only the first, so any others cannot be addressed by this pass",
                }
            )
        if not file_id or file_id in keepers:
            continue
        delete.append(
            {
                "file_id": file_id,
                "post_id": post["post_id"],
                "image_count": post["image_count"],
                "url": f"https://cdn.imgchest.com/files/{file_id}",
            }
        )

    # In-use but not on the site: recover into the Removed drawer. Compared by
    # exact URL against the database, not by file id.
    recover = [
        {"character": character, "url": url}
        for url, character in in_use.items()
        if url not in on_site_urls
    ]
    return {"delete": delete, "recover": recover, "warnings": warnings, "keepers": keepers}


def record_post_ids(posts: list[dict], rows: list[dict]) -> int:
    """Store the ImgChest post id on every row whose file the listing named.

    The app needs it to delete a post later; this pass has the listing in hand,
    so it fills the column the same way `backfill_imgchest_post_ids.py` would --
    except that script can go once the cleanup has run. Only NULL columns are
    written, so a re-run and the existing backfill cannot disagree.
    """
    file_to_post = {p["file_id"]: p["post_id"] for p in posts if p["file_id"] and p["post_id"]}
    written = 0
    for row in rows:
        file_id = imgchest_utils.file_id_from_url(row["url"])
        if not file_id:
            continue
        post_id = file_to_post.get(file_id)
        if post_id and db.set_imgchest_post_id(row["url"], post_id):
            written += 1
    return written


# --- Execute --------------------------------------------------------------


def delete_candidate(candidate: dict) -> None:
    """Delete one candidate, whole post or single file.

    Mirrors the app's permanent-delete logic: a single-image post is deleted
    whole, a post with siblings loses only the file. A post already gone is fine.
    The token comes from IMGCHEST_API_KEY via `imgchest_utils`.
    """
    if candidate["image_count"] > 1:
        imgchest_utils.delete_imgchest_file(candidate["file_id"])
    else:
        imgchest_utils.delete_imgchest_post(candidate["post_id"])


def recover_rows(recover: list[dict], added_by: str | None) -> int:
    """Re-add the in-use-but-missing images into the Removed drawer.

    Two existing paths, not hand-rolled SQL: `add_custom_images` creates the row,
    `remove_custom_images` soft-deletes it with a reason. They land active for a
    moment and are immediately removed, which is exactly the state the drawer
    lists. `added_by` is normally NULL for migrated rows; it is a parameter only
    so a test can avoid creating an identities row.
    """
    by_character: dict[str, list[str]] = {}
    for item in recover:
        by_character.setdefault(item["character"], []).append(item["url"])
    recovered = 0
    for character, urls in by_character.items():
        recovered += db.add_custom_images(character, urls, added_by=added_by)
        # Staff act on behalf of the inherited library; passing the actor is what
        # the removal path wants. A module-level constant keeps the reason fixed.
        db.remove_custom_images(
            character, urls, actor_id=added_by or "", is_moderator=True, reason=_RECOVER_REASON
        )
    return recovered


# --- Entry point ----------------------------------------------------------


def _summarise(in_use: dict, on_site_urls: set, plan: dict) -> dict:
    delete = plan["delete"]
    recover = plan["recover"]
    return {
        "files_in_use": len(in_use),
        "files_on_site": len(on_site_urls),
        "keepers": len(plan["keepers"]),
        "delete_candidates": len(delete),
        "recoverable": len(recover),
        "multi_image_posts": len(plan["warnings"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="the ImgChest account's username")
    parser.add_argument("--export", required=True, help="path to the Discord export (.txt)")
    parser.add_argument(
        "--preview",
        default="imgchest-cleanup-preview.json",
        help="where to write the preview the app renders",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually delete and recover; without it this is a dry run",
    )
    parser.add_argument(
        "--no-recover",
        action="store_true",
        help="with --execute, delete only; do not re-add the recover set",
    )
    parser.add_argument(
        "--rescue",
        action="append",
        default=[],
        metavar="URL",
        help="force a URL into the keep set (repeatable); use when the preview shows a surprise",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="with --execute, delete at most N candidates (0 = all); for a trial run",
    )
    args = parser.parse_args()

    token = os.environ.get("IMGCHEST_API_KEY", "").strip()
    if not token:
        return _fail("IMGCHEST_API_KEY is not set.")

    export_path = Path(args.export)
    if not export_path.exists():
        return _fail(f"export not found: {export_path}")
    in_use, malformed = parse_export(export_path.read_text(encoding="utf-8"))
    print(f"export: {len(in_use)} unique in-use URLs, {len(malformed)} malformed lines")

    for url in args.rescue:
        in_use.setdefault(url, "(rescued)")

    print(f"listing posts for {args.username} ...")
    posts = list_posts(args.username, token)
    print(f"  {len(posts)} posts listed")

    rows = db.all_custom_image_urls()
    # Match by file id, because a stored URL's extension is not always readable
    # from the listing; the id is the stable key. The exact URLs are the recover
    # comparison.
    on_site_file_ids = {
        fid for fid in (imgchest_utils.file_id_from_url(r["url"]) for r in rows) if fid
    }
    on_site_urls = {r["url"] for r in rows}

    plan = build_plan(posts, in_use, on_site_file_ids, on_site_urls)
    counts = _summarise(in_use, on_site_urls, plan)

    preview = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "account": args.username,
        "export": {
            "path": str(export_path),
            "unique_urls": len(in_use),
            "malformed": malformed[:200],
            "malformed_total": len(malformed),
        },
        "counts": counts,
        "delete": plan["delete"],
        "recover": plan["recover"],
        "warnings": plan["warnings"],
        "executed": False,
    }

    Path(args.preview).write_text(json.dumps(preview, indent=2), encoding="utf-8")
    print(f"preview written to {args.preview}")
    for key, value in counts.items():
        print(f"  {key}: {value}")

    if not args.execute:
        print("\ndry run: nothing deleted. Review the preview, then re-run with --execute.")
        return 0

    delete_list = plan["delete"]
    if args.limit:
        delete_list = delete_list[: args.limit]
    print(f"\ndeleting {len(delete_list)} candidate(s) ...")
    deleted = 0
    failed = 0
    for candidate in delete_list:
        try:
            delete_candidate(candidate)
            deleted += 1
        except ImgChestError as e:
            failed += 1
            print(f"  ! {candidate['file_id']}: {e}", file=sys.stderr)
        time.sleep(_DELETE_DELAY)
    print(f"  deleted {deleted}, failed {failed}")

    recovered = 0
    if plan["recover"] and not args.no_recover:
        print(f"recovering {len(plan['recover'])} in-use image(s) into the Removed drawer ...")
        recovered = recover_rows(plan["recover"], added_by=None)
        print(f"  recovered {recovered}")

    # Fill the post ids the survivors need, from the listing already fetched.
    post_ids = record_post_ids(posts, rows)
    print(f"recorded {post_ids} ImgChest post id(s)")

    preview["executed"] = True
    preview["executed_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    preview["deleted"] = deleted
    preview["delete_failed"] = failed
    preview["recovered"] = recovered
    preview["post_ids_recorded"] = post_ids
    Path(args.preview).write_text(json.dumps(preview, indent=2), encoding="utf-8")
    print("\nDone.")
    return 0


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
