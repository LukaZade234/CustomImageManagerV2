#!/usr/bin/env python3
"""Remove the personal notes that slipped into character names.

A few catalog extracts carried a note typed after the name, and it landed in the
name itself: "Sora (HCLW) | wish later". `catalog_import.strip_account_marker`
now drops it on import; this cleans the rows already stored, in both the catalog
and the working set.

Each noted row is renamed to its clean name, unless a row with that name already
exists in the same table. In the catalog the noted row is then a duplicate and is
deleted. In the working set it is only reported: a working character owns images,
bookmarks and history, and merging two of them is a decision, not a cleanup.

Dry run by default.

    uv run python scripts/strip_name_notes.py
    uv run python scripts/strip_name_notes.py --apply
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import catalog_import  # noqa: E402
import db  # noqa: E402


def plan(conn) -> list[tuple[str, str, int, str, str]]:
    """(table, action, id, name, clean name) for every noted name."""
    steps = []
    for table in ("character_catalog", "characters"):
        rows = conn.execute(f"SELECT id, name FROM {table}").fetchall()
        taken = {catalog_import.name_key(row["name"]) for row in rows}
        for row in rows:
            clean = catalog_import.strip_account_marker(row["name"])
            if clean == row["name"]:
                continue
            if catalog_import.name_key(clean) not in taken:
                action = "rename"
            elif table == "character_catalog":
                action = "delete"
            else:
                action = "skip"
            steps.append((table, action, row["id"], row["name"], clean))
    return steps


def apply(conn, steps) -> None:
    for table, action, row_id, _name, clean in steps:
        if action == "rename":
            conn.execute(
                f"UPDATE {table} SET name = ?, name_key = ? WHERE id = ?",
                (clean, catalog_import.name_key(clean), row_id),
            )
        elif action == "delete":
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the changes")
    args = parser.parse_args()

    print(f"database: {db.database_path()}")
    with db.transaction() as conn:
        steps = plan(conn)
        for table, action, row_id, name, clean in steps:
            note = " (a working character with that name exists; merge by hand)" * (
                action == "skip"
            )
            print(f"  {action:6} {table} #{row_id}: {name!r} -> {clean!r}{note}")
        if args.apply:
            apply(conn, steps)
    print(f"{len(steps)} noted names{'' if args.apply else ' (dry run, nothing written)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
