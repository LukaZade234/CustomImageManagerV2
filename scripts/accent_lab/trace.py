"""Why a version picks what it picks, for named live characters.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.trace v37 "Reze|Kyouka Jirou"

Prints the seed and the decision trace: which path (standard, monochrome,
pale-pink), clear winner or tie (and how the main image scored the candidates),
which hue the aim settled on, whether it was shaded from pale or saturated
pixels, and any fallback or safety net used.
"""

from __future__ import annotations

import sys

from . import lab
from . import methods as M


def main() -> None:
    version, names = sys.argv[1], sys.argv[2].split("|")
    fn = getattr(M, version)
    for n in names:
        _, p, g = lab.load_character(f"live:{n}", None)
        tr: list[str] = []
        r = fn(p, g, tr)
        print(f"{n[:24]:24s} {lab.fmt(r)[:30]}  {tr[0] if tr else ''}", flush=True)


if __name__ == "__main__":
    main()
