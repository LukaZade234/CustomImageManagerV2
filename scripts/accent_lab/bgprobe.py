"""Background colour per character, using the pipeline's own cut-out decisions (ACCENT.md §37).

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.bgprobe "Gon Freecss|Lynae"

Per character: how many images separate, are scenes, or miss the character; the
background's top colour families (share of background pixels, colour = S >= 0.12);
and whether those colours are on the character itself.
"""

from __future__ import annotations

import sys

import numpy as np

from . import lab, seg
from . import methods as M

# 30-degree HSV families from -15 degrees; the three green bands are merged
BANDS = ["red", "orange", "yellow", "green", "green", "green", "cyan", "sky blue", "blue", "violet", "magenta", "pink"]  # fmt: skip
FAMILIES = ["red", "orange", "yellow", "green", "cyan", "sky blue", "blue", "violet", "magenta", "pink"]  # fmt: skip
_BAND_TO_FAMILY = np.array([FAMILIES.index(b) for b in BANDS])


def _family(h):
    return _BAND_TO_FAMILY[((h + 15) % 360 // 30).astype(int)]


def probe(name: str) -> None:
    _, _, gallery = lab.load_character(f"live:{name}", None)
    bg_shares, fg_shares = [], []
    kinds = {"separated": 0, "scene": 0, "character missed": 0}
    for im in gallery:
        full = M._full_res(im.info["src"])
        a = np.asarray(full, np.float64).reshape(-1, 3) / 255
        m = (seg.mask_for(full) >= M.FG_THRESHOLD).reshape(-1)
        share = m.mean()
        kind = (
            "character missed"
            if share < M.MIN_FG_SHARE
            else "scene"
            if share > M.MAX_FG
            else "separated"
        )
        kinds[kind] += 1
        mx, mn = a.max(1), a.min(1)
        d = np.maximum(mx - mn, 1e-9)
        r, g, b = a.T
        h = (
            np.where(
                mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)
            )
            * 60
        )
        s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
        colour = (s >= 0.12) & (mx >= 0.15)
        bg = ~m if kind == "separated" else np.ones_like(m)
        fg = m if kind == "separated" else np.zeros_like(m)
        n = len(FAMILIES)
        bg_shares.append(np.bincount(_family(h[bg & colour]), minlength=n) / max(bg.sum(), 1))
        fg_shares.append(
            np.bincount(_family(h[fg & colour]), minlength=n) / fg.sum()
            if fg.sum()
            else np.full(n, np.nan)
        )
    bgs, fgs = np.array(bg_shares), np.array(fg_shares)
    top = np.argsort(bgs.mean(0))[::-1][:3]
    counts = ", ".join(f"{v} {k}" for k, v in kinds.items() if v)
    print(f"\n{name}: {len(gallery)} images ({counts})")
    print(
        "  background colour, mean share of background: "
        + ", ".join(f"{FAMILIES[i]} {bgs.mean(0)[i]:.0%}" for i in top)
        + f" | no colour {1 - bgs.sum(1).mean():.0%}"
    )
    for i in top[:2]:
        separated = int((~np.isnan(fgs[:, i])).sum())
        print(
            f"   {FAMILIES[i]:9s} tops the background in {(bgs.argmax(1) == i).mean():.0%} of images;"
            f" on the character {np.nanmean(fgs[:, i]):.1%} of the cut-out,"
            f" in {(fgs[:, i] >= 0.02).sum()} of {separated} separated images"
        )


if __name__ == "__main__":
    for character in sys.argv[1].split("|"):
        probe(character)
