#!/usr/bin/env python3
"""Take a READ-ONLY snapshot of the live database into local JSON files.

The v1 site is still serving users from this database. This script only ever
runs SELECT, and opens the connection in read-only mode so the server itself
rejects any write. Run it once; everything afterwards works from the snapshot.

Usage, from the repository root:

    uv run python scripts/export_neon_snapshot.py                 # uses DATABASE_URL from .env
    uv run python scripts/export_neon_snapshot.py --out snapshot  # choose the directory
"""

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

KEYS = ("characters", "custom_images", "saved_characters", "last_updated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="database URL (default: $DATABASE_URL)")
    parser.add_argument("--out", default="snapshot", help="output directory (default: snapshot)")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO_ROOT / ".env")
    except ImportError:
        pass

    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set and --url was not given.", file=sys.stderr)
        return 2
    if url.startswith("postgres://"):
        url = "postgresql://" + url[11:]

    import psycopg

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # read_only is enforced by the server: any INSERT/UPDATE/DELETE errors out.
    with psycopg.connect(url, autocommit=False) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT key FROM kv_store ORDER BY key")
            present = [row[0] for row in cur.fetchall()]
            print(f"keys present in kv_store: {present}\n")

            total_bytes = 0
            for key in KEYS:
                cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
                row = cur.fetchone()
                if row is None:
                    print(f"  {key:<18} MISSING")
                    continue
                value = row[0]
                text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                path = out / f"{key}.json"
                path.write_text(text, encoding="utf-8")
                total_bytes += len(text.encode("utf-8"))

                if isinstance(value, dict):
                    shape = f"{len(value)} keys"
                    if key == "custom_images":
                        images = sum(len(v or []) for v in value.values())
                        non_empty = sum(1 for v in value.values() if v)
                        shape += f", {images} images across {non_empty} characters"
                elif isinstance(value, list):
                    shape = f"{len(value)} entries"
                else:
                    shape = type(value).__name__
                print(f"  {key:<18} {shape:<52} -> {path}")

    print(f"\nsnapshot written to {out.resolve()}  ({total_bytes / 1024:.1f} KiB of JSON)")
    print("Nothing was modified: the connection was opened read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
