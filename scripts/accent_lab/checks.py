"""Score extractor versions against every review verdict the owner has given.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.checks v36,v37
    ... checks v37 --only FULL_REVIEW,V36_REVIEW        # a subset of the review sets
    ... checks v37 --bad                               # print only the failures

The verdicts are the dictionaries in lab.py -- PANEL (the original calibration
panel, local ids), REVIEW (first two rounds), SAMPLE_REVIEW (the random sample),
PROFILE_REVIEW (the colour-profile paths), FULL_REVIEW (the full 4+ check) and
V36_REVIEW. By default every live set is used (PANEL needs the local library).
Each version is any `method_<name>` / `<name>(portrait, gallery, trace)` in
methods.py, or `current` for the shipped extractor.
"""

from __future__ import annotations

import argparse

from . import lab
from . import methods as M

SETS = ["SAMPLE_REVIEW", "REVIEW", "PROFILE_REVIEW", "FULL_REVIEW", "V36_REVIEW"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("versions", help="comma-separated, e.g. v36,v37")
    parser.add_argument("--only", default="", help="comma-separated review sets from lab.py")
    parser.add_argument("--bad", action="store_true", help="print only rows with a failure")
    args = parser.parse_args()
    versions = args.versions.split(",")
    sets = args.only.split(",") if args.only else SETS
    checks: dict = {}
    for name in sets:
        checks.update(getattr(lab, name))  # later sets override earlier verdicts
    fns = {v: (lab.method_current if v == "current" else getattr(M, v)) for v in versions}
    score = dict.fromkeys(versions, 0)
    for cid, (label, ok) in checks.items():
        try:
            _, p, g = lab.load_character(cid, None)
        except FileNotFoundError:
            print(f"{label[:34]:34s} (not fetched)")
            continue
        cells, bad = [], False
        for v, fn in fns.items():
            r = fn(p, g)
            good = bool(ok(r))
            score[v] += good
            bad |= not good
            cells.append(f"{v}:{'ok ' if good else 'BAD'} {(r or {}).get('seed', 'None   ')}")
        if bad or not args.bad:
            print(f"{label[:34]:34s}", " | ".join(cells), flush=True)
    print(" | ".join(f"{v}: {s} of {len(checks)}" for v, s in score.items()))


if __name__ == "__main__":
    main()
