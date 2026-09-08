#!/usr/bin/env python3
"""Load the v1 key-value documents into the v2 SQLite schema.

Accepts either a Postgres dump of the `kv_store` table (`kv_store.sql`) or the
directory of JSON files written by `export_neon_snapshot.py`.

Idempotent: re-running will not duplicate rows.

    uv run python scripts/migrate_v1_to_sqlite.py --dump kv_store.sql
    uv run python scripts/migrate_v1_to_sqlite.py --snapshot snapshot/
    uv run python scripts/migrate_v1_to_sqlite.py --dump kv_store.sql --db data/imgmanager.db
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DOC_KEYS = ("characters", "custom_images", "saved_characters", "last_updated")
_INSERT_RE = re.compile(r"^insert into \"kv_store\".*?values \('([a-z_]+)', '(.*)'\);\s*$")


def load_from_dump(path: Path) -> dict:
    docs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _INSERT_RE.match(line)
        if m:
            # Postgres escapes a single quote by doubling it.
            docs[m.group(1)] = json.loads(m.group(2).replace("''", "'"))
    return docs


def load_from_snapshot(path: Path) -> dict:
    docs = {}
    for key in DOC_KEYS:
        f = path / f"{key}.json"
        if f.exists():
            docs[key] = json.loads(f.read_text(encoding="utf-8"))
    return docs


def merge_characters(raw: list) -> tuple[list, list]:
    """Collapse duplicate names, later non-empty values winning.

    The live data contains 'Levy McGarden' twice: once as seeded (with a rank and
    a local image filename) and once re-added later through Add Character (no
    rank, an ImgChest URL). Taking the later non-empty value for each field keeps
    both halves rather than discarding one record.
    """
    by_name: dict[str, dict] = {}
    merged: list[str] = []
    for entry in raw:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        if name not in by_name:
            by_name[name] = {
                "name": name,
                "series": entry.get("series") or "",
                "rank": entry.get("rank") or "",
                "main_image_url": entry.get("main_image_url") or "",
            }
            continue
        merged.append(name)
        target = by_name[name]
        for field in ("series", "rank", "main_image_url"):
            value = entry.get(field) or ""
            if value:
                target[field] = value
    return list(by_name.values()), merged


def iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--dump", type=Path, help="Postgres dump of the kv_store table")
    src.add_argument("--snapshot", type=Path, help="directory of JSON documents")
    parser.add_argument("--db", type=Path, default=None, help="target SQLite file")
    args = parser.parse_args()

    if args.db:
        import os

        os.environ["DATABASE_PATH"] = str(args.db)

    import db as dbm

    docs = load_from_dump(args.dump) if args.dump else load_from_snapshot(args.snapshot)
    for key in DOC_KEYS:
        docs.setdefault(key, [] if key in ("characters", "saved_characters") else {})

    characters, merged = merge_characters(docs["characters"])
    custom_images = docs["custom_images"] or {}
    last_updated = docs["last_updated"] or {}
    saved = docs["saved_characters"] or []

    print(f"target: {dbm.database_path()}")
    print(
        f"source: {len(docs['characters'])} character records "
        f"({len(characters)} after merging {len(merged)} duplicate name(s)), "
        f"{sum(len(v or []) for v in custom_images.values())} images across "
        f"{len(custom_images)} characters"
    )
    if merged:
        print(f"  merged duplicates: {merged}")

    with dbm.transaction() as conn:
        # --- characters -------------------------------------------------
        for c in characters:
            conn.execute(
                "INSERT INTO characters (name, series, rank, main_image_url)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET"
                "   series = excluded.series, rank = excluded.rank,"
                "   main_image_url = excluded.main_image_url",
                (c["name"], c["series"], c["rank"], c["main_image_url"]),
            )

        # Any name that owns images but never appeared in the character list.
        created = 0
        for name in custom_images:
            cur = conn.execute(
                "INSERT INTO characters (name) VALUES (?) ON CONFLICT (name) DO NOTHING", (name,)
            )
            created += cur.rowcount
        if created:
            print(f"  created {created} character(s) that only existed in custom_images")

        ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM characters")}

        # --- custom images ----------------------------------------------
        inserted = skipped = 0
        for name, urls in custom_images.items():
            char_id = ids[name]
            position = 0
            for url in urls or []:
                if not isinstance(url, str) or not url.startswith("http"):
                    skipped += 1
                    continue
                cur = conn.execute(
                    "INSERT INTO custom_images (character_id, url, position, added_by)"
                    " VALUES (?, ?, ?, NULL) ON CONFLICT (character_id, url) DO NOTHING",
                    (char_id, url, position),
                )
                if cur.rowcount:
                    inserted += 1
                    position += 1
        print(
            f"  images inserted: {inserted}" + (f", skipped {skipped} non-URL" if skipped else "")
        )

        # --- timestamps ---------------------------------------------------
        applied = orphaned = 0
        for name, ts in last_updated.items():
            char_id = ids.get(name)
            if char_id is None:
                orphaned += 1
                continue
            try:
                conn.execute(
                    "UPDATE characters SET updated_at = ? WHERE id = ?", (iso(ts), char_id)
                )
                applied += 1
            except (ValueError, OSError, OverflowError):
                orphaned += 1
        print(
            f"  timestamps applied: {applied}"
            + (f", {orphaned} for unknown names" if orphaned else "")
        )

        # --- bookmarks ------------------------------------------------------
        if saved:
            conn.execute(
                "INSERT INTO identities (id, handle, role) VALUES (?, 'Legacy', 'user')"
                " ON CONFLICT (id) DO NOTHING",
                (dbm.LEGACY_IDENTITY_ID,),
            )
            for entry in saved:
                char_id = ids.get(entry.get("name"))
                if char_id is not None:
                    conn.execute(
                        "INSERT INTO saved (identity_id, character_id) VALUES (?, ?)"
                        " ON CONFLICT DO NOTHING",
                        (dbm.LEGACY_IDENTITY_ID, char_id),
                    )
            print(f"  bookmarks migrated: {len(saved)}")
        else:
            print("  bookmarks: none in source (v1's global list was empty)")

    # --- verification -------------------------------------------------------
    conn = dbm.get_connection()
    n_chars = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
    n_imgs = conn.execute("SELECT COUNT(*) FROM custom_images").fetchone()[0]
    expected_imgs = sum(
        1
        for urls in custom_images.values()
        for u in (urls or [])
        if isinstance(u, str) and u.startswith("http")
    )
    print(f"\nresult: {n_chars} characters, {n_imgs} images")
    ok = n_chars == len(ids) and n_imgs == expected_imgs
    print("verification:", "OK" if ok else f"MISMATCH (expected {expected_imgs} images)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
