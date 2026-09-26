"""Trace one character through the V12 pipeline and say why it lands where it does.

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.explain "live:Himeno"

Prints, for the segmented gallery and the portrait (whole and segmented): the
top hue families, the smoothed peak with its margin and band confidence, the
candidates, coverage, the pale-identity decision, and the reason for a decline.
"""

from __future__ import annotations

import sys

from . import lab
from . import methods as M

A = M.A
FAMILIES = [
    ("red", 345, 15), ("orange", 15, 40), ("yellow", 40, 70), ("green", 70, 150),
    ("teal", 150, 185), ("cyan", 185, 205), ("blue", 205, 240), ("violet", 240, 285),
    ("magenta", 285, 345),
]  # fmt: skip


def families(hist):
    total = sum(hist) or 1.0
    out = []
    for name, lo, hi in FAMILIES:
        s = 0.0
        for i in range(A.HUE_BINS):
            d = (i + 0.5) * 5
            if (lo <= d < hi) if lo < hi else (d >= lo or d < hi):
                s += hist[i]
        out.append((name, s / total))
    return " ".join(f"{n} {s:.0%}" for n, s in sorted(out, key=lambda t: -t[1]) if s >= 0.03)


def peaks(hist, k=4):
    smooth, total = A._smooth(hist)
    if total <= 0:
        return "-"
    order = sorted(range(A.HUE_BINS), key=lambda i: -smooth[i])
    picked: list[int] = []
    for i in order:
        if all(A._hue_distance((i + 0.5) * 5, (j + 0.5) * 5) >= 30 for j in picked):
            picked.append(i)
        if len(picked) == k:
            break
    return ", ".join(f"{(i + 0.5) * 5:.0f}deg {smooth[i] / smooth[order[0]]:.2f}" for i in picked)


def section(label, grids):
    entries = [(g, 1.0) for g in grids]
    sat = A._pool_histogram(entries, "saturated")
    pale = A._pool_histogram(entries, "pale")
    print(f"  {label}: {len(grids)} measured image(s)")
    print(f"    saturated families: {families(sat)}")
    print(f"    saturated peaks (HSV, relative): {peaks(sat)}")
    print(f"    pale families:      {families(pale)}")
    win = M.peak_winner(sat, M.V8)
    smooth, total = A._smooth(sat)
    if total > 0:
        top = max(range(A.HUE_BINS), key=lambda i: smooth[i])
        wd = (top + 0.5) * 5
        rival = max(
            (smooth[i] for i in range(A.HUE_BINS) if A._hue_distance((i + 0.5) * 5, wd) >= 60),
            default=0,
        )
        share = M.band_sum(sat, wd, 22.5) / sum(sat)
        margin = smooth[top] / rival if rival else float("inf")
        print(
            f"    peak {wd:.1f}  margin {margin:.2f} (need {A.MIN_MARGIN})"
            f"  band share {share:.2f} (need {M.V8['min_share']})"
        )
        if win is None:
            why = "margin (two-colour)" if margin < A.MIN_MARGIN else "band share too low"
            print(f"    -> saturated pool DECLINES: {why}")
        else:
            conf = win[2]
            hue = win[0]
            cov = sum(M.band_sum(g.hist_cov, hue, 22.5) for g in grids) / max(1, len(grids))
            pale_win = A._dominant_hue(pale, A.MIN_CONFIDENCE, True)
            pale_id = M._pale_identity(entries, hue, conf, pale_win)
            print(
                f"    coverage {cov:.3f} (need {M.V8['min_cov']})  single-bin conf {conf:.3f}"
                f"  pale identity: {pale_id}"
            )
            print(f"    candidates: {[round(c) for c in M.candidates(sat)]}")
    return sat


def main() -> None:
    cid = sys.argv[1]
    cid = int(cid) if cid.isdigit() else cid
    name, portrait, gallery = lab.load_character(cid, None)
    print(f"{name}: {len(gallery)} gallery images, portrait {'yes' if portrait else 'NO'}")
    fp, fg = M._segmented(portrait, gallery, drop_scenes=True)
    print(
        f"  segmentation kept {len(fg)} of {len(gallery)} images (others were unseparable scenes)"
    )
    gm = [x for x in (M.measure(i, M._no_pale_skin) for i in fg) if x is not None]
    section("gallery (segmented)", gm)
    if portrait is not None:
        whole = M.measure(portrait, M._no_pale_skin)
        seg = M.measure(fp, M._no_pale_skin)
        section("portrait, whole", [whole] if whole else [])
        section("portrait, segmented", [seg] if seg else [])
    for m in ("current", "v8", "v12"):
        fn = lab.method_current if m == "current" else getattr(M, f"method_{m}")
        print(f"  {m:8s} -> {lab.fmt(fn(portrait, gallery))}")


if __name__ == "__main__":
    main()
