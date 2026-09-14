#!/usr/bin/env python3
"""Seed made-up leaderboard data so the home page can be reviewed.

The home page ranks four things off `/api/stats`: most visited characters,
most covered characters, most covered series and top contributors. Characters,
series and images are real data and are usually already populated. The
contributor board, though, hides itself unless more than one contributor
exists, which leaves the layout impossible to review on a quiet database.

This script invents contributors and view activity so every ranked section
renders. It touches nothing that carries the artwork: it only borrows active
images that have no owner (`added_by IS NULL`, the images migrated from v1)
and hands them to invented Discord identities, and it writes view rows under
invented viewer ids. No character, image, URL or timestamp is created,
changed or removed. The invented identities are attribution-hidden, so they
rank without printing made-up names onto real character pages.

    # Add the demo board to the working database.
    uv run python scripts/seed_leaderboard_demo.py

    # Remove it again.
    uv run python scripts/seed_leaderboard_demo.py --clean

Seeding is idempotent: it always clears the previous demo rows first. Cleaning
deletes the demo identities, which sets their borrowed images back to unowned
through the foreign key, and drops the demo views.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db  # noqa: E402  (path is fixed up above)

_CONTRIBUTOR_PREFIX = "demo-contrib-"
_VIEW_PREFIX = "demo-view-"

# Handles follow the app's adjective-plus-animal pseudonyms, so a seeded board
# reads like the real one. Counts descend so the ranking has a shape to look at.
_CONTRIBUTORS: list[tuple[str, int]] = [
    ("Scarlet Ibis", 214),
    ("Quiet Otter", 176),
    ("Amber Kestrel", 143),
    ("Vivid Moth", 118),
    ("Gentle Orca", 91),
    ("Rustic Ferret", 69),
    ("Lucid Lynx", 52),
    ("Bold Magpie", 38),
    ("Silent Heron", 29),
    ("Brave Newt", 17),
]

# Viewers per character, spread so the "most visited" board is not a tie.
_VIEW_COUNTS = [46, 39, 33, 28, 23, 19, 16, 13, 10, 8, 6, 4, 3, 2]


def _clean(conn) -> None:
    conn.execute("DELETE FROM character_views WHERE identity_id LIKE ?", (_VIEW_PREFIX + "%",))
    # custom_images.added_by is ON DELETE SET NULL, so borrowed images become
    # unowned again exactly as they were.
    conn.execute("DELETE FROM identities WHERE id LIKE ?", (_CONTRIBUTOR_PREFIX + "%",))


def _seed(conn) -> list[tuple[str, int]]:
    contributors = [
        (_CONTRIBUTOR_PREFIX + str(i), handle, count)
        for i, (handle, count) in enumerate(_CONTRIBUTORS)
    ]
    for ident, handle, _count in contributors:
        conn.execute(
            "INSERT INTO identities (id, handle, discord_id, hide_attribution)"
            " VALUES (?, ?, ?, 1)",
            (ident, handle, ident),
        )

    needed = sum(count for _i, _h, count in contributors)
    borrowed = conn.execute(
        "SELECT id FROM custom_images"
        " WHERE state = 'active' AND added_by IS NULL"
        " ORDER BY RANDOM() LIMIT ?",
        (needed,),
    ).fetchall()
    if len(borrowed) < needed:
        raise SystemExit(
            f"Need {needed} unowned images to seed contributors, found {len(borrowed)}."
        )

    cursor = 0
    result: list[tuple[str, int]] = []
    for ident, handle, count in contributors:
        chunk = [row["id"] for row in borrowed[cursor : cursor + count]]
        cursor += count
        conn.executemany(
            "UPDATE custom_images SET added_by = ? WHERE id = ?",
            [(ident, image_id) for image_id in chunk],
        )
        result.append((handle, count))

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    bucket = now[:13]
    characters = conn.execute(
        "SELECT c.id, c.name FROM characters c"
        " JOIN custom_images ci ON ci.character_id = c.id AND ci.state = 'active'"
        " GROUP BY c.id ORDER BY COUNT(ci.id) DESC, c.name LIMIT ?",
        (len(_VIEW_COUNTS),),
    ).fetchall()
    for index, (viewers, character) in enumerate(zip(_VIEW_COUNTS, characters, strict=False)):
        conn.executemany(
            "INSERT INTO character_views (character_id, identity_id, bucket, viewed_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (identity_id, character_id, bucket)"
            " DO UPDATE SET viewed_at = excluded.viewed_at",
            [
                (character["id"], f"{_VIEW_PREFIX}{index}-{j}", bucket, now)
                for j in range(viewers)
            ],
        )
    return result


def _print_board(conn) -> None:
    print("\nTop contributors")
    for row in conn.execute(
        "SELECT i.handle, COUNT(ci.id) AS n FROM identities i"
        " JOIN custom_images ci ON ci.added_by = i.id AND ci.state = 'active'"
        " WHERE i.discord_id IS NOT NULL AND i.hide_from_leaderboard = 0"
        " GROUP BY i.id ORDER BY n DESC, i.handle LIMIT 10"
    ):
        print(f"  {row['handle']:<16} {row['n']}")

    print("\nMost visited this week")
    highlights = db.get_home_highlights()
    for row in highlights["most_viewed"]:
        print(f"  {row['name']:<24} {row['viewers']} viewers")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="database file (defaults to DATABASE_PATH or data/imgmanager.db)")
    parser.add_argument("--clean", action="store_true", help="remove the demo data and exit")
    args = parser.parse_args()

    if args.db:
        os.environ["DATABASE_PATH"] = str(args.db)

    conn = db.get_connection()
    if args.clean:
        with db.transaction():
            _clean(conn)
        print(f"Removed demo leaderboard data from {db.database_path()}.")
        return

    with db.transaction():
        _clean(conn)
        _seed(conn)

    print(f"Seeded demo leaderboard data in {db.database_path()}.\n")
    _print_board(conn)


if __name__ == "__main__":
    main()
