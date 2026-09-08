#!/usr/bin/env python3
"""
One-time import: CSV + optional mapping JSON into PostgreSQL characters kv_store.

Requires DATABASE_URL. Paths are required (no bundled CharName.csv in repo).

Example (from repository root):
  DATABASE_URL=postgresql://... python scripts/import_characters_to_db.py \\
    --csv /path/to/CharName.csv --mapping /path/to/character_image_mapping.json
"""
import argparse
import csv
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import db  # noqa: E402


def main():
    p = argparse.ArgumentParser(description='Import characters from CSV + mapping JSON into DB.')
    p.add_argument('--csv', required=True, help='Path to CharName.csv (or equivalent)')
    p.add_argument('--mapping', default='', help='Path to character_image_mapping.json (optional)')
    args = p.parse_args()

    if not os.environ.get('DATABASE_URL'):
        print('Set DATABASE_URL to your PostgreSQL connection string.', file=sys.stderr)
        return 1

    csv_path = os.path.abspath(args.csv)
    if not os.path.isfile(csv_path):
        print(f'CSV not found: {csv_path}', file=sys.stderr)
        return 1

    mapping = {}
    if args.mapping:
        mp = os.path.abspath(args.mapping)
        if os.path.isfile(mp):
            try:
                with open(mp, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
            except Exception as e:
                print(f'Error reading mapping: {e}', file=sys.stderr)

    existing = db.get_characters()
    if existing is not None and len(existing) > 0:
        print("Characters already in DB, skipping import. Clear 'characters' in kv_store to re-import.")
        return 0

    chars = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('name', '')
            if not name:
                continue
            img = mapping.get(name, {}).get('filename', '')
            chars.append({
                'name': name,
                'series': row.get('series', ''),
                'rank': row.get('rank', ''),
                'main_image_url': img,
            })

    db._set_characters_raw(chars)
    print(f'Imported {len(chars)} characters into DB')
    return 0


if __name__ == '__main__':
    exit(main())
