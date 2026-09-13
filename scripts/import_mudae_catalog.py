#!/usr/bin/env python3
"""Import one or more Mudae `$wa` / `$ima` extracts into the character catalog.

The same character is captured by many extracts, so the parser merges the whole
input by a Unicode-folded name key before anything is written: duplicates are
dropped, and when two captures disagree the better (lower) rank wins. The
catalog is then upserted, and optionally the existing `characters` rows have
their rank, series and portrait refreshed from it.

Idempotent: re-running the same extracts changes nothing. Nothing is ever
deleted, and a name that only exists in the catalog does not become a working
`characters` row -- that happens when someone saves or customises it.

    # Preview what an import would change. Writes no catalog or character rows.
    uv run python scripts/import_mudae_catalog.py extract_*.txt --dry-run

    # Import the catalog and refresh matching characters' rank/series/portrait.
    uv run python scripts/import_mudae_catalog.py extract_*.txt --batch 2026-09

    # Catalog only, leaving the working characters untouched.
    uv run python scripts/import_mudae_catalog.py extract_*.txt --no-enrich

    # Fill only missing character fields instead of overwriting.
    uv run python scripts/import_mudae_catalog.py extract_*.txt --overwrite empty
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import catalog_import  # noqa: E402  (path is fixed up above)


def _read_sources(paths: list[Path]) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for path in paths:
        # utf-8-sig eats a BOM; errors=replace keeps one bad byte from losing a
        # whole extract. The parser then quarantines whatever does not fit.
        sources.append((str(path), path.read_text(encoding="utf-8-sig", errors="replace")))
    return sources


def _print_parse_summary(result: catalog_import.ParseResult) -> None:
    print(f"extracts:        {len(result.sources)}")
    print(f"lines read:      {result.lines_total}")
    print(f"unique characters: {len(result.characters)}")
    print(f"series:          {len(result.series)}")
    print(f"duplicates merged: {result.duplicates}")
    print(f"conflicts resolved: {result.conflicts}")
    print(f"unparseable lines:  {len(result.issues)}")
    if result.noise:
        print(f"ignored noise lines: {result.noise}")
    for issue in result.issues[:20]:
        print(f"  {issue.source}:{issue.line_no}: {issue.reason}: {issue.text[:90]}")
    if len(result.issues) > 20:
        print(f"  ... and {len(result.issues) - 20} more")


def _print_gaps(ranks: dict, series: dict) -> None:
    print("\nRank coverage (captured rank numbers):")
    print(f"  captured {ranks['captured']}, lowest #{ranks['min']}, highest #{ranks['max']}")
    print(
        f"  missing in range: {ranks['missing']} ({ranks['missing_pct']}% of "
        f"#{ranks['min']}-#{ranks['max']})"
    )
    for row in ranks["coverage"]:
        print(
            f"  ranks 1..{row['ceiling']:<6} {row['captured']:>6} captured"
            f"  {row['missing']:>6} missing  ({row['pct']}%)"
        )
    print("  largest missing rank ranges:")
    for start, end in ranks["largest_ranges"]:
        size = end - start + 1
        label = f"#{start}" if start == end else f"#{start}-#{end}"
        print(f"    {label:<18} {size} missing")
    print(f"  first missing ranks: {ranks['first_missing'][:30]}")

    print("\nSeries coverage (from the listed/total headers):")
    print(
        f"  series {series['series']}, listed {series['listed']}, "
        f"reported total {series['total']}, missing {series['missing']}"
    )
    for row in series["incomplete"][:15]:
        print(f"    {row['missing']:>4} missing  {row['series'][:40]:42} {row['listed']}/{row['total']}")


def _build_report(
    args: argparse.Namespace,
    result: catalog_import.ParseResult,
    enrich: dict | None,
    db_counts: dict | None,
    gaps: dict,
) -> dict:
    report: dict = {
        "batch": args.batch,
        "dry_run": args.dry_run,
        "overwrite": args.overwrite,
        "sources": result.sources,
        "parsed": {
            "lines": result.lines_total,
            "characters": len(result.characters),
            "series": len(result.series),
            "duplicates": result.duplicates,
            "conflicts": result.conflicts,
            "ignored_noise": result.noise,
            "issues": [
                {
                    "source": issue.source,
                    "line": issue.line_no,
                    "reason": issue.reason,
                    "text": issue.text,
                }
                for issue in result.issues
            ],
        },
        "gaps": gaps,
    }
    if db_counts is not None:
        report["catalog"] = db_counts
    if enrich is not None:
        report["enrich"] = enrich
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Mudae $wa/$ima extracts into the character catalog."
    )
    parser.add_argument("sources", nargs="+", type=Path, help="Extract text file(s).")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Database path. Defaults to DATABASE_PATH or data/imgmanager.db.",
    )
    parser.add_argument("--batch", default=None, help="Label recorded on each catalog row.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and preview changes without writing catalog or character rows.",
    )
    parser.add_argument(
        "--no-enrich",
        dest="enrich",
        action="store_false",
        help="Import the catalog only; leave existing characters untouched.",
    )
    parser.add_argument(
        "--overwrite",
        choices=("all", "empty"),
        default="all",
        help="Whether enrichment overwrites existing fields or only fills empty ones.",
    )
    parser.add_argument("--report", type=Path, default=None, help="Write a JSON report here.")
    parser.add_argument(
        "--aliases",
        type=Path,
        default=_REPO_ROOT / "mudae_aliases.json",
        help="Rename/alias map applied during enrichment. Defaults to mudae_aliases.json.",
    )
    args = parser.parse_args()

    missing = [path for path in args.sources if not path.is_file()]
    if missing:
        for path in missing:
            print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    aliases: dict = {}
    if args.aliases.is_file():
        raw = json.loads(args.aliases.read_text(encoding="utf-8"))
        aliases = catalog_import.resolve_aliases(raw)
        print(f"Aliases: {len(aliases)} from {args.aliases}")
    elif args.aliases != _REPO_ROOT / "mudae_aliases.json":
        print(f"error: aliases file not found: {args.aliases}", file=sys.stderr)
        return 2

    result = catalog_import.parse_sources(_read_sources(args.sources))
    print("Parsed")
    _print_parse_summary(result)

    gaps = {
        "ranks": catalog_import.rank_gaps(result),
        "series": catalog_import.series_gaps(result),
    }
    _print_gaps(gaps["ranks"], gaps["series"])

    if not result.characters:
        print("error: no characters parsed; nothing to import", file=sys.stderr)
        return 2

    if args.db is not None:
        os.environ["DATABASE_PATH"] = str(args.db)

    import db as dbm  # imported here so --db is honoured before the connection opens

    scraped_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    overwrite = args.overwrite == "all"

    enrich: dict | None = None
    db_counts: dict | None = None

    if args.dry_run:
        preview = {
            row["name_key"]: {
                "name": row["name"],
                "series": row["series"],
                "rank": row["rank"],
                "mudae_image_url": row["mudae_image_url"],
            }
            for row in dbm.get_catalog_characters()
        }
        # A dry run previews against the union of what is already stored and
        # what this batch would add, so the numbers match a real run.
        preview.update(catalog_import.as_catalog_map(result))
        enrich = dbm.enrich_characters_from_catalog(
            overwrite=overwrite, dry_run=True, catalog=preview, aliases=aliases
        )
        print("\nDry run: no catalog or character rows written.")
    else:
        inserted, updated = dbm.upsert_catalog_characters(
            catalog_import.as_catalog_rows(result),
            scraped_at=scraped_at,
            source_batch=args.batch,
        )
        series_written = dbm.upsert_catalog_series(
            catalog_import.as_series_rows(result), scraped_at=scraped_at
        )
        db_counts = {
            "inserted": inserted,
            "updated": updated,
            "series": series_written,
        }
        print(f"\nCatalog written: {inserted} inserted, {updated} updated, {series_written} series")
        if args.enrich:
            enrich = dbm.enrich_characters_from_catalog(overwrite=overwrite, aliases=aliases)

    if enrich is not None:
        print(
            f"Enrichment: {enrich['matched']} matched, {enrich['updated']} updated,"
            f" {enrich['unchanged']} unchanged, {len(enrich['unmatched'])} unmatched"
        )
        for alias in enrich.get("aliased", []):
            print(f"  alias: {alias['name']} -> catalog {alias['catalog_name']}")
        for rename in enrich.get("renamed", []):
            print(f"  rename: {rename['from']} -> {rename['to']}")
        for conflict in enrich.get("rename_conflicts", []):
            print(f"  rename refused (name taken): {conflict['name']} -> {conflict['to']}")
        for change in enrich["changes"][:10]:
            detail = ", ".join(
                f"{column} {before_after['before']!r} -> {before_after['after']!r}"
                for column, before_after in change["fields"].items()
            )
            print(f"  {change['name']}: {detail}")
        if len(enrich["changes"]) > 10:
            print(f"  ... and {len(enrich['changes']) - 10} more")

    if args.report is not None:
        report = _build_report(args, result, enrich, db_counts, gaps)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
