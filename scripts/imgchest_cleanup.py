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

Recover candidates are probed for liveness before they are planned. The export
records what was pasted into Discord, not what is still hosted, so a URL can be
in it and gone -- and putting a 404 back on the site is a broken image for staff
to remove again. Dead files are reported in their own list and never recovered;
`--no-verify` skips the probing. URLs hosted anywhere but ImgChest are somebody
else's upload and are reported the same way.

`--execute` does not act on that preview, because it cannot: every run re-lists
the account and rebuilds the plan, so the execute run builds a *fresh* one. It
therefore compares a fingerprint of which files it would delete against the
preview on disk and refuses if they differ, leaving the reviewed file alone and
writing this run's plan beside it as `.proposed.json`. `--force` is the only way
past, for a change that has been looked at and expected. See `CUTOVER.md`.

    uv run python scripts/imgchest_cleanup.py \\
        --username NAME --export discord-export.txt --preview preview.json
    uv run python scripts/imgchest_cleanup.py ... --limit 5 --execute
    uv run python scripts/imgchest_cleanup.py ... --execute

The script is rate-limit aware (60 requests a minute), and safe to re-run: a file
already gone reads as gone, and already-present rows are skipped on re-add.
"""

from __future__ import annotations

import argparse
import hashlib
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
import image_utils  # noqa: E402
import imgchest_utils  # noqa: E402
from imgchest_utils import ImgChestError  # noqa: E402
from remote_images import _request_headers_for_image_import  # noqa: E402

_BASE = "https://api.imgchest.com/v1"
_PER_PAGE = 100
# The API allows 60 requests a minute; a page a second keeps clear of it.
_PAGE_DELAY = 1.05
# Between file/post deletes, to stay inside the same window.
_DELETE_DELAY = 1.05
# Between liveness probes. These are CDN requests rather than API ones, but the
# same host rate-limits and a check is not worth being the thing that gets us
# throttled during a listing.
_PROBE_DELAY = 0.15
# A liveness probe has to be cheap: the answer is in the status line, so the
# body is cut off after a few bytes.
_PROBE_TIMEOUT = 20

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


# --- Liveness -------------------------------------------------------------


def url_is_alive(url: str) -> bool:
    """Whether an image URL still serves an image.

    The export is a record of what was pasted into Discord, not of what is still
    hosted. Images get deleted from ImgChest over time, so a URL can be in the
    export and genuinely gone -- and re-adding one puts a dead link on the site
    for staff to clean up later.

    A bare `requests.get` is not enough: ImgChest answers 403 to anything without
    a browser User-Agent, which reads as "gone" when the image is fine. The
    headers are the app's own image-fetch headers for the same reason. The body
    is abandoned after the status line, so this costs a round trip rather than a
    download.
    """
    try:
        response = requests.get(
            url,
            headers=_request_headers_for_image_import(url),
            timeout=_PROBE_TIMEOUT,
            stream=True,
        )
        try:
            if response.status_code != 200:
                return False
            return response.headers.get("Content-Type", "").lower().startswith("image/")
        finally:
            response.close()
    except requests.RequestException:
        # A network failure is not evidence the image is gone, but it is
        # evidence it cannot be recovered right now, which is the same result.
        return False


def partition_recover(in_use: dict, on_site_urls: set, *, verify: bool = True) -> dict:
    """Split in-use-but-missing URLs into recover / dead / foreign.

    - **recover** -- ImgChest, still serving an image. The only set worth putting
      back on the site.
    - **dead** -- ImgChest, but the file is gone. Reported so the operator can see
      what Discord is still pointing at, never recovered.
    - **foreign** -- not ImgChest, so never this app's upload. Reported, never
      recovered.

    With `verify` off, everything ImgChest goes to `recover` and `dead` is empty,
    which is the behaviour before the probe existed.
    """
    recover: list[dict] = []
    dead: list[dict] = []
    foreign: list[dict] = []
    checked = 0
    for url, character in in_use.items():
        if url in on_site_urls:
            continue
        entry = {"character": character, "url": url}
        if not imgchest_utils.file_id_from_url(url):
            foreign.append(entry)
            continue
        if verify:
            checked += 1
            if checked > 1:
                time.sleep(_PROBE_DELAY)
            if not url_is_alive(url):
                dead.append(entry)
                continue
        recover.append(entry)
    return {"recover": recover, "dead": dead, "foreign": foreign}


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
                # The app uploads under `image_utils.UPLOAD_SUFFIX`, and the
                # listing's file id alone (no suffix) is not a fetchable URL --
                # the preview's thumbnails 404'd without this.
                "url": f"https://cdn.imgchest.com/files/{file_id}{image_utils.UPLOAD_SUFFIX}",
            }
        )

    # In-use but not on the site: recover into the Removed drawer. Compared by
    # exact URL against the database, not by file id.
    #
    # Split by whether the app could have made the URL, and -- done here rather
    # than in this pure function -- by whether the file still exists. The app has
    # only ever uploaded to ImgChest, so an Imgur URL in the export is somebody
    # else's upload that happens to be used in Discord; re-adding it would put a
    # foreign image on the site, under a row that could never be permanently
    # deleted from here because this account has no post for it. A dead ImgChest
    # file is the same problem from the other end: put back, it is a broken
    # image for staff to remove again. Both are reported and never recovered;
    # `main` probes liveness and moves what fails into `dead`.
    #
    # Kept pure -- no network -- so the bucketing stays testable without an
    # ImgChest account or a running clock.
    recover = []
    foreign = []
    for url, character in in_use.items():
        if url in on_site_urls:
            continue
        entry = {"character": character, "url": url}
        if imgchest_utils.file_id_from_url(url):
            recover.append(entry)
        else:
            foreign.append(entry)
    return {
        "delete": delete,
        "recover": recover,
        "foreign": foreign,
        "warnings": warnings,
        "keepers": keepers,
    }

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
    lists.

    No actor, deliberately. `added_by` is normally NULL for migrated rows, and
    the removal is passed `actor_id=None` so `removed_by` stays NULL too -- no
    person made this call, the script did. Passing an empty string here instead
    is not harmless: it is non-NULL, so the rows join to an identity and surface
    in that identity's moderation history under a generated pseudonym. That
    happened once, to 1,222 rows, and they read as removed by "Gilded Wigeon".
    """
    by_character: dict[str, list[str]] = {}
    for item in recover:
        by_character.setdefault(item["character"], []).append(item["url"])
    recovered = 0
    for character, urls in by_character.items():
        recovered += db.add_custom_images(character, urls, added_by=added_by)
        # Staff act on behalf of the inherited library, so the removal is allowed
        # to bypass ownership -- but it is not attributed to anyone.
        db.remove_custom_images(
            character, urls, actor_id=None, is_moderator=True, reason=_RECOVER_REASON
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
        "dead_urls": len(plan.get("dead") or []),
        "foreign_urls": len(plan.get("foreign") or []),
        "multi_image_posts": len(plan["warnings"]),
    }


def delete_fingerprint(delete: list[dict]) -> str:
    """A stable digest of *which* files are about to be deleted.

    Only the file ids, sorted, because that is the set that matters: the fate of
    every candidate. Order and any cosmetic field can change between two listings
    without changing what happens, so they are deliberately not part of it.

    This is what makes the review meaningful. Every run re-lists the account and
    rebuilds the plan from scratch, so an `--execute` run does not use the plan
    that was reviewed -- it builds a new one. If the account moved in between
    (new uploads, a post already gone, an updated export), the new plan can
    differ, and nothing about running the command says so.
    """
    ids = sorted(str(c.get("file_id") or "") for c in delete)
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def describe_delete_diff(reviewed: list[dict], current: list[dict]) -> list[str]:
    """Plain sentences for what changed between the reviewed and current plans."""
    reviewed_ids = {str(c.get("file_id") or "") for c in reviewed}
    current_ids = {str(c.get("file_id") or "") for c in current}
    added = current_ids - reviewed_ids
    removed = reviewed_ids - current_ids
    lines = [
        f"the reviewed plan had {len(reviewed_ids)} to delete; this run would delete {len(current_ids)}"
    ]
    if added:
        preview = ", ".join(sorted(added)[:5])
        more = f" (+{len(added) - 5} more)" if len(added) > 5 else ""
        lines.append(f"  newly in line to be deleted, not in what you reviewed: {preview}{more}")
    if removed:
        preview = ", ".join(sorted(removed)[:5])
        more = f" (+{len(removed) - 5} more)" if len(removed) > 5 else ""
        lines.append(f"  reviewed for deletion but no longer a candidate: {preview}{more}")
    return lines


def read_previous_preview(path: Path) -> dict | None:
    """The preview already on disk, or None if there is none or it is unreadable.

    Unreadable is returned as None on purpose: this is a guard rail, not a
    parser, and refusing to run because a previous preview was truncated would
    be its own failure. The caller decides what an absent preview means.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


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
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "with --execute, proceed even if the plan no longer matches the preview"
            " on disk; for when you have deliberately re-reviewed"
        ),
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help=(
            "skip probing recover candidates for liveness; faster, but dead links"
            " then get re-added to the site"
        ),
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
    # A cleanup plans against what the site holds, so an empty read is never a
    # real state -- it means the database was not found. The likely cause is a
    # missing DATABASE_PATH: `db` falls back to ./data/imgmanager.db and *creates*
    # it if absent, so the run plans against a brand-new empty file, reports
    # files_on_site: 0, and computes a delete list that keeps only what the export
    # names. That is thousands of extra deletions, and nothing about the output
    # would say so.
    if not rows:
        return _fail(
            f"the database at {db.database_path()} holds no images, which cannot be"
            " right for a cleanup. Set DATABASE_PATH to the real database and re-run."
        )
    print(f"database: {db.database_path()} ({len(rows)} rows)")
    # Match by file id, because a stored URL's extension is not always readable
    # from the listing; the id is the stable key. The exact URLs are the recover
    # comparison.
    on_site_file_ids = {
        fid for fid in (imgchest_utils.file_id_from_url(r["url"]) for r in rows) if fid
    }
    on_site_urls = {r["url"] for r in rows}

    plan = build_plan(posts, in_use, on_site_file_ids, on_site_urls)

    # Probe the recover candidates before anything is planned around them. The
    # export records what was pasted into Discord, not what is still hosted, so a
    # URL can be in it and gone -- and recovering one puts a broken image on the
    # site for staff to remove again. Skipped only on request.
    if args.no_verify:
        plan["dead"] = []
        print("recover candidates: liveness check skipped (--no-verify)")
    elif plan["recover"]:
        print(f"checking {len(plan['recover'])} recover candidate(s) are still hosted ...")
        parted = partition_recover(
            {entry["url"]: entry["character"] for entry in plan["recover"]},
            on_site_urls,
        )
        plan["recover"] = parted["recover"]
        plan["dead"] = parted["dead"]
        print(f"  {len(plan['recover'])} alive, {len(plan['dead'])} no longer hosted")
    else:
        plan["dead"] = []

    counts = _summarise(in_use, on_site_urls, plan)
    preview_path = Path(args.preview)
    # Read what is on disk before overwriting it: that is the plan the operator
    # reviewed, and the guard below compares it against this run's.
    previous = read_previous_preview(preview_path)
    fingerprint = delete_fingerprint(plan["delete"])

    preview = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "account": args.username,
        "fingerprint": fingerprint,
        "export": {
            "path": str(export_path),
            "unique_urls": len(in_use),
            "malformed": malformed[:200],
            "malformed_total": len(malformed),
        },
        "counts": counts,
        "delete": plan["delete"],
        "recover": plan["recover"],
        "dead": plan.get("dead") or [],
        "foreign": plan.get("foreign") or [],
        "warnings": plan["warnings"],
        "executed": False,
    }

    # The guard, before anything is written. Every run rebuilds the plan from a
    # fresh listing, so without this the delete list is whatever the account
    # looks like *now* -- which may not be what was reviewed, and deleting images
    # people are still using cannot be undone. A missing previous preview is
    # tolerated (a first `--execute` with no review step is the operator's own
    # choice); a *different* one is not, and refusing without overwriting leaves
    # the reviewed file in place so the two can be compared.
    if args.execute and not args.force and previous is not None:
        if previous.get("fingerprint") != fingerprint:
            proposed_path = preview_path.with_suffix(".proposed.json")
            proposed_path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
            print(
                "\nREFUSING TO EXECUTE: the plan has changed since the preview was written.",
                file=sys.stderr,
            )
            for line in describe_delete_diff(previous.get("delete") or [], plan["delete"]):
                print(line, file=sys.stderr)
            print(f"  What you reviewed is untouched at {preview_path}", file=sys.stderr)
            print(f"  This run's plan is at {proposed_path} — diff them.", file=sys.stderr)
            print(
                "  Re-run without --execute to review it in the app, or pass --force"
                " to accept this plan as it stands.",
                file=sys.stderr,
            )
            return _fail("aborted: preview does not match the current plan")
    elif args.execute and not args.force and previous is None:
        print(
            "\nnote: no readable preview at that path, so there is nothing to check this run"
            " against. Run without --execute first to review the plan.",
            file=sys.stderr,
        )

    preview_path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    print(f"preview written to {preview_path}")
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
