#!/usr/bin/env python3
"""
One-time migration: copy JSON backups into PostgreSQL (kv_store).

Requires DATABASE_URL. Point --dir or individual paths at a folder containing
backup copies of the old files (or pass each file path).

Example (from repository root):
  DATABASE_URL=postgresql://... python scripts/migrate_to_db.py --dir ./backup_from_git
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import db  # noqa: E402

DEFAULT_NAMES = [
    ('custom_images', 'custom_images.json'),
    ('saved_characters', 'saved_characters.json'),
    ('last_updated', 'last_updated.json'),
]


def main():
    p = argparse.ArgumentParser(description='Migrate JSON backup files into PostgreSQL.')
    p.add_argument(
        '--dir',
        default='.',
        help='Directory to look for default filenames (default: current directory)',
    )
    args = p.parse_args()
    base = os.path.abspath(args.dir)

    if not os.environ.get('DATABASE_URL'):
        print('Set DATABASE_URL to your PostgreSQL connection string.', file=sys.stderr)
        return 1

    for name, filename in DEFAULT_NAMES:
        path = os.path.join(base, filename)
        if not os.path.exists(path):
            print(f'Skip {path} (not found)')
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f'Error reading {path}: {e}')
            continue

        getter = getattr(db, f'get_{name}')
        existing = getter()
        if existing and name == 'custom_images' and isinstance(existing, dict) and len(existing) > 0:
            print(f'Skip {path} (db already has data)')
            continue
        if existing and name == 'saved_characters' and len(existing) > 0:
            print(f'Skip {path} (db already has data)')
            continue
        if existing and name == 'last_updated' and len(existing) > 0:
            print(f'Skip {path} (db already has data)')
            continue

        getattr(db, f'set_{name}')(data)
        print(f'Migrated {path} -> database')
    return 0


if __name__ == '__main__':
    exit(main())
