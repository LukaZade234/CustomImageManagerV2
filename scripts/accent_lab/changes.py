"""Characters whose accent visibly changed between two full runs.

    uv run python -m scripts.accent_lab.changes full_v40 full_v43 [0.08]

Compares the per-character results `fullcheck compute` wrote to two folders under
.data by Oklab distance; 0.08 is the "visibly changed" threshold the doc's counts use
(an invisible hex step changes most characters).
"""

from __future__ import annotations

import json
import sys

from . import lab
from .fullcheck import _oklab


def main(a: str, b: str, threshold: float = 0.08) -> None:
    rows = []
    old_dir, new_dir = lab.DATA / a, lab.DATA / b
    files = sorted(old_dir.glob("*.json"))
    for f in files:
        other = new_dir / f.name
        if not other.is_file():
            continue
        x, y = json.loads(f.read_text()), json.loads(other.read_text())
        if not x.get("seed") or not y.get("seed"):
            if x.get("seed") != y.get("seed"):
                rows.append((9.0, x["name"], x["count"], x.get("seed"), y.get("seed")))
            continue
        d = sum((p - q) ** 2 for p, q in zip(_oklab(x["seed"]), _oklab(y["seed"]), strict=True))
        if d**0.5 >= threshold:
            rows.append((d**0.5, x["name"], x["count"], x["seed"], y["seed"]))
    print(f"{len(rows)} of {len(files)} visibly changed (Oklab >= {threshold})")
    for d, name, count, s1, s2 in sorted(rows, reverse=True):
        print(f"  {d:.2f} {name[:28]:28s} {count:4d}  {s1} -> {s2}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.08)
