"""Run variants over every local character with >= 6 cached thumbnails and
summarise how the seeds move: chroma, lightness, declines, hue shifts.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.library current,v8,v12 --all

Segmenting variants take a while the first time (masks are then cached).
Results go to `.data/library.json` for `sheet.py`.
"""

from __future__ import annotations

import argparse
import json
import statistics

from . import lab
from .panel import resolve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("methods")
    parser.add_argument("--all", action="store_true", help="measure every image")
    parser.add_argument("--live", nargs="*", default=[], help="also include fetched live names")
    parser.add_argument(
        "--live-only", action="store_true", help="every fetched live character, no local ones"
    )
    args = parser.parse_args()
    names = args.methods.split(",")
    fns = {m: resolve(m) for m in names}
    rows = []
    if args.live_only:
        ids = [f"live:{n}" for n in lab.live_names()]
    else:
        ids = lab.library_ids(6) + [f"live:{n}" for n in args.live]
    for cid in ids:
        name, portrait, gallery = lab.load_character(cid, None if args.all else 60)
        row = {"id": cid, "name": name, "n": len(gallery)}
        for m, fn in fns.items():
            row[m] = fn(portrait, gallery)
        rows.append(row)
        print(name, len(gallery), *(row[m]["seed"] if row[m] else "-" for m in names), flush=True)
    lab.DATA.mkdir(parents=True, exist_ok=True)
    (lab.DATA / "library.json").write_text(json.dumps(rows, indent=1, default=float))

    print(f"\n{len(rows)} characters")
    for m in names:
        seeded = [r[m] for r in rows if r[m]]
        print(
            f"{m:8s} seeded {len(seeded):3d}"
            f"  median C {statistics.median(s['chroma'] for s in seeded):.3f}"
            f"  median L {statistics.median(s['lightness'] for s in seeded):.2f}"
            f"  dark(L<0.45) {sum(s['lightness'] < 0.45 for s in seeded):3d}"
            f"  grey(C<0.05) {sum(s['chroma'] < 0.05 for s in seeded):3d}"
        )
    base = names[0]
    for m in names[1:]:
        moved = [
            (r["name"], r[base]["seed"], r[m]["seed"])
            for r in rows
            if r[base] and r[m] and lab.hue_gap(r[base]["hue"], r[m]["hue"]) > 30
        ]
        print(f"\n{base} -> {m}: hue moved >30 deg: {moved}")
        print("  seeded -> declined:", [r["name"] for r in rows if r[base] and not r[m]])
        print("  declined -> seeded:", [r["name"] for r in rows if not r[base] and r[m]])


if __name__ == "__main__":
    main()
