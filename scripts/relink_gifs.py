#!/usr/bin/env python3
"""Re-host the GIFs that ImgChest stored under a `.png` link.

From 2026-09-10 every upload was named `….png` on ImgChest (`imgchest_filename`),
and ImgChest takes a link's extension from that name rather than the bytes. An
animated GIF, the one upload kept as-is, therefore came back as a `.png` link:
the gallery treated it as a still and thumbnailed its first frame, and the `$ai`
command carried a link Mudae could not use. The same file is not reachable under
`.gif` (ImgChest answers 404), so the only repair is a fresh upload.

`upload_to_imgchest` now names GIF bytes `.gif`. This fixes the rows uploaded
before that: it reads the first bytes of every `.png` link, and for each that is
really a GIF it downloads the file, uploads it again (as `.gif`), points the row
at the new link and drops the still thumbnail, so the gallery falls back to the
animated original the way it does for every other GIF.

Dry run by default. Nothing is deleted from ImgChest unless `--delete-old`.

    uv run python scripts/relink_gifs.py
    uv run python scripts/relink_gifs.py --apply
"""

import argparse
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402
import imgchest_utils  # noqa: E402
import thumbnails  # noqa: E402
from remote_images import imgchest_filename  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (imgmanager maintenance)"}


def _is_gif(session: requests.Session, url: str) -> bool | None:
    """True for GIF bytes; None when the link could not be read."""
    try:
        response = session.get(url, headers={"Range": "bytes=0-15"}, timeout=30)
    except requests.RequestException:
        return None
    return response.ok and response.content[:6] in (b"GIF87a", b"GIF89a")


def _candidates(since: str) -> list[dict]:
    rows = (
        db.get_connection()
        .execute(
            "SELECT ci.id, ci.url, ci.thumb_key, ci.imgchest_post_id, ci.state, c.name"
            "  FROM custom_images ci JOIN characters c ON c.id = ci.character_id"
            " WHERE lower(ci.url) LIKE '%.png' AND ci.added_at >= ? AND ci.purged_at IS NULL"
            " ORDER BY ci.id",
            (since,),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def _relink(session: requests.Session, row: dict, delete_old: bool) -> str:
    response = session.get(row["url"], timeout=120)
    response.raise_for_status()
    handle, path = tempfile.mkstemp(suffix=".gif")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(response.content)
        result = imgchest_utils.upload_to_imgchest(path, upload_name=imgchest_filename(row["name"]))
    finally:
        os.remove(path)
    if not result or not result[1].lower().endswith(".gif"):
        raise RuntimeError(f"ImgChest did not return a .gif link: {result}")
    _, new_url, post_id = result

    with db.transaction() as conn:
        updated = conn.execute(
            "UPDATE custom_images SET url = ?, imgchest_post_id = ?, thumb_key = NULL"
            " WHERE id = ? AND url = ?",
            (new_url, post_id, row["id"], row["url"]),
        ).rowcount
    if not updated:
        raise RuntimeError("the row changed underneath; new upload left unused: " + new_url)

    # The still thumbnail is what hid the animation; without it the gallery
    # loads the GIF itself. Best effort -- an orphaned object is harmless.
    if row["thumb_key"]:
        thumbnails.delete_mirror(row["thumb_key"])
    thumbnails.cache_path(row["id"]).unlink(missing_ok=True)
    if delete_old and row["imgchest_post_id"]:
        imgchest_utils.delete_imgchest_post(row["imgchest_post_id"])
    return new_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Re-upload and update the rows")
    parser.add_argument(
        "--since", default="2026-09-10", help="Only rows added on or after this date"
    )
    parser.add_argument(
        "--delete-old", action="store_true", help="Also delete the old `.png` post on ImgChest"
    )
    args = parser.parse_args()

    print(f"database: {db.database_path()}")
    session = requests.Session()
    session.headers.update(HEADERS)
    rows = _candidates(args.since)
    print(f"checking {len(rows)} .png links added since {args.since}")

    # Only the first 16 bytes of each, but there can be thousands: read them in
    # parallel. The CDN is Cloudflare's, and this is a fraction of a gallery view.
    with ThreadPoolExecutor(12) as pool:
        verdicts = list(pool.map(lambda row: _is_gif(session, row["url"]), rows))
    unreadable = [row for row, verdict in zip(rows, verdicts, strict=True) if verdict is None]
    for row in unreadable:
        print(f"  could not read #{row['id']} {row['url']}")
    gifs = [row for row, verdict in zip(rows, verdicts, strict=True) if verdict]

    failed = 0
    for row in gifs:
        label = f"#{row['id']} {row['name']} ({row['state']}) {row['url']}"
        if not args.apply:
            print(f"  would relink {label}")
            continue
        try:
            print(f"  relinked {label} -> {_relink(session, row, args.delete_old)}")
        except Exception as exc:  # noqa: BLE001 -- report and carry on with the rest
            failed += 1
            print(f"  FAILED {label}: {exc}")

    verb = "relinked" if args.apply else "to relink"
    print(f"{len(gifs) - failed} {verb}, {failed} failed, {len(unreadable)} unreadable")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
