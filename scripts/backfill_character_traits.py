#!/usr/bin/env python3
"""Derive a character's gender and pool line from the Mudae catalog.

The catalog stores each character's pool codes (`wa`, `wg`, `ha`, `hg`) and the
four parsed booleans. Two of them are the gender and two are the roulette pool:

    w  waifu     -> female
    h  husbando  -> male
    a  Animanga  -> the "Animanga" pool
    g  Game      -> the "Game" pool

So `wa` is a woman in the Animanga roulette and `hg` a man in the Game one,
which is what a `$im` card prints beside and under the series. This copies that
onto the working rows so a character page shows it without a Discord lookup.

Only rows the catalog knows are touched; a name it does not have is left as it
was. Idempotent, and `updated_at` is not changed -- enriching from the catalog
is not a user edit.

    uv run python scripts/backfill_character_traits.py --dry-run
    uv run python scripts/backfill_character_traits.py
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import catalog_import  # noqa: E402
import db  # noqa: E402


def pool_label(is_anime: bool, is_game: bool) -> str:
    """The line Mudae prints under the series, from the roulette booleans."""
    if is_anime and is_game:
        return "Game & Animanga"
    if is_anime:
        return "Animanga"
    if is_game:
        return "Game"
    return ""


def derive(conn):
    """Yield (name, is_female, is_male, pools) for every working row the catalog knows."""
    catalog = {
        row["name_key"]: row
        for row in conn.execute(
            "SELECT name_key, is_waifu, is_husbando, is_anime, is_game FROM character_catalog"
        )
    }
    for row in conn.execute("SELECT name FROM characters ORDER BY name"):
        match = catalog.get(catalog_import.name_key(row["name"]))
        if match is None:
            continue
        yield (
            row["name"],
            bool(match["is_waifu"]),
            bool(match["is_husbando"]),
            pool_label(bool(match["is_anime"]), bool(match["is_game"])),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    print(f"database: {db.database_path()}")
    conn = db.get_connection()
    traits = list(derive(conn))
    matched = len(traits)
    total = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]

    both = sum(1 for _, f, m, _ in traits if f and m)
    female = sum(1 for _, f, m, _ in traits if f and not m)
    male = sum(1 for _, f, m, _ in traits if m and not f)
    print(f"catalog match: {matched} of {total} characters")
    print(f"  female {female}, male {male}, both {both}, ungendered {matched - female - male - both}")

    if args.dry_run:
        for name, is_female, is_male, pools in traits[:15]:
            marks = "".join(c for c, on in (("F", is_female), ("M", is_male)) if on) or "-"
            print(f"  {name}: {marks}  {pools or '(no pool)'}")
        return 0

    changed = db.apply_character_traits(traits)
    print(f"updated {changed} of {matched} matched rows (the rest already agreed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
