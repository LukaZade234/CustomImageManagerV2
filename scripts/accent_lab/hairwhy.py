"""Why a character's hair did not win (ACCENT.md §36): replay V40's classifier on parsed hair.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.hairwhy "Shouko Nishimiya|Vertin"

For each character: how much of the cut-out the face parser calls hair, the hair's median
HSV, what V40's rules do to those pixels (removed as skin, too grey or dark to vote, full,
damped or half vote), and the hair's share of each image's colour vote.
"""

import sys

import numpy as np
from PIL import Image

from . import faceparse as FP
from . import lab
from . import methods as M

A = M.A
captured = {}
_orig = M.classify_np


def spy(img, **kw):
    if kw.get("warm_white") is not None and "kw" not in captured:  # the hue measure
        captured["kw"] = kw
        captured["LIGHT_LO"] = M.LIGHT_LO
        captured["WARM_DARK_V"] = M.WARM_DARK_V
        captured["SKIN_HUE"] = A.SKIN_HUE
    return _orig(img, **kw)


M.classify_np = spy


def fates(img, kw):
    """Per pixel: fate code, vote weight, HSV hue. Mirrors classify_np."""
    a, h, s, v, d, L, C, oh = M._pixels(img)
    fate = np.full(len(h), "", object)
    white = np.all(a >= 0.999, axis=1)
    fate[white] = "bg"
    rest = ~white
    dark = rest & (v < 0.15)
    fate[dark] = "too dark"
    rest &= ~dark
    nw = rest & (v >= 0.95) & (s <= 0.15)
    fate[nw] = "near-white"
    rest &= ~nw
    lo, hi = kw.get("skin_hue") or captured["SKIN_HUE"]
    sk = rest & (h >= lo) & (h <= hi) & (s >= 0.12) & (s <= 0.55) & (v >= kw.get("skin_val", 0.6))
    fate[sk] = "skin-hue rule"
    rest &= ~sk
    if kw.get("skin") is not None:
        ps = np.fromiter(
            (kw["skin"](a_, b_, c_) for a_, b_, c_ in zip(h, s, v, strict=True)), bool, len(h)
        )
        ps &= rest & (s >= A.PALE_SAT_MIN)
        fate[ps] = "pale-skin rule"
        rest &= ~ps

    def zone(z0, z1):
        return (h >= z0) & (h <= z1) if z0 <= z1 else (h >= z0) | (h <= z1)

    sat = rest & (s >= A.SATURATED_SAT_MIN)
    pale = rest & ~sat & (s >= A.PALE_SAT_MIN) & (v >= A.PALE_VAL_MIN)
    grey = rest & ~sat & ~pale
    fate[grey] = "grey"
    w = np.zeros(len(h))
    lo_, b_ = captured["LIGHT_LO"]
    lp = np.clip((v - lo_) / b_, 0, 1) * np.clip((0.97 - v) / 0.07, 0, 1)
    w_sat = s**1.6 * lp
    damped = np.zeros(len(h), bool)
    wd = kw.get("warm_damp")
    if wd:
        wz = zone(wd[0], wd[1])
        dmp = wz & ((s <= wd[2]) | (v < captured["WARM_DARK_V"]))
        w_sat = np.where(dmp, w_sat * wd[3], w_sat)
        damped |= dmp & sat
    wl = kw.get("warm_damp_light")
    if wl:
        lz = zone(wl[0], wl[1]) & (s <= wl[2])
        w_sat = np.where(lz, w_sat * wl[3], w_sat)
        damped |= lz & sat
    ww = kw.get("warm_white")
    if ww:
        wwm = pale & zone(ww[0], ww[1]) & (s < ww[2])
        fate[wwm] = "warm-white rule"
        pale &= ~wwm
    w_pale = s * A.PALE_VOTE_WEIGHT
    if wd:
        w_pale = np.where(zone(wd[0], wd[1]), w_pale * wd[3], w_pale)
    fate[sat] = np.where(damped[sat], "saturated (damped 1/4)", "saturated")
    fate[pale] = "pale (half vote)"
    w[sat] = w_sat[sat]
    w[pale] = w_pale[pale]
    return fate, w, h, s, v


def analyse(name):
    captured.clear()
    _, p, g = lab.load_character(f"live:{name}", None)
    tr = []
    r = M.v40(p, g, tr)
    kw = captured["kw"]
    n_img = n_hair_img = 0
    fate_tot: dict = {}
    hair_px = fg_px = 0
    shares, hue_w = [], np.zeros(72)
    hs, ss, vs = [], [], []
    saved = (M.FACE_SKIN_OUT, M.HAIR_BOOST)
    M.FACE_SKIN_OUT, M.HAIR_BOOST = False, 0
    try:
        for im in g:
            fg = M.foreground_only(im)
            if M.fg_share(fg) > M.MAX_FG:
                continue
            n_img += 1
            src = im.info.get("src")
            labs, _ = FP.labels_and_faces(M._full_res(src))
            labs = np.asarray(Image.fromarray(labs).resize(fg.size, Image.NEAREST)).reshape(-1)
            fate, w, h, s, v = fates(fg, kw)
            keep = fate != "bg"
            hair = keep & (labs == FP.HAIR)
            fg_px += keep.sum()
            hair_px += hair.sum()
            if hair.sum() < 20:
                continue
            n_hair_img += 1
            for f in fate[hair]:
                fate_tot[f] = fate_tot.get(f, 0) + 1
            tw = w[keep].sum()
            shares.append(w[hair].sum() / tw if tw > 0 else 0)
            hue_w += np.bincount(
                np.minimum((h[hair] / 5).astype(int), 71), weights=w[hair], minlength=72
            )
            hs.append(np.median(h[hair]))
            ss.append(np.median(s[hair]))
            vs.append(np.median(v[hair]))
    finally:
        M.FACE_SKIN_OUT, M.HAIR_BOOST = saved
    tot = sum(fate_tot.values()) or 1
    print(f"\n== {name}: V40 {r['seed'] if r else None}")
    print(f"   {tr[0][:230] if tr else ''}")
    print(
        f"   hair found in {n_hair_img} of {n_img} usable images; hair = {hair_px / max(1, fg_px):.0%} of cut-out pixels"
    )
    if hs:
        print(
            f"   hair median HSV: h {np.median(hs):.0f}  s {np.median(ss):.2f}  v {np.median(vs):.2f}"
        )
        print(
            "   what happens to hair pixels: "
            + ", ".join(
                f"{k} {c / tot:.0%}" for k, c in sorted(fate_tot.items(), key=lambda x: -x[1])
            )
        )
        print(f"   hair's share of each image's colour vote (median): {np.median(shares):.0%}")
        top = np.argsort(hue_w)[::-1][:3]
        print(
            "   hair's vote goes to HSV hue: "
            + ", ".join(
                f"{(i + 0.5) * 5:.0f}deg {hue_w[i] / max(hue_w.sum(), 1e-9):.0%}" for i in top
            )
        )


if __name__ == "__main__":
    for n in sys.argv[1].split("|"):
        analyse(n)
