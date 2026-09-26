"""Run extractor variants over the calibration panel, side by side.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.panel current,v8,v12
    ... panel current,v12 --all        # every image instead of the 60-image sample

Names are `current` (shipped) or any `method_<name>` in methods.py. `mcu` also
needs `--with materialyoucolor`. Live panel entries need `fetch_live` first and
are skipped with a note when absent.
"""

from __future__ import annotations

import argparse

from . import lab, methods


def resolve(name):
    return lab.method_current if name == "current" else getattr(methods, f"method_{name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("methods", help="comma-separated, e.g. current,v8,v12")
    parser.add_argument("--all", action="store_true", help="measure every image")
    parser.add_argument("--review", action="store_true", help="use the owner's review set")
    parser.add_argument("--sample-review", action="store_true", help="the random-sample review")
    args = parser.parse_args()
    fns = [(m, resolve(m)) for m in args.methods.split(",")]
    panel = lab.REVIEW if args.review else lab.PANEL
    if args.sample_review:
        panel = lab.SAMPLE_REVIEW
    for cid, (label, ok) in panel.items():
        try:
            name, portrait, gallery = lab.load_character(cid, None if args.all else 60)
        except FileNotFoundError:
            print(f"{label[:30]:30s} (not fetched: run fetch_live)")
            continue
        cells = []
        for m, fn in fns:
            r = fn(portrait, gallery)
            cells.append(f"{m}:{'ok ' if ok(r) else 'BAD'} {lab.fmt(r)}")
        print(f"{label[:30]:30s} {len(gallery):3d} ", " | ".join(cells), flush=True)


if __name__ == "__main__":
    main()
