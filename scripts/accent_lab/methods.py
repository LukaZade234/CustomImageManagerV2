"""Every extractor variant tried in docs/ACCENT.md sections 14-18.

Each `method_<name>(portrait, gallery)` takes the images `lab.load_character`
returns and gives `lab.describe(seed)` or None. Names match the doc's tables.
Only `method_current` (in lab.py) is what ships; nothing here is wired into the
app. Variants build on each other, so read them in order.

    mcu   Material Color Utilities' quantiser + Score, pooled.    dead end
    v5    band-share winner and confidence, vivid core            Reze -> pink
    v6    peak location, band confidence, HSV-ranked core         darker seeds
    v7    one continuous OKLCH chroma weight, presence pooling    Lynae declines
    v8    shipped classes + band confidence + vivid core          the base
    v9    v8 + classifier-gap pixels vote                         no gain
    v10   v8 on the segmented foreground                          Lynae -> cyan
    v11   v10 + pale skin rejected                                fixes the leak
    v11d  v11 + drop scenes the mask cannot separate              Lynae #34b0c1
    v12   v11d + portrait breaks ties between gallery candidates  Reze -> navy
    v13   pale votes on hue, 30-degree candidates, whole main
          image breaks ties, main-image fallback                  skin floods pale
    v14   valley clusters, skin rule through orange               clusters too wide
    v15   skin stops at 38 (blonde survives), pale-vs-saturated
          shade choice, agreed aim, presence pooling option       Panty yellow
    v16   fixed +-30 degree colour windows                        19/23 of review
    v17   v16 tuned + chroma floor for tinted pale identities     21/23
    v18   aim within +-15; a tie with no main image takes a side  21/23; gold drift
    v19   v18 + shaded skin removed from the saturated class      no gain
    v20   v18 + skin-tone zone damped to 1/4 (not dropped)        Ishtar red
    v21   v20 + peak-centred windows + warm whites dropped        split: see below
    v22   v20 + warm whites dropped, aim across the window        25/26; Lynae pale
    v23   v22 + whites muted (not dropped), aim by sub-colour     worse
    v24   v22's hue, v20's shade (whites only vote on the hue)    25/26
    v25   skin zone wraps down through red (with the dark rule)   broke approved reds
    v26   pale-skin rule starts at 352 (pale pink is not skin)    broke Panty, Shiki
    v27   v26 + skin shadow damped + shade blended to bright half 39-41/49
    v28   v24's classes + v27's blend + skin-shadow damping       43/49
    v29   v28 + pale pink counts once stronger than a highlight   43/49
    v30   colour-profile paths: monochrome and pale pink          46/49
    v31   mono picks a side, tints only as far as the greys lean,
          takes a strong highlight; pale pink must be present     fixes 4 false pinks
    v32   v31 + each pink shaded from its own lighter pinks       47/49
    v33   dark-side mono back to a tinted mid tone; highlight
          must recur in 3 images; tie candidates need real colour 56/59, the candidate
"""

from __future__ import annotations

import colorsys
import math

import numpy as np
from PIL import Image

from . import seg
from .lab import A, describe, portrait_schedule

# ---- shared measurement helpers -------------------------------------------------


class Grids:
    """Shipped per-image grids plus how much of the frame each hue covers."""

    __slots__ = ("saturated", "pale", "sat_cov", "hist_cov")

    def __init__(self, saturated, pale, sat_cov, hist_cov):
        self.saturated = saturated
        self.pale = pale
        self.sat_cov = sat_cov  # share of all pixels in the saturated class
        self.hist_cov = hist_cov  # hue bin -> share of all pixels (saturated class)


_cache: dict = {}


def measure(img, measure_image=None):
    """`accent_extract.measure_image` plus pixel coverage, cached per image."""
    measure_image = measure_image or A.measure_image
    key = (id(img), measure_image)
    hit = _cache.get(key)
    if hit and hit[0] is img:
        return hit[1]
    base = measure_image(img)
    result = None
    if base is not None:
        total = 0
        cov = [0] * A.HUE_BINS
        for r8, g8, b8 in img.getdata():
            total += 1
            h, s, v = colorsys.rgb_to_hsv(r8 / 255, g8 / 255, b8 / 255)
            if v < 0.15 or s < A.SATURATED_SAT_MIN or (r8, g8, b8) == (255, 255, 255):
                continue
            hue = h * 360
            if A.SKIN_HUE[0] <= hue <= A.SKIN_HUE[1] and s <= 0.55 and v >= 0.6:
                continue
            cov[min(A.HUE_BINS - 1, int(hue / 360 * A.HUE_BINS))] += 1
        hist_cov = [c / total for c in cov]
        result = Grids(base.saturated, base.pale, sum(hist_cov), hist_cov)
    _cache[key] = (img, result)
    return result


def band_sum(hist, centre, span):
    return sum(hist[i] for i in range(A.HUE_BINS) if A._hue_distance((i + 0.5) * 5, centre) <= span)


def oklab_to_hex(L, a, b):
    lc = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    mc = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    sc = (L - 0.0894841775 * a - 1.291485548 * b) ** 3

    def enc(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    rgb = (
        enc(4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc),
        enc(-1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc),
        enc(-0.0041960863 * lc - 0.7034186147 * mc + 1.707614701 * sc),
    )
    return "#" + "".join(f"{round(x * 255):02x}" for x in rgb)


def fit_in_gamut(L, C, hue):
    """Hex for OKLCH (L, C, hue), shedding chroma -- never hue -- until it fits."""
    while C > 0.005:
        hx = oklab_to_hex(L, C * math.cos(math.radians(hue)), C * math.sin(math.radians(hue)))
        r, g, b = (int(hx[i : i + 2], 16) / 255 for i in (1, 3, 5))
        if abs(A.rgb_to_oklch(r, g, b)[1] - C) < 0.008:
            return hx
        C *= 0.97
    return oklab_to_hex(L, 0, 0)


def pale_seed(entries, hue):
    rep = A._representative(
        A._merged_band_grid(entries, hue, A.BAND_SPAN, "pale"), hue, A.BAND_SPAN
    )
    r = A._seed_from_representative(rep) if rep else None
    return r["seed"] if r else None


# ---- MCU ------------------------------------------------------------------------


def method_mcu(portrait, gallery):
    from materialyoucolor.quantize import QuantizeCelebi
    from materialyoucolor.score.score import Score, ScoreOptions

    def quantize(img):
        q = QuantizeCelebi([[r, g, b, 255] for r, g, b in img.getdata()], 128)
        tot = sum(q.values())
        return {c: n / tot for c, n in q.items()}

    def pick(entries):
        pool: dict[int, float] = {}
        wsum = sum(w for _, w in entries)
        for img, w in entries:
            for c, s in quantize(img).items():
                pool[c] = pool.get(c, 0.0) + s * w / wsum
        fallback = 0xFF000001
        out = Score.score(
            {c: max(1, int(v * 1e6)) for c, v in pool.items()},
            ScoreOptions(desired=1, fallback_color_argb=fallback, filter=True),
        )
        if not out or out[0] == fallback:
            return None
        return describe(f"#{out[0] & 0xFFFFFF:06x}")

    return portrait_schedule(pick, portrait, gallery)


# ---- V5: band-share winner ----------------------------------------------------------

V5 = {"span": 22.5, "min_share": 0.2, "min_margin": 1.25, "core": 0.35, "min_cov": 0.03}


def _band_winner(hist, p):
    total = sum(hist)
    if total <= 0:
        return None
    smooth, _ = A._smooth(hist)
    bands = [band_sum(hist, (i + 0.5) * 5, p["span"]) for i in range(A.HUE_BINS)]
    win = max(range(A.HUE_BINS), key=lambda i: (bands[i], smooth[i]))
    share = bands[win] / total
    if share < p["min_share"]:
        return None
    wd = (win + 0.5) * 5
    rival = max(
        (
            bands[i]
            for i in range(A.HUE_BINS)
            if A._hue_distance((i + 0.5) * 5, wd) >= 2 * p["span"] + 15
        ),
        default=0,
    )
    if rival > 0 and bands[win] / rival < p["min_margin"]:
        return None
    return wd, share


def _v5_vivid(grid, centre, span, core):
    cells = []
    for (hb, sb, vb), w in grid.items():
        hue = (hb + 0.5) * 5
        if A._hue_distance(hue, centre) > span:
            continue
        s, v = (sb + 0.5) / A.SAT_STEPS, (vb + 0.5) / A.VAL_STEPS
        L, C, h = A.rgb_to_oklch(*colorsys.hsv_to_rgb(hue / 360, s, v))
        cells.append((C, L, h, w))
    if not cells:
        return None
    total = sum(c[3] for c in cells)
    cells.sort(key=lambda c: -c[0])
    picked, run = [], 0.0
    for c in cells:
        picked.append(c)
        run += c[3]
        if run >= total * core:
            break
    la = aa = bb = ww = 0.0
    for C, L, h, w in picked:
        w *= 1.0 if 0.5 <= L <= 0.85 else 0.35
        la += L * w
        aa += C * math.cos(math.radians(h)) * w
        bb += C * math.sin(math.radians(h)) * w
        ww += w
    return oklab_to_hex(la / ww, aa / ww, bb / ww)


def _v5_decide_from(entries, p=V5):
    if not entries:
        return None
    sat_hist = A._pool_histogram(entries, "saturated")
    pale_win = A._dominant_hue(A._pool_histogram(entries, "pale"), A.MIN_CONFIDENCE, True)
    sat_win = _band_winner(sat_hist, p)
    if sat_win is not None:
        hue, _ = sat_win
        legacy = A._dominant_hue(sat_hist, 0.0, False)
        if _pale_identity(entries, hue, legacy[1] if legacy else 0.0, pale_win):
            return describe(pale_seed(entries, hue))
        wsum = sum(w for _, w in entries)
        cov = sum(band_sum(g.hist_cov, hue, p["span"]) * w for g, w in entries) / wsum
        if cov < p["min_cov"]:
            return None
        grid = A._merged_band_grid(entries, hue, p["span"], "saturated")
        return describe(_v5_vivid(grid, hue, p["span"], p["core"]))
    if pale_win is not None:
        return describe(pale_seed(entries, pale_win[0]))
    return None


def _pale_identity(entries, hue, conf, pale_win):
    """The shipped pale-identity rules, on the shipped (single-bin) confidence."""
    sat_mass = sum(A._merged_band_grid(entries, hue, A.BAND_SPAN, "saturated").values())
    pale_mass = sum(A._merged_band_grid(entries, hue, A.BAND_SPAN, "pale").values())
    if pale_mass <= 0:
        return False
    share = pale_mass / (pale_mass + sat_mass)
    coherent = (
        pale_win is not None
        and A._hue_distance(pale_win[0], hue) <= A.PALE_AGREEMENT
        and pale_win[1] >= A.PALE_CONF_MULT * conf
    )
    weak = share >= A.PALE_REP_MIN_SHARE and conf < A.PALE_REP_MAX_SAT_CONF
    return coherent or weak


def _schedule(decide_from, portrait, gallery, p):
    """Shipped portrait schedule, except a 10+ gallery that declines stays declined."""
    n = len(gallery)
    base = [(g, 1.0) for g in gallery]
    share = A._portrait_share(n)
    if portrait is None or share <= 0:
        return decide_from(base, p)
    if n == 0:
        return decide_from([(portrait, 1.0)], p)
    return decide_from([*base, (portrait, share / (1 - share) * n)], p)


def _measured(portrait, gallery, measure_image=None):
    pm = measure(portrait, measure_image) if portrait is not None else None
    gm = [x for x in (measure(i, measure_image) for i in gallery) if x is not None]
    return pm, gm


def method_v5(portrait, gallery):
    pm, gm = _measured(portrait, gallery)
    if pm is None and not gm:
        return None
    return _schedule(_v5_decide_from, pm, gm, V5)


# ---- V6 / V8: peak picks the hue, band share is confidence, vivid core shade ----------

V6 = {
    "conf_span": 22.5,
    "min_share": 0.2,
    "core": 0.35,
    "min_cov": 0.03,
    "hue_span": 10,
    "rank": "hsv",
}
V8 = {**V6, "rank": "oklch"}


def peak_winner(hist, p):
    """Shipped peak location and margin; confidence measured as band share."""
    smooth, total = A._smooth(hist)
    if total <= 0:
        return None
    win = max(range(A.HUE_BINS), key=lambda i: smooth[i])
    wd = (win + 0.5) * 5
    rival = max(
        (
            smooth[i]
            for i in range(A.HUE_BINS)
            if A._hue_distance((i + 0.5) * 5, wd) >= A.RIVAL_SEPARATION
        ),
        default=0,
    )
    if rival > 0 and smooth[win] / rival < A.MIN_MARGIN:
        return None
    share = band_sum(hist, wd, p["conf_span"]) / sum(hist)
    if share < p["min_share"]:
        return None
    return wd, share, smooth[win] / total


def vivid_shade(grid, peak, p):
    """Hue pinned near the peak; L and C from the most colourful `core` of the band."""
    cells = []
    for (hb, sb, vb), w in grid.items():
        hue = (hb + 0.5) * 5
        if A._hue_distance(hue, peak) > p["conf_span"]:
            continue
        s, v = (sb + 0.5) / A.SAT_STEPS, (vb + 0.5) / A.VAL_STEPS
        L, C, h = A.rgb_to_oklch(*colorsys.hsv_to_rgb(hue / 360, s, v))
        cells.append((s if p["rank"] == "hsv" else C, L, C, h, w, hue))
    if not cells:
        return None
    near = [c for c in cells if A._hue_distance(c[5], peak) <= p["hue_span"]] or cells
    sx = sum(math.sin(math.radians(c[3])) * c[4] for c in near)
    cx = sum(math.cos(math.radians(c[3])) * c[4] for c in near)
    hue = math.degrees(math.atan2(sx, cx)) % 360
    total = sum(c[4] for c in cells)
    cells.sort(key=lambda c: -c[0])
    run = Lw = Cw = ww = 0.0
    for _, L, C, _, w, _ in cells:
        Lw += L * w
        Cw += C * w
        ww += w
        run += w
        if run >= total * p["core"]:
            break
    return fit_in_gamut(Lw / ww, Cw / ww, hue)


def peak_decide_from(entries, p=V8):
    if not entries:
        return None
    sat_hist = A._pool_histogram(entries, "saturated")
    pale_win = A._dominant_hue(A._pool_histogram(entries, "pale"), A.MIN_CONFIDENCE, True)
    sat_win = peak_winner(sat_hist, p)
    if sat_win is not None:
        hue, _, conf = sat_win
        if _pale_identity(entries, hue, conf, pale_win):
            seed = pale_seed(entries, hue)
            if seed:  # a pale seed too grey to use falls back to the saturated band
                return describe(seed)
        wsum = sum(w for _, w in entries)
        cov = sum(band_sum(g.hist_cov, hue, p["conf_span"]) * w for g, w in entries) / wsum
        if cov < p["min_cov"]:
            return None
        grid = A._merged_band_grid(entries, hue, p["conf_span"], "saturated")
        return describe(vivid_shade(grid, hue, p))
    if pale_win is not None:
        seed = pale_seed(entries, pale_win[0])
        return describe(seed) if seed else None
    return None


def _peak_method(p, measure_image=None):
    def run(portrait, gallery):
        pm, gm = _measured(portrait, gallery, measure_image)
        if pm is None and not gm:
            return None
        return _schedule(peak_decide_from, pm, gm, p)

    return run


method_v6 = _peak_method(V6)
method_v8 = _peak_method(V8)


# ---- V7: one continuous OKLCH weighting ------------------------------------------

V7 = {
    "c0": 0.02, "c1": 0.10, "pool_pow": 0.5, "conf_span": 22.5, "min_share": 0.22,
    "margin": 1.25, "rival_sep": 60, "core": 0.35, "hue_span": 12, "min_cov": 0.04,
    "Lmin": 0.25,
}  # fmt: skip


def _to_oklch(img):
    a = np.asarray(img.convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    m1 = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    m2 = np.array(
        [
            [0.2104542553, 0.793617785, -0.0040720468],
            [1.9779984951, -2.428592205, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.808675766],
        ]
    )
    lab = np.cbrt(lin @ m1.T) @ m2.T
    L, a_, b_ = lab[:, 0], lab[:, 1], lab[:, 2]
    return L, np.hypot(a_, b_), np.degrees(np.arctan2(b_, a_)) % 360


class _OkMeasure:
    __slots__ = ("C", "L", "cov", "h", "hist", "w")


def _v7_measure(img, p=V7):
    L, C, h = _to_oklch(img)
    keep = (p["Lmin"] <= L) & ~((L > 0.93) & (C < 0.04))
    keep &= ~((h >= 35) & (h <= 80) & (C >= 0.02) & (C <= 0.13) & (L > 0.62))  # skin
    w = np.clip((C - p["c0"]) / (p["c1"] - p["c0"]), 0, 1) * keep
    tot = w.sum()
    if tot <= 1e-6 or (w > 0).sum() < 24:
        return None
    m = _OkMeasure()
    bins = np.minimum((h / 360 * A.HUE_BINS).astype(int), A.HUE_BINS - 1)
    m.hist = np.bincount(bins, weights=w, minlength=A.HUE_BINS) / tot
    sel = w > 0
    m.L, m.C, m.h, m.w = L[sel], C[sel], h[sel], w[sel] / tot
    m.cov = tot / len(L)
    return m


def _np_smooth(hist):
    k = np.exp(-(np.arange(-5, 6) ** 2) / (2 * 1.6**2))
    return np.convolve(np.concatenate([hist[-5:], hist, hist[:5]]), k, mode="valid")


def _np_hd(a, b):
    d = np.abs(a - b) % 360
    return np.where(d > 180, 360 - d, d)


def _v7_decide_from(entries, p=V7):
    if not entries:
        return None
    ws = np.array([w for _, w in entries])
    hists = np.array([m.hist for m, _ in entries]) ** p["pool_pow"]
    hists /= hists.sum(axis=1, keepdims=True)
    pool = (hists * ws[:, None]).sum(0) / ws.sum()
    sm = _np_smooth(pool)
    win = int(sm.argmax())
    centres = (np.arange(A.HUE_BINS) + 0.5) * 5
    wd = centres[win]
    far = _np_hd(centres, wd) >= p["rival_sep"]
    rival = sm[far].max() if far.any() else 0
    if rival > 0 and sm[win] / rival < p["margin"]:
        return None
    band = _np_hd(centres, wd) <= p["conf_span"]
    if pool[band].sum() / pool.sum() < p["min_share"]:
        return None
    if sum(m.cov * m.hist[band].sum() * w for m, w in entries) / ws.sum() < p["min_cov"]:
        return None
    parts = []
    for m, w in entries:
        s = _np_hd(m.h, wd) <= p["conf_span"]
        if s.any():
            parts.append((m.L[s], m.C[s], m.h[s], m.w[s] / m.w[s].sum() * w))
    L, C, h, wt = (np.concatenate(x) for x in zip(*parts, strict=True))
    near = _np_hd(h, wd) <= p["hue_span"]
    hue = (
        math.degrees(
            math.atan2(
                (np.sin(np.radians(h[near])) * wt[near]).sum(),
                (np.cos(np.radians(h[near])) * wt[near]).sum(),
            )
        )
        % 360
    )
    order = np.argsort(-C)
    cum = np.cumsum(wt[order])
    top = order[: int(np.searchsorted(cum, cum[-1] * p["core"])) + 1]
    Lc = float((L[top] * wt[top]).sum() / wt[top].sum())
    Cc = float((C[top] * wt[top]).sum() / wt[top].sum())
    return describe(fit_in_gamut(Lc, Cc, hue))


def method_v7(portrait, gallery):
    pm = _v7_measure(portrait) if portrait is not None else None
    gm = [x for x in (_v7_measure(i) for i in gallery) if x is not None]
    if pm is None and not gm:
        return None
    return _schedule(_v7_decide_from, pm, gm, V7)


# ---- V9 / V11: alternative pixel classifiers ------------------------------------

# Pale anime skin: pink-to-peach, lightly saturated, bright. SKIN_HUE (12-48)
# misses the pink half of it, which then wins the pale class as dusty pink.
# val_lo was 0.6 at first; shaded skin at V 0.45-0.6 then still won Artoria
# (Alter) a grey-mauve once segmentation had removed her red backgrounds.
PALE_SKIN = {"hue_lo": 335, "hue_hi": 20, "sat_hi": 0.35, "val_lo": 0.45}
GAP = {"sat_min": 0.10, "val_min": 0.25, "weight": 0.5}


def is_pale_skin(h, s, v):
    return (
        (h >= PALE_SKIN["hue_lo"] or h <= PALE_SKIN["hue_hi"])
        and s <= PALE_SKIN["sat_hi"]
        and v >= PALE_SKIN["val_lo"]
    )


def _in_zone(hue, lo, hi):
    """Whether `hue` lies in [lo, hi] on the wheel; lo > hi wraps through 0."""
    return lo <= hue <= hi if lo <= hi else (hue >= lo or hue <= hi)


def classify(
    img,
    *,
    gap=False,
    reject_pale_skin=False,
    skin=None,
    skin_hue=None,
    skin_val=0.6,
    warm_damp=None,
    warm_white=None,
    warm_damp_light=None,
):
    """The shipped `measure_image`, with the experimental switches.

    `skin` is the pale-skin predicate used when `reject_pale_skin` is set.
    `warm_damp` is (hue_lo, hue_hi, sat_max, factor): pixels in that hue range at
    or under that saturation vote with weight x factor instead of being dropped.
    `warm_white` is (hue_lo, hue_hi, sat_below): pale pixels in that hue range
    under that saturation are dropped -- cream paper, ivory, warm-lit whites.
    """
    skin = skin or is_pale_skin
    skin_lo, skin_hi = skin_hue or A.SKIN_HUE
    img = img.convert("RGB")
    sat_grid: dict = {}
    pale_grid: dict = {}
    st = pt = 0.0
    kept = 0
    for r8, g8, b8 in img.getdata():
        r, g, b = r8 / 255, g8 / 255, b8 / 255
        hue, s, v = colorsys.rgb_to_hsv(r, g, b)
        if v < 0.15 or (v >= 0.95 and s <= 0.15) or max(r, g, b) - min(r, g, b) < 1e-9:
            continue
        hue *= 360
        if skin_lo <= hue <= skin_hi and 0.12 <= s <= 0.55 and v >= skin_val:
            continue
        if reject_pale_skin and s >= A.PALE_SAT_MIN and skin(hue, s, v):
            continue
        key = (min(71, int(hue / 5)), min(19, int(s * 20)), min(19, int(v * 20)))
        if s >= A.SATURATED_SAT_MIN:
            w = s**1.6 * A._light_pref(v)
            if (
                warm_damp
                and _in_zone(hue, warm_damp[0], warm_damp[1])
                and (s <= warm_damp[2] or v < WARM_DARK_V)
            ):
                w *= warm_damp[3]
            elif (
                warm_damp_light
                and _in_zone(hue, warm_damp_light[0], warm_damp_light[1])
                and s <= warm_damp_light[2]
            ):
                w *= warm_damp_light[3]
            sat_grid[key] = sat_grid.get(key, 0) + w
            st += w
            kept += 1
        elif s >= A.PALE_SAT_MIN and v >= A.PALE_VAL_MIN:
            w = s * A.PALE_VOTE_WEIGHT
            if warm_white and warm_white[0] <= hue <= warm_white[1] and s < warm_white[2]:
                if len(warm_white) > 3 and warm_white[3] == "mute":
                    pt += w  # still part of the image's pale total, so nothing renormalises
                    kept += 1
                continue
            if warm_damp and _in_zone(hue, warm_damp[0], warm_damp[1]):
                w *= warm_damp[3]
            pale_grid[key] = pale_grid.get(key, 0) + w
            pt += w
            kept += 1
        elif gap and s >= GAP["sat_min"] and v >= GAP["val_min"]:
            w = s**1.6 * A._light_pref(v) * GAP["weight"]
            sat_grid[key] = sat_grid.get(key, 0) + w
            st += w
            kept += 1
    if kept < 24:
        return None
    sat_grid = {k: w / st for k, w in sat_grid.items()} if st > 0 else {}
    pale_grid = {k: w / pt for k, w in pale_grid.items()} if pt > 0 else {}
    if not sat_grid and not pale_grid:
        return None
    return A.ImageGrids(sat_grid, pale_grid)


def _with_gap(img):
    return classify(img, gap=True)


def _no_pale_skin(img):
    return classify(img, reject_pale_skin=True)


method_v9 = _peak_method(V8, _with_gap)
method_v8s = _peak_method(V8, _no_pale_skin)  # v8 + skin fix, no segmentation


# ---- V10-V12: segmentation, then the tie-breaker ------------------------------------

FG_THRESHOLD = 0.5
MIN_FG_SHARE = 0.03  # a smaller mask is more likely a miss than a character
MAX_FG = 0.85  # a larger one is a scene the model could not separate


def _full_res(path):
    with Image.open(path) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
        return im.convert("RGB")


def foreground_only(img):
    """Background painted white (which the classifier already ignores).

    The mask comes from the full-resolution source when the image carries one;
    at 200px the model misses the character in about half of all images.
    """
    src = img.info.get("src")
    m = seg.mask_for(_full_res(src) if src else img)
    if m.shape[::-1] != img.size:
        m = (
            np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR))
            / 255.0
        )
    keep = m >= FG_THRESHOLD
    if keep.mean() < MIN_FG_SHARE:
        return img
    arr = np.asarray(img.convert("RGB")).copy()
    arr[~keep] = 255
    return Image.fromarray(arr)


def fg_share(img):
    return float((np.asarray(img) != 255).any(axis=2).mean())


def _segmented(portrait, gallery, drop_scenes):
    fp = foreground_only(portrait) if portrait is not None else None
    fg = []
    for g in gallery:
        f = foreground_only(g)
        if drop_scenes and fg_share(f) > MAX_FG:
            continue
        fg.append(f)
    return fp, fg


def _seg_method(measure_image=None, drop_scenes=False):
    inner = _peak_method(V8, measure_image)

    def run(portrait, gallery):
        return inner(*_segmented(portrait, gallery, drop_scenes))

    return run


method_v10 = _seg_method()
method_v11 = _seg_method(_no_pale_skin)
method_v11d = _seg_method(_no_pale_skin, drop_scenes=True)

CANDIDATE_RATIO = 0.6
CANDIDATE_SHARE = 0.15


def candidates(hist):
    """Hues the gallery strongly supports: smoothed peaks >= 60% of the top one,
    60 degrees apart, each holding >= 15% of the pool within +-22.5 degrees."""
    smooth, total = A._smooth(hist)
    if total <= 0:
        return []
    order = sorted(range(A.HUE_BINS), key=lambda i: -smooth[i])
    top = smooth[order[0]]
    picked: list[float] = []
    for i in order:
        if smooth[i] < CANDIDATE_RATIO * top:
            break
        d = (i + 0.5) * 5
        if any(A._hue_distance(d, c) < A.RIVAL_SEPARATION for c in picked):
            continue
        if band_sum(hist, d, 22.5) / sum(hist) >= CANDIDATE_SHARE:
            picked.append(d)
    return picked


def _v12_decide(portrait, gallery, p=V8):
    """The portrait chooses between gallery candidates; it never adds or blends one."""
    base = [(g, 1.0) for g in gallery]
    if len(gallery) < 10 or portrait is None:
        return _schedule(peak_decide_from, portrait, gallery, p)
    sat_hist = A._pool_histogram(base, "saturated")
    cands = candidates(sat_hist)
    if len(cands) < 2:
        return peak_decide_from(base, p)
    ph = A._pool_histogram([(portrait, 1.0)], "saturated")
    scores = {c: band_sum(ph, c, 22.5) for c in cands}
    best = max(cands, key=lambda c: scores[c])
    if scores[best] <= 0:
        return peak_decide_from(base, p)
    grid = A._merged_band_grid(base, best, p["conf_span"], "saturated")
    return describe(vivid_shade(grid, best, p))


def method_v12(portrait, gallery):
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    pm, gm = _measured(fp, fg, _no_pale_skin)
    if pm is None and not gm:
        return None
    return _v12_decide(pm, gm)


# ---- V13: the owner's review ----------------------------------------------------
#
# Three changes over V12, each from the review of its contact sheet:
#
# 1. Light colours vote on the hue. Pale pixels only ever entered through the
#    narrow pale-identity rule, so a character whose colour is light hair
#    (Ceres Fauna's mint, Rebecca's teal) lost the hue to saturated clothing and
#    backgrounds. Hue evidence is now saturated + PALE_WEIGHT x pale, both
#    normalised per image.
# 2. Ties go to the main image, whole. Candidates are the evidence's peaks at
#    least TIE_RATIO of the top one and CANDIDATE_SEP apart (60 degrees merged
#    Reze's violet into blue); the main image -- background included, which on
#    Mudae portraits is often the character's colour -- picks the one it carries
#    most of. It still never adds a hue of its own.
# 3. No colour from the gallery -> the main image alone decides (the owner
#    prefers a semi-correct colour to none).

PALE_WEIGHT = 1.0
CANDIDATE_SEP = 30
TIE_RATIO = 1 / A.MIN_MARGIN  # within the shipped two-colour margin = a tie
TIE_BAND = 15  # +-degrees of the main image counted for a candidate


def evidence(entries):
    sat = A._pool_histogram(entries, "saturated")
    pale = A._pool_histogram(entries, "pale")
    return [s + PALE_WEIGHT * p for s, p in zip(sat, pale, strict=True)], sat, pale


def peak_list(hist, sep=CANDIDATE_SEP):
    """Smoothed peaks, strongest first, each `sep` degrees from any stronger one."""
    smooth, total = A._smooth(hist)
    if total <= 0:
        return [], smooth
    picked: list[int] = []
    for i in sorted(range(A.HUE_BINS), key=lambda i: -smooth[i]):
        if all(A._hue_distance((i + 0.5) * 5, (j + 0.5) * 5) >= sep for j in picked):
            picked.append(i)
    return picked, smooth


def shade_at(entries, hue, p=V8):
    """Vivid shade of `hue`: the shipped pale-identity rule picks the class."""
    sat_hist = A._pool_histogram(entries, "saturated")
    pale_hist = A._pool_histogram(entries, "pale")
    smooth, total = A._smooth(sat_hist)
    b = min(A.HUE_BINS - 1, int(hue / 5))
    conf = smooth[b] / total if total > 0 else 0.0
    pale_win = A._dominant_hue(pale_hist, A.MIN_CONFIDENCE, True)
    sat_grid = A._merged_band_grid(entries, hue, p["conf_span"], "saturated")
    pale_grid = A._merged_band_grid(entries, hue, p["conf_span"], "pale")
    use_pale = not sat_grid or (pale_grid and _pale_identity(entries, hue, conf, pale_win))
    grid = pale_grid if use_pale else sat_grid
    if not grid:
        return None
    return describe(vivid_shade(grid, hue, p))


def v13_decide_from(entries, portrait=None, p=V8):
    """(result, reason). `portrait` is the whole main image's grids, for ties."""
    if not entries:
        return None, "no images"
    hist, _, _ = evidence(entries)
    peaks, smooth = peak_list(hist)
    if not peaks:
        return None, "no chromatic evidence"
    top = smooth[peaks[0]]
    tied = [i for i in peaks if smooth[i] >= TIE_RATIO * top]
    rivals_far = [i for i in tied[1:] if A._hue_distance((i + 0.5) * 5, (peaks[0] + 0.5) * 5) >= 60]
    choice = (peaks[0] + 0.5) * 5
    reason = "clear winner"
    if rivals_far:
        if portrait is None:
            return None, "two-colour tie, no main image to break it"
        ph, _, _ = evidence([(portrait, 1.0)])
        scores = {(i + 0.5) * 5: band_sum(ph, (i + 0.5) * 5, TIE_BAND) for i in tied}
        choice = max(scores, key=scores.get)
        if scores[choice] <= 0:
            return None, "two-colour tie, main image carries neither"
        reason = "tie broken by main image: " + ", ".join(
            f"{h:.0f}deg {s:.2f}" for h, s in sorted(scores.items(), key=lambda t: -t[1])
        )
    share = band_sum(hist, choice, p["conf_span"]) / sum(hist)
    if share < CANDIDATE_SHARE:
        return None, f"winning band holds only {share:.2f}"
    wsum = sum(w for _, w in entries)
    cov = sum(band_sum(g.hist_cov, choice, p["conf_span"]) * w for g, w in entries) / wsum
    pale_cov = (
        sum(
            sum(
                w2
                for (hb, _, _), w2 in g.pale.items()
                if A._hue_distance((hb + 0.5) * 5, choice) <= 22.5
            )
            * w
            for g, w in entries
        )
        / wsum
    )
    if cov < p["min_cov"] and pale_cov < 0.25:
        return None, f"too little of the art wears it (coverage {cov:.3f})"
    return shade_at(entries, choice, p), reason


def v13(portrait, gallery, trace=None):
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    gm = [x for x in (measure(i, _no_pale_skin) for i in fg) if x is not None]
    whole = measure(portrait, _no_pale_skin) if portrait is not None else None
    seg_p = measure(fp, _no_pale_skin) if fp is not None else None
    n = len(gm)
    share = A._portrait_share(n)
    entries = [(g, 1.0) for g in gm]
    if seg_p is not None and 0 < share < 1 and n:
        entries.append((seg_p, share / (1 - share) * n))
    result, reason = v13_decide_from(entries, whole)
    source = "gallery"
    if result is None and whole is not None:
        fallback, why = v13_decide_from([(whole, 1.0)], None)
        if fallback is not None:
            result, source, reason = fallback, "main image (fallback)", f"{reason}; fallback: {why}"
    if trace is not None:
        trace.append(f"{source}: {reason}")
    return result


def method_v13(portrait, gallery):
    return v13(portrait, gallery)


# ---- V14: colour clusters, skin through orange, main image picks and aims -------
#
# V13's peaks split a colour that spans a range of hues (Ceres Fauna's mint to
# teal, Reze's blue to violet) into small peaks that each lose to one compact
# rival. V14 compares *clusters*: arcs of the hue wheel between valleys of a
# broadly smoothed histogram, scored by the mass they hold. And very pale skin
# (S < 0.12, peach) slipped under both skin rules into the pale class, so the
# pale-skin rule now reaches through orange.

CLUSTER_SIGMA = 2.5  # bins (12.5 degrees): broad enough to merge a colour's shading
MIN_CLUSTER = 0.08  # share of evidence; smaller arcs are noise
SKIN_V14 = {"hue_lo": 335, "hue_hi": 48, "sat_hi": 0.35, "val_lo": 0.45}


def _is_skin_v14(h, s, v):
    lo, hi = SKIN_V14["hue_lo"], SKIN_V14["hue_hi"]
    return (h >= lo or h <= hi) and s <= SKIN_V14["sat_hi"] and v >= SKIN_V14["val_lo"]


def _no_skin_v14(img):
    return classify(img, reject_pale_skin=True, skin=_is_skin_v14)


def _broad_smooth(hist):
    r = int(3 * CLUSTER_SIGMA)
    k = [math.exp(-(j * j) / (2 * CLUSTER_SIGMA**2)) for j in range(-r, r + 1)]
    n = len(hist)
    return [sum(hist[(i + j) % n] * k[j + r] for j in range(-r, r + 1)) for i in range(n)]


def clusters(hist):
    """[(lo_bin, hi_bin, mass_share, peak_bin)] strongest first; arcs are inclusive."""
    n = len(hist)
    total = sum(hist)
    if total <= 0:
        return []
    sm = _broad_smooth(hist)
    valleys = [i for i in range(n) if sm[i] <= sm[i - 1] and sm[i] < sm[(i + 1) % n]]
    if not valleys:
        peak = max(range(n), key=lambda i: sm[i])
        return [(0, n - 1, 1.0, peak)]
    out = []
    for a, b in zip(valleys, valleys[1:] + valleys[:1], strict=True):
        arc = [(a + k) % n for k in range((b - a) % n or n)]
        mass = sum(hist[i] for i in arc) / total
        peak = max(arc, key=lambda i: sm[i])
        out.append((arc[0], arc[-1], mass, peak))
    return sorted((c for c in out if c[2] >= MIN_CLUSTER), key=lambda c: -c[2])


def _in_arc(i, lo, hi):
    return lo <= i <= hi if lo <= hi else (i >= lo or i <= hi)


def v14_decide_from(entries, portrait=None, p=V8):
    if not entries:
        return None, "no images"
    hist, _, _ = evidence(entries)
    cl = clusters(hist)
    if not cl:
        return None, "no chromatic evidence"
    top = cl[0]
    tied = [c for c in cl if c[2] >= TIE_RATIO * top[2]]
    chosen, peak_bin = top, top[3]
    reason = f"clear winner ({top[2]:.2f} vs {cl[1][2]:.2f})" if len(cl) > 1 else "single colour"
    if len(tied) > 1:
        if portrait is None:
            return None, "two-colour tie, no main image to break it"
        ph = evidence_v15([(portrait, 1.0)])
        pt = sum(ph) or 1.0
        scores = [
            (sum(ph[i] for i in range(A.HUE_BINS) if _in_arc(i, c[0], c[1])) / pt, c) for c in tied
        ]
        best_score, chosen = max(scores, key=lambda t: t[0])
        if best_score <= 0:
            return None, "two-colour tie, main image carries neither"
        # Aim at the main image's own peak inside the chosen colour.
        arc = [i for i in range(A.HUE_BINS) if _in_arc(i, chosen[0], chosen[1])]
        ps, _ = A._smooth(ph)
        peak_bin = max(arc, key=lambda i: ps[i])
        reason = "tie broken by main image: " + ", ".join(
            f"{(c[3] + 0.5) * 5:.0f}deg {s:.2f}" for s, c in sorted(scores, key=lambda t: -t[0])
        )
    if chosen[2] < 0.15:
        return None, f"winning colour holds only {chosen[2]:.2f}"
    hue = (peak_bin + 0.5) * 5
    wsum = sum(w for _, w in entries)
    cov = sum(band_sum(g.hist_cov, hue, p["conf_span"]) * w for g, w in entries) / wsum
    pale_share = (
        sum(
            sum(w2 for (hb, _, _), w2 in g.pale.items() if _in_arc(hb, chosen[0], chosen[1])) * w
            for g, w in entries
        )
        / wsum
    )
    if cov < p["min_cov"] and pale_share < 0.25:
        return None, f"too little of the art wears it (coverage {cov:.3f})"
    return shade_at(entries, hue, p), reason


def v14(portrait, gallery, trace=None, measure_image=None):
    measure_image = measure_image or _no_skin_v14
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    gm = [x for x in (measure(i, measure_image) for i in fg) if x is not None]
    whole = measure(portrait, measure_image) if portrait is not None else None
    seg_p = measure(fp, measure_image) if fp is not None else None
    n = len(gm)
    share = A._portrait_share(n)
    entries = [(g, 1.0) for g in gm]
    if seg_p is not None and 0 < share < 1 and n:
        entries.append((seg_p, share / (1 - share) * n))
    result, reason = v14_decide_from(entries, whole)
    source = "gallery"
    if result is None and whole is not None:
        fallback, why = v14_decide_from([(whole, 1.0)], None)
        if fallback is not None:
            result, source, reason = fallback, "main image (fallback)", f"{reason}; fallback: {why}"
    if trace is not None:
        trace.append(f"{source}: {reason}")
    return result


def method_v14(portrait, gallery):
    return v14(portrait, gallery)


# ---- V15: blonde survives, pale colours shaded vividly, agreed aim ----------------
#
# From the owner's review of V14 against the art itself:
# - The shipped skin rule (hue 12-48) also removes blonde hair at 40-48, which is
#   why Panty's yellow barely registered. Anime skin sits at ~15-35; the rule
#   stops at 38 here, and the pale-skin rule likewise.
# - The shipped pale-identity rule misfires when asked about a hue other than
#   the saturated peak it was built around (V14 turned Lynae pale). Instead the
#   band's pale and saturated shares are compared directly.
# - Pale colours are shaded from their most vivid pixels, as saturated ones are:
#   a pale identity (Rebecca's hair) should still read as a colour.
# - A tie broken by the main image aims where the gallery and the main image
#   agree -- the product of their smoothed histograms -- not at the main image's
#   own peak, which sent Artoria's red to her orange.

SKIN_HUE_V15 = (12, 38)
POOL_POW = 1.0  # 0.5 = presence-weighted: a colour in most images beats one heavy in a few


def _hue_marginal(grid):
    h = [0.0] * A.HUE_BINS
    for (hb, _, _), w in grid.items():
        h[hb] += w
    return h


def evidence_v15(entries):
    """Per image: saturated + PALE_WEIGHT x pale, normalised, raised to POOL_POW."""
    pooled = [0.0] * A.HUE_BINS
    wsum = sum(w for _, w in entries) or 1.0
    for g, w in entries:
        h = [
            s + PALE_WEIGHT * p
            for s, p in zip(_hue_marginal(g.saturated), _hue_marginal(g.pale), strict=True)
        ]
        t = sum(h)
        if t <= 0:
            continue
        h = [(x / t) ** POOL_POW for x in h]
        t = sum(h)
        for i in range(A.HUE_BINS):
            pooled[i] += h[i] / t * w / wsum
    return pooled


PALE_OVER_SAT = 1.5  # pale must outweigh saturated this much in the band to shade from it


def _is_skin_v15(h, s, v):
    return (h >= 335 or h <= 38) and s <= 0.35 and v >= 0.45


def _no_skin_v15(img):
    return classify(img, reject_pale_skin=True, skin=_is_skin_v15, skin_hue=SKIN_HUE_V15)


def shade_v15(entries, hue, p=V8):
    sat_total = sum(A._pool_histogram(entries, "saturated")) or 1.0
    pale_total = sum(A._pool_histogram(entries, "pale")) or 1.0
    sat_grid = A._merged_band_grid(entries, hue, p["conf_span"], "saturated")
    pale_grid = A._merged_band_grid(entries, hue, p["conf_span"], "pale")
    sat_share = sum(sat_grid.values()) / sat_total
    pale_share = sum(pale_grid.values()) / pale_total
    use_pale = pale_grid and (not sat_grid or pale_share >= PALE_OVER_SAT * sat_share)
    grid = pale_grid if use_pale else sat_grid
    if not grid:
        return None, "nothing in the band"
    return describe(vivid_shade(grid, hue, p)), ("pale" if use_pale else "saturated")


def v15_decide_from(entries, portrait=None, p=V8):
    if not entries:
        return None, "no images"
    hist = evidence_v15(entries)
    cl = clusters(hist)
    if not cl:
        return None, "no chromatic evidence"
    top = cl[0]
    tied = [c for c in cl if c[2] >= TIE_RATIO * top[2]]
    chosen, peak_bin = top, top[3]
    reason = f"clear winner ({top[2]:.2f} vs {cl[1][2]:.2f})" if len(cl) > 1 else "single colour"
    if len(tied) > 1:
        if portrait is None:
            return None, "two-colour tie, no main image to break it"
        ph = evidence_v15([(portrait, 1.0)])
        pt = sum(ph) or 1.0
        scores = [
            (sum(ph[i] for i in range(A.HUE_BINS) if _in_arc(i, c[0], c[1])) / pt, c) for c in tied
        ]
        best_score, chosen = max(scores, key=lambda t: t[0])
        if best_score <= 0:
            return None, "two-colour tie, main image carries neither"
        gs, gt = A._smooth(hist)
        ps, pst = A._smooth(ph)
        arc = [i for i in range(A.HUE_BINS) if _in_arc(i, chosen[0], chosen[1])]
        peak_bin = max(arc, key=lambda i: (gs[i] / gt) * (ps[i] / pst))
        reason = "tie broken by main image: " + ", ".join(
            f"{(c[3] + 0.5) * 5:.0f}deg {s:.2f}" for s, c in sorted(scores, key=lambda t: -t[0])
        )
    if chosen[2] < 0.15:
        return None, f"winning colour holds only {chosen[2]:.2f}"
    hue = (peak_bin + 0.5) * 5
    wsum = sum(w for _, w in entries)
    cov = sum(band_sum(g.hist_cov, hue, p["conf_span"]) * w for g, w in entries) / wsum
    pale_share = (
        sum(
            sum(w2 for (hb, _, _), w2 in g.pale.items() if _in_arc(hb, chosen[0], chosen[1])) * w
            for g, w in entries
        )
        / wsum
    )
    if cov < p["min_cov"] and pale_share < 0.25:
        return None, f"too little of the art wears it (coverage {cov:.3f})"
    result, cls = shade_v15(entries, hue, p)
    return result, f"{reason}; {hue:.0f}deg shaded from {cls}"


def v15(portrait, gallery, trace=None):
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    gm = [x for x in (measure(i, _no_skin_v15) for i in fg) if x is not None]
    whole = measure(portrait, _no_skin_v15) if portrait is not None else None
    seg_p = measure(fp, _no_skin_v15) if fp is not None else None
    n = len(gm)
    share = A._portrait_share(n)
    entries = [(g, 1.0) for g in gm]
    if seg_p is not None and 0 < share < 1 and n:
        entries.append((seg_p, share / (1 - share) * n))
    result, reason = v15_decide_from(entries, whole)
    source = "gallery"
    if result is None and whole is not None:
        fallback, why = v15_decide_from([(whole, 1.0)], None)
        if fallback is not None:
            result, source, reason = fallback, "main image (fallback)", f"{reason}; fallback: {why}"
    if trace is not None:
        trace.append(f"{source}: {reason}")
    return result


def method_v15(portrait, gallery):
    return v15(portrait, gallery)


# ---- V16: fixed-width colour windows instead of valley clusters -------------------
#
# V14/V15's valley clusters came out 170 degrees wide (Ceres Fauna's mint, her
# blue outfit and everything between were one "colour"), so a colour that owned
# the art could not be told from its neighbours. A colour is now a window of
# +-WINDOW degrees; candidates are window maxima at least 2 x WINDOW apart.

WINDOW = 30
AIM_GALLERY_POW = 1.0  # >1 keeps the aim nearer the gallery's own peak
AIM_SPAN = WINDOW  # how far from the winning window's centre the final hue may move
TIE_WITHOUT_MAIN = "decline"  # or "top": a tie with no main image takes the stronger side
PALE_RULE_TOO = True  # also shade from pale when the shipped pale-identity rule says so


def windows(hist):
    """[(centre_deg, share)] strongest first, centres >= 2*WINDOW apart."""
    total = sum(hist) or 1.0
    w = [band_sum(hist, (i + 0.5) * 5, WINDOW) / total for i in range(A.HUE_BINS)]
    out: list[tuple[float, float]] = []
    for i in sorted(range(A.HUE_BINS), key=lambda i: -w[i]):
        c = (i + 0.5) * 5
        if all(A._hue_distance(c, o) >= 2 * WINDOW for o, _ in out):
            out.append((c, w[i]))
    return out


def shade_v16(entries, hue, p=V8):
    result, cls = shade_v15(entries, hue, p)
    if cls == "saturated" and PALE_RULE_TOO:
        sat_hist = A._pool_histogram(entries, "saturated")
        win = peak_winner(sat_hist, p)
        pale_win = A._dominant_hue(A._pool_histogram(entries, "pale"), A.MIN_CONFIDENCE, True)
        if (
            win
            and A._hue_distance(win[0], hue) <= 22.5
            and _pale_identity(entries, hue, win[2], pale_win)
        ):
            grid = A._merged_band_grid(entries, hue, p["conf_span"], "pale")
            if grid:
                return describe(vivid_shade(grid, hue, p)), "pale (shipped rule)"
    return result, cls


def v16_decide_from(entries, portrait=None, p=V8):
    if not entries:
        return None, "no images"
    hist = evidence_v15(entries)
    cands = windows(hist)
    if not cands or cands[0][1] <= 0:
        return None, "no chromatic evidence"
    top_c, top_s = cands[0]
    tied = [(c, s) for c, s in cands if s >= TIE_RATIO * top_s]
    hue = top_c
    if len(cands) < 2:
        reason = "single colour"
    else:
        reason = (
            f"clear winner {top_c:.0f}deg {top_s:.2f} vs {cands[1][0]:.0f}deg {cands[1][1]:.2f}"
        )
    if len(tied) > 1 and portrait is None and TIE_WITHOUT_MAIN == "top":
        tied = tied[:1]
        reason = "two-colour tie, no main image: took the stronger side"
    if len(tied) > 1:
        if portrait is None:
            return None, "two-colour tie, no main image to break it"
        ph = evidence_v15([(portrait, 1.0)])
        pt = sum(ph) or 1.0
        scores = [(band_sum(ph, c, WINDOW) / pt, c) for c, _ in tied]
        best, chosen = max(scores)
        if best <= 0:
            return None, "two-colour tie, main image carries neither"
        gs, gt = A._smooth(hist)
        ps, pst = A._smooth(ph)
        near = [i for i in range(A.HUE_BINS) if A._hue_distance((i + 0.5) * 5, chosen) <= AIM_SPAN]
        hue = (max(near, key=lambda i: (gs[i] / gt) ** AIM_GALLERY_POW * (ps[i] / pst)) + 0.5) * 5
        reason = "tie broken by main image: " + ", ".join(
            f"{c:.0f}deg {s:.2f}" for s, c in sorted(scores, reverse=True)
        )
    else:
        gs, _ = A._smooth(hist)
        near = [i for i in range(A.HUE_BINS) if A._hue_distance((i + 0.5) * 5, top_c) <= AIM_SPAN]
        hue = (max(near, key=lambda i: gs[i]) + 0.5) * 5
    share = band_sum(hist, hue, WINDOW) / (sum(hist) or 1.0)
    if share < 0.15:
        return None, f"winning colour holds only {share:.2f}"
    wsum = sum(w for _, w in entries)
    cov = sum(band_sum(g.hist_cov, hue, p["conf_span"]) * w for g, w in entries) / wsum
    pale_share = (
        sum(
            sum(
                w2
                for (hb, _, _), w2 in g.pale.items()
                if A._hue_distance((hb + 0.5) * 5, hue) <= WINDOW
            )
            * w
            for g, w in entries
        )
        / wsum
    )
    if cov < p["min_cov"] and pale_share < 0.25:
        return None, f"too little of the art wears it (coverage {cov:.3f})"
    result, cls = shade_v16(entries, hue, p)
    return result, f"{reason}; {hue:.0f}deg shaded from {cls}"


def v16(portrait, gallery, trace=None):
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    gm = [x for x in (measure(i, _no_skin_v15) for i in fg) if x is not None]
    whole = measure(portrait, _no_skin_v15) if portrait is not None else None
    seg_p = measure(fp, _no_skin_v15) if fp is not None else None
    n = len(gm)
    share = A._portrait_share(n)
    entries = [(g, 1.0) for g in gm]
    if seg_p is not None and 0 < share < 1 and n:
        entries.append((seg_p, share / (1 - share) * n))
    result, reason = v16_decide_from(entries, whole)
    source = "gallery"
    if result is None and whole is not None:
        fallback, why = v16_decide_from([(whole, 1.0)], None)
        if fallback is not None:
            result, source, reason = fallback, "main image (fallback)", f"{reason}; fallback: {why}"
    if trace is not None:
        trace.append(f"{source}: {reason}")
    return result


def method_v16(portrait, gallery):
    return v16(portrait, gallery)


# ---- V17: V16 at its best setting, plus a chroma floor for pale identities --------
#
# A pale identity shaded from its own pixels is still pale (Panty's blonde came
# out cream, C 0.05). The accent must read as a colour, so a pale-shaded seed is
# lifted to PALE_MIN_CHROMA at the same hue and lightness (then gamut-fitted).

PALE_MIN_CHROMA = 0.09
PALE_LIFT_FROM = 0.035  # below this the pale colour is grey (2B), not a tint to strengthen


def v17(portrait, gallery, trace=None, window=30):
    global PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW
    PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW = 0.5, 0.5, window, 2.0
    local_trace: list[str] = []
    r = v16(portrait, gallery, local_trace)
    pale_shaded = "pale" in local_trace[0].rsplit("shaded from", 1)[-1]
    if r is not None and pale_shaded and PALE_LIFT_FROM <= r["chroma"] < PALE_MIN_CHROMA:
        r = describe(fit_in_gamut(r["lightness"], PALE_MIN_CHROMA, r["hue"]))
        local_trace[0] += f"; chroma lifted to {PALE_MIN_CHROMA}"
    if trace is not None:
        trace.extend(local_trace)
    return r


def method_v17(portrait, gallery):
    return v17(portrait, gallery)


# ---- V18: keep the aim near the winning colour; a tie without a main image ------
#
# V17 aimed anywhere in the +-30 window, so a red window (Ereshkigal, Ishtar,
# Will Auceptin) was aimed at its 40-degree edge, where pale blonde and skin
# pile up, and came out pale gold. The aim now stays within AIM_SPAN of the
# window's centre. And a two-colour tie with no main image to break it takes the
# stronger side instead of declining -- the owner prefers a semi-correct colour.


def v18(portrait, gallery, trace=None, window=30):
    global AIM_SPAN, TIE_WITHOUT_MAIN
    AIM_SPAN, TIE_WITHOUT_MAIN = min(15, window), "top"
    try:
        return v17(portrait, gallery, trace, window=window)
    finally:
        AIM_SPAN, TIE_WITHOUT_MAIN = WINDOW, "decline"


def method_v18(portrait, gallery):
    return v18(portrait, gallery)


# ---- V19: V18 with shaded skin removed from the saturated class too --------------

SKIN_VAL_V19 = 0.45


def _no_skin_v19(img):
    return classify(
        img, reject_pale_skin=True, skin=_is_skin_v15, skin_hue=SKIN_HUE_V15, skin_val=SKIN_VAL_V19
    )


def v19(portrait, gallery, trace=None):
    global _no_skin_v15
    original = _no_skin_v15
    _no_skin_v15 = _no_skin_v19  # v16 measures through this name
    try:
        return v18(portrait, gallery, trace)
    finally:
        _no_skin_v15 = original


def method_v19(portrait, gallery):
    return v19(portrait, gallery)


# ---- V20: damp the skin-tone zone instead of trusting presence there -----------------
#
# V17's presence pooling rewards what appears in every image -- and in anime art
# that is skin and warm shading. Dazai, Poison Ivy, Will Auceptin and Ishtar all
# won an orange window (22-32 degrees) that is skin and brown, then aimed and
# shaded it into gold. The skin-tone zone (hue 10-45, S <= WARM_SAT_MAX; the
# whole zone for pale pixels) now votes at WARM_FACTOR weight. Red hair (under
# 10 degrees, or more saturated) and blonde (above 45) are untouched.

WARM_ZONE = (10, 45)
WARM_SAT_MAX = 0.65
WARM_FACTOR = 0.25
WARM_DARK_V = 0.55  # brown: dark warm pixels are damped however saturated


def _no_skin_v20(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v15,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
    )


V20_WINDOW = 30


def v20(portrait, gallery, trace=None):
    global _no_skin_v15
    original = _no_skin_v15
    _no_skin_v15 = _no_skin_v20  # v16 measures through this name
    try:
        return v18(portrait, gallery, trace, window=V20_WINDOW)
    finally:
        _no_skin_v15 = original


def method_v20(portrait, gallery):
    return v20(portrait, gallery)


# ---- V21: windows centred on peaks; warm whites dropped ------------------------------
#
# V20 still went gold for Will Auceptin, Osamu Dazai and Poison Ivy. Two causes:
# a +-30 window centred at 22-28 degrees summed red (0-20) and gold (40-60) --
# two colours -- into one that beat either; and faint warm whites (pale, S under
# 0.15, hue 35-70: cream paper, ivory, warm-lit highlights) fed the gold side.
# Windows are now centred only on peaks of the smoothed evidence, and those
# faint warm whites do not vote.

WARM_WHITE = (35, 70, 0.15)


def peak_windows(hist):
    """Like `windows`, but every centre is a local maximum of the smoothed evidence."""
    total = sum(hist) or 1.0
    sm, _ = A._smooth(hist)
    n = A.HUE_BINS
    peaks = [i for i in range(n) if sm[i] >= sm[i - 1] and sm[i] >= sm[(i + 1) % n] and sm[i] > 0]
    scored = sorted(
        (((i + 0.5) * 5, band_sum(hist, (i + 0.5) * 5, WINDOW) / total) for i in peaks),
        key=lambda t: -t[1],
    )
    out: list[tuple[float, float]] = []
    for c, sc in scored:
        if all(A._hue_distance(c, o) >= 2 * WINDOW for o, _ in out):
            out.append((c, sc))
    return out


def _no_skin_v21(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v15,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
        warm_white=WARM_WHITE,
    )


def v21(portrait, gallery, trace=None):
    global _no_skin_v15, windows
    original_measure, original_windows = _no_skin_v15, windows
    _no_skin_v15, windows = _no_skin_v21, peak_windows  # v16 reads both names
    try:
        return v18(portrait, gallery, trace)
    finally:
        _no_skin_v15, windows = original_measure, original_windows


def method_v21(portrait, gallery):
    return v21(portrait, gallery)


def v21_whites_only(portrait, gallery, trace=None):
    """V21's warm-white rule without its peak-centred windows."""
    global _no_skin_v15
    original = _no_skin_v15
    _no_skin_v15 = _no_skin_v21
    try:
        return v18(portrait, gallery, trace)
    finally:
        _no_skin_v15 = original


def v21_peaks_only(portrait, gallery, trace=None):
    """V21's peak-centred windows without its warm-white rule (V20 measurement)."""
    global _no_skin_v15, windows
    original_measure, original_windows = _no_skin_v15, windows
    _no_skin_v15, windows = _no_skin_v20, peak_windows
    try:
        return v18(portrait, gallery, trace)
    finally:
        _no_skin_v15, windows = original_measure, original_windows


# ---- V22: V20 + warm whites dropped, aim across the whole window ---------------------
#
# Of V21's two changes only the warm-white rule helped (25/26); peak-centred
# windows broke Panty, Rebecca and Tsumugi. V18 had narrowed the aim to +-15
# degrees because pale skin and cream at the window's edge pulled it to gold;
# with the skin zone damped and warm whites gone, the aim may use the whole
# window again, which lets Will Auceptin's red peak (8 degrees) beat the gold
# half of a window centred at 28.


def v22(portrait, gallery, trace=None):
    global _no_skin_v15, AIM_SPAN, TIE_WITHOUT_MAIN
    original = _no_skin_v15
    _no_skin_v15 = _no_skin_v21
    try:
        AIM_SPAN, TIE_WITHOUT_MAIN = 30, "top"
        return v17(portrait, gallery, trace)
    finally:
        _no_skin_v15 = original
        AIM_SPAN, TIE_WITHOUT_MAIN = WINDOW, "decline"


def method_v22(portrait, gallery):
    return v22(portrait, gallery)


# ---- V23: mute warm whites, aim by sub-colour mass --------------------------------------
#
# Two fixes to V22. Dropping warm whites renormalised the pale class, so what was
# left (Lynae's pale cyan) grew and flipped her shade to pale; muted whites still
# count toward the pale total but cast no vote. And the aim compared single peak
# heights, which a compact colour always wins: Will Auceptin's red spreads over
# 40 degrees, his gold in three images is packed into 15. The aim now picks the
# spot inside the chosen window whose +-AIM_BAND neighbourhood holds the most.

AIM_BAND = 15


def _no_skin_v23(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v15,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
        warm_white=(*WARM_WHITE, "mute"),
    )


def _aim_by_mass(hist, centre, span):
    near = [i for i in range(A.HUE_BINS) if A._hue_distance((i + 0.5) * 5, centre) <= span]
    return (max(near, key=lambda i: band_sum(hist, (i + 0.5) * 5, AIM_BAND)) + 0.5) * 5


def v23(portrait, gallery, trace=None):
    global _no_skin_v15, AIM_SPAN, TIE_WITHOUT_MAIN, v16_decide_from
    global PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW
    saved = (_no_skin_v15, v16_decide_from)
    base_decide = v16_decide_from
    _no_skin_v15 = _no_skin_v23
    PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW = 0.5, 0.5, 30, 2.0
    AIM_SPAN, TIE_WITHOUT_MAIN = 30, "top"

    def decide(entries, portrait=None, p=V8):
        result, reason = base_decide(entries, portrait, p)
        if result is None or "tie broken" in reason or not entries:
            return result, reason
        hist = evidence_v15(entries)
        hue = _aim_by_mass(hist, windows(hist)[0][0], AIM_SPAN)
        shaded, cls = shade_v16(entries, hue, p)
        return shaded, reason.split(";")[0] + f"; {hue:.0f}deg (mass aim) shaded from {cls}"

    v16_decide_from = decide  # v16 calls it by name
    try:
        local: list[str] = []
        r = v16(portrait, gallery, local)
        pale_shaded = local and "pale" in local[0].rsplit("shaded from", 1)[-1]
        if r is not None and pale_shaded and PALE_LIFT_FROM <= r["chroma"] < PALE_MIN_CHROMA:
            r = describe(fit_in_gamut(r["lightness"], PALE_MIN_CHROMA, r["hue"]))
            local[0] += f"; chroma lifted to {PALE_MIN_CHROMA}"
        if trace is not None:
            trace.extend(local)
        return r
    finally:
        _no_skin_v15, v16_decide_from = saved
        AIM_SPAN, TIE_WITHOUT_MAIN = WINDOW, "decline"


def method_v23(portrait, gallery):
    return v23(portrait, gallery)


# ---- V24: V22's hue, V20's shade --------------------------------------------------------
#
# Dropping warm whites (V21/V22) fixed the gold drift but renormalised the pale
# class, so the pale-versus-saturated shade decision tipped to pale for Lynae
# (#7fdce9) and Kotoko Ijichi (#fcefa9). The two measurements now do separate
# jobs: whites dropped for *which hue* (evidence, windows, ties, coverage),
# whites kept for *which shade* of it.


def v24(portrait, gallery, trace=None):
    global shade_v16, AIM_SPAN, TIE_WITHOUT_MAIN, PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW
    PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW = 0.5, 0.5, 30, 2.0
    AIM_SPAN, TIE_WITHOUT_MAIN = 30, "top"
    fp, fg = _segmented(portrait, gallery, drop_scenes=True)
    pairs = [(measure(i, _no_skin_v21), measure(i, _no_skin_v20)) for i in fg]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    whole = measure(portrait, _no_skin_v21) if portrait is not None else None
    whole_shade = measure(portrait, _no_skin_v20) if portrait is not None else None
    seg_p = measure(fp, _no_skin_v21) if fp is not None else None
    seg_p_shade = measure(fp, _no_skin_v20) if fp is not None else None
    n = len(pairs)
    share = A._portrait_share(n)
    hue_entries = [(a, 1.0) for a, _ in pairs]
    shade_entries = [(b, 1.0) for _, b in pairs]
    if seg_p is not None and seg_p_shade is not None and 0 < share < 1 and n:
        wt = share / (1 - share) * n
        hue_entries.append((seg_p, wt))
        shade_entries.append((seg_p_shade, wt))

    original_shade = shade_v16

    def run(entries, shade_with, portrait_grids):
        global shade_v16
        shade_v16 = lambda _e, h, p=V8: original_shade(shade_with, h, p)  # noqa: E731
        try:
            return v16_decide_from(entries, portrait_grids)
        finally:
            shade_v16 = original_shade

    try:
        result, reason = run(hue_entries, shade_entries, whole)
        source = "gallery"
        if result is None and whole is not None:
            fb, why = run([(whole, 1.0)], [(whole_shade, 1.0)], None)
            if fb is not None:
                result, source, reason = fb, "main image (fallback)", f"{reason}; fallback: {why}"
        pale_shaded = "pale" in reason.rsplit("shaded from", 1)[-1]
        if (
            result is not None
            and pale_shaded
            and PALE_LIFT_FROM <= result["chroma"] < PALE_MIN_CHROMA
        ):
            result = describe(fit_in_gamut(result["lightness"], PALE_MIN_CHROMA, result["hue"]))
            reason += f"; chroma lifted to {PALE_MIN_CHROMA}"
        if trace is not None:
            trace.append(f"{source}: {reason}")
        return result
    finally:
        AIM_SPAN, TIE_WITHOUT_MAIN = WINDOW, "decline"


def method_v24(portrait, gallery):
    return v24(portrait, gallery)


# ---- V25: the skin zone reaches down through red ------------------------------------------
#
# The random sample's brick reds (Mitsuri Kanroji, Tohru, Nadeko Sengoku, Tewi
# Inaba, Nagatoro-san) all won a window centred at 18-28 degrees: skin shadow,
# blush and lips, which run from about 350 to 10 degrees -- below the damped
# zone (10-45). The zone now wraps from WARM_ZONE_V25[0] through 0. Real reds
# (hair, clothes) are more saturated than skin and keep their full vote.

WARM_ZONE_V25 = (350, 45)
WARM_SAT_MAX_V25 = 0.6


def _no_skin_v25_hue(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v15,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE_V25, WARM_SAT_MAX_V25, WARM_FACTOR),
        warm_white=WARM_WHITE,
    )


def _no_skin_v25_shade(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v15,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE_V25, WARM_SAT_MAX_V25, WARM_FACTOR),
    )


def v25(portrait, gallery, trace=None):
    global _no_skin_v21, _no_skin_v20
    saved = (_no_skin_v21, _no_skin_v20)
    _no_skin_v21, _no_skin_v20 = _no_skin_v25_hue, _no_skin_v25_shade  # v24 reads both
    try:
        return v24(portrait, gallery, trace)
    finally:
        _no_skin_v21, _no_skin_v20 = saved


def method_v25(portrait, gallery):
    return v25(portrait, gallery)


# ---- V26: pale pink is not skin -----------------------------------------------------------
#
# V15's pale-skin rule removed hue 335-38 at S <= 0.35 -- which also removes pale
# pink clothes and hair (Tewi Inaba's dress, Sakurako Kawawa's cream-pink,
# Mitsuri Kanroji's hair). What remained at that hue was skin shadow, eyes and
# ribbons, shaded into brick red. Anime skin sits at roughly 352-38 degrees;
# pale pink at 325-352. The rule now starts at PALE_SKIN_FROM.

PALE_SKIN_FROM = 352


def _is_skin_v26(h, s, v):
    return (h >= PALE_SKIN_FROM or h <= 38) and s <= 0.35 and v >= 0.45


def _no_skin_v26_hue(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v26,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
        warm_white=WARM_WHITE,
    )


def _no_skin_v26_shade(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v26,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
    )


def v26(portrait, gallery, trace=None):
    global _no_skin_v21, _no_skin_v20
    saved = (_no_skin_v21, _no_skin_v20)
    _no_skin_v21, _no_skin_v20 = _no_skin_v26_hue, _no_skin_v26_shade  # v24 reads both
    try:
        return v24(portrait, gallery, trace)
    finally:
        _no_skin_v21, _no_skin_v20 = saved


def method_v26(portrait, gallery):
    return v26(portrait, gallery)


# ---- V27: skin shadow below 10 degrees damped; shade blends in the bright half ----------
#
# The random sample's pinks (Tewi Inaba, Nadeko Sengoku, Mitsuri Kanroji) came out
# brick red for two reasons. Skin shadow and blush at 355-10 degrees kept pulling
# the aim toward red; they are now damped like the rest of the skin zone, but only
# at skin saturation and without the dark rule, which in V25 also damped dark red
# clothes (Superman). And the vivid core picks a band's deepest shading, which in a
# pink band is red. The shade now blends (SHADE_BLEND) the vivid core with the
# most chromatic half of the band's *brighter* pixels, pale and saturated together.

SKIN_SHADOW_ZONE = (355, 10, 0.55, WARM_FACTOR)
SHADE_BLEND = 0.5


def _classify_v27(img, whites):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_v26,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
        warm_white=WARM_WHITE if whites else None,
        warm_damp_light=SKIN_SHADOW_ZONE,
    )


def _no_skin_v27_hue(img):
    return _classify_v27(img, True)


def _no_skin_v27_shade(img):
    return _classify_v27(img, False)


def _band_cells(entries, hue, span, cls, scale):
    grid = A._merged_band_grid(entries, hue, span, cls)
    total = sum(grid.values()) or 1.0
    out = []
    for (hb, sb, vb), w in grid.items():
        h = (hb + 0.5) * 5
        if A._hue_distance(h, hue) > span:
            continue
        s, v = (sb + 0.5) / A.SAT_STEPS, (vb + 0.5) / A.VAL_STEPS
        L, C, oh = A.rgb_to_oklch(*colorsys.hsv_to_rgb(h / 360, s, v))
        out.append((L, C, oh, w / total * scale))
    return out


def _lab_mean(cells):
    ww = sum(c[3] for c in cells) or 1.0
    L = sum(c[0] * c[3] for c in cells) / ww
    a = sum(c[1] * math.cos(math.radians(c[2])) * c[3] for c in cells) / ww
    b = sum(c[1] * math.sin(math.radians(c[2])) * c[3] for c in cells) / ww
    return L, a, b


def bright_half(entries, hue, p=V8):
    """OKLab mean of the most chromatic half of the band's brighter-than-median pixels."""
    cells = _band_cells(entries, hue, p["conf_span"], "saturated", 1.0)
    cells += _band_cells(entries, hue, p["conf_span"], "pale", 0.5)
    if not cells:
        return None
    total = sum(c[3] for c in cells)
    run, median_l = 0.0, cells[0][0]
    for c in sorted(cells, key=lambda c: c[0]):
        run += c[3]
        if run >= total / 2:
            median_l = c[0]
            break
    bright = sorted((c for c in cells if c[0] >= median_l), key=lambda c: -c[1])
    bt = sum(c[3] for c in bright)
    run, top = 0.0, []
    for c in bright:
        top.append(c)
        run += c[3]
        if run >= bt / 2:
            break
    return _lab_mean(top)


def v27(portrait, gallery, trace=None):
    global _no_skin_v21, _no_skin_v20, shade_v16
    saved = (_no_skin_v21, _no_skin_v20, shade_v16)
    original_shade = shade_v16

    def blended(entries, hue, p=V8):
        result, cls = original_shade(entries, hue, p)
        bh = bright_half(entries, hue, p)
        if result is None or bh is None or SHADE_BLEND <= 0:
            return result, cls
        r, g, b = (int(result["seed"][i : i + 2], 16) / 255 for i in (1, 3, 5))
        L, C, h = A.rgb_to_oklch(r, g, b)
        a0, b0 = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
        t = SHADE_BLEND
        mix = ((1 - t) * L + t * bh[0], (1 - t) * a0 + t * bh[1], (1 - t) * b0 + t * bh[2])
        mc = math.hypot(mix[1], mix[2])
        mh = math.degrees(math.atan2(mix[2], mix[1])) % 360
        return describe(fit_in_gamut(mix[0], mc, mh)), f"{cls}, blended {t}"

    _no_skin_v21, _no_skin_v20, shade_v16 = _no_skin_v27_hue, _no_skin_v27_shade, blended
    try:
        return v24(portrait, gallery, trace)
    finally:
        _no_skin_v21, _no_skin_v20, shade_v16 = saved


def method_v27(portrait, gallery):
    return v27(portrait, gallery)


# ---- V28: V24's measurement with V27's blended shade -------------------------------------
#
# V26/V27's "pale pink is not skin" broke Panty (yellow -> pink), Nephis and Shiki
# Ryougi; V27's blended shade was the part that helped the pinks. V28 keeps V24's
# pixel classes and adds only the blend, optionally with the skin-shadow damping.

V28_SHADOW = False


def _v28_measure(whites):
    def run(img):
        return classify(
            img,
            reject_pale_skin=True,
            skin=_is_skin_v15,
            skin_hue=SKIN_HUE_V15,
            warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
            warm_white=WARM_WHITE if whites else None,
            warm_damp_light=SKIN_SHADOW_ZONE if V28_SHADOW else None,
        )

    return run


def v28(portrait, gallery, trace=None):
    global _no_skin_v27_hue, _no_skin_v27_shade
    saved = (_no_skin_v27_hue, _no_skin_v27_shade)
    _no_skin_v27_hue, _no_skin_v27_shade = _v28_measure(True), _v28_measure(False)
    try:
        return v27(portrait, gallery, trace)
    finally:
        _no_skin_v27_hue, _no_skin_v27_shade = saved


def method_v28(portrait, gallery):
    return v28(portrait, gallery)


# ---- V29: V28 + pale pink counts once it is stronger than a skin highlight -----------
#
# Freeing all pale pink (V26) broke Panty, Nephis and Shiki Ryougi -- at 335-352
# degrees there are skin highlights too. They are fainter than pink hair and
# clothes, so between PALE_SKIN_FROM and 335 the pale-skin rule now only removes
# pixels up to PINK_SKIN_SAT_MAX.

PINK_SKIN_SAT_MAX = 0.25


def _is_skin_v29(h, s, v):
    if v < 0.45:
        return False
    if 335 <= h < PALE_SKIN_FROM:
        return s <= PINK_SKIN_SAT_MAX
    return (h >= PALE_SKIN_FROM or h <= 38) and s <= 0.35


def _v29_measure(whites):
    def run(img):
        return classify(
            img,
            reject_pale_skin=True,
            skin=_is_skin_v29,
            skin_hue=SKIN_HUE_V15,
            warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
            warm_white=WARM_WHITE if whites else None,
            warm_damp_light=SKIN_SHADOW_ZONE,
        )

    return run


def v29(portrait, gallery, trace=None):
    global _no_skin_v27_hue, _no_skin_v27_shade, SHADE_BLEND
    saved = (_no_skin_v27_hue, _no_skin_v27_shade, SHADE_BLEND)
    _no_skin_v27_hue, _no_skin_v27_shade = _v29_measure(True), _v29_measure(False)
    SHADE_BLEND = V29_BLEND
    try:
        return v27(portrait, gallery, trace)
    finally:
        _no_skin_v27_hue, _no_skin_v27_shade, SHADE_BLEND = saved


V29_BLEND = 0.35


def method_v29(portrait, gallery):
    return v29(portrait, gallery)


# ---- V30: colour-profile paths (the owner's idea) ------------------------------------------
#
# One global rule cannot treat pale pink as both skin and identity. V30 profiles
# the character first and sends two profiles down their own path; everyone else
# gets V29 unchanged.
#
# - Monochrome (2B, A2): little of the art carries real colour. The accent is the
#   character's dominant tone with only a faint tint -- the site's frontend refuses
#   seeds below chroma 0.025, so a pure grey is not possible.
# - Pale pink (Tewi Inaba, Nadeko Sengoku, Sakurako Kawawa): the colour is almost
#   all pink/red *and* a real part of it is pale. Approved reds are just as
#   pink/red but almost never pale (2-5% against 11-30%), so the pale share is the
#   test. On this path pale pink counts as identity rather than skin, the hue is
#   kept in the pink range, and the shade leans to the brighter pixels.

MONO_MAX_CHROMATIC = 0.30
PINK_MIN_SHARE = 0.70
PINK_MIN_PALE = 0.10
PINK_RANGE = (320, 12)
PINK_BLEND = 0.75
PINK_AIM = (315, 358)  # where pale pink hair and clothes sit (HSV)
MONO_WARM = (0, 100)  # OKLCH hues ignored for the monochrome tint: skin, brown, pink
MONO_TINT = (0.03, 0.045)
MONO_DEFAULT_HUE = 250  # a hint of blue when the art has no tint of its own


def colour_profile(images):
    """Medians across images: chromatic share, pink/red share, pale share within it."""
    chrom, pink, pale_in = [], [], []
    for f in images:
        arr = np.asarray(f.convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
        arr = arr[~np.all(arr >= 0.999, axis=1)]  # painted-out background
        if len(arr) < 50:
            continue
        mx, mn = arr.max(1), arr.min(1)
        v = mx
        s = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0)
        r, g, b = arr.T
        d = np.maximum(mx - mn, 1e-9)
        h = (
            np.where(
                mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)
            )
            * 60
        )
        lit = v >= 0.15
        chrom.append(float(((s >= 0.15) & lit).sum() / len(arr)))
        ev = lit & (s >= 0.08) & ~((h >= 12) & (h <= 38))
        w = np.where(s < 0.22, 0.5, 1.0) * s * ev
        pr = (h >= PINK_RANGE[0]) | (h < PINK_RANGE[1])
        total = w.sum()
        if total > 0:
            pw = (w * pr).sum()
            pink.append(float(pw / total))
            pale_in.append(float((w * pr * (s < 0.22)).sum() / pw) if pw > 0 else 0.0)

    def med(xs):
        return sorted(xs)[len(xs) // 2] if xs else 0.0

    return {"chromatic": med(chrom), "pink": med(pink), "pale_in_pink": med(pale_in)}


def _mono_seed(images):
    """Dominant tone of the non-skin foreground, with a faint tint."""
    Ls, As, Bs, Ws = [], [], [], []
    for f in images:
        L, C, h = _to_oklch(f)
        rgb = np.asarray(f.convert("RGB")).reshape(-1, 3)
        keep = ~np.all(rgb >= 254, axis=1) & (L > 0.12) & (L < 0.97)
        keep &= ~((h >= 35) & (h <= 80) & (C >= 0.02) & (C <= 0.13) & (L > 0.55))  # skin
        if keep.sum() < 50:
            continue
        w = np.full(int(keep.sum()), 1.0 / keep.sum())
        Ls.append(L[keep])
        As.append((C * np.cos(np.radians(h)))[keep])
        Bs.append((C * np.sin(np.radians(h)))[keep])
        Ws.append(w)
    if not Ls:
        return None
    L, a, b, w = (np.concatenate(x) for x in (Ls, As, Bs, Ws))
    order = np.argsort(L)
    cum = np.cumsum(w[order])
    tone = float(np.clip(L[order][np.searchsorted(cum, cum[-1] / 2)], 0.3, 0.8))
    hue_all = np.degrees(np.arctan2(b, a)) % 360
    neutral = (np.hypot(a, b) < 0.08) & ~((hue_all >= MONO_WARM[0]) & (hue_all <= MONO_WARM[1]))
    ma = float((a[neutral] * w[neutral]).sum() / max(w[neutral].sum(), 1e-9))
    mb = float((b[neutral] * w[neutral]).sum() / max(w[neutral].sum(), 1e-9))
    tint = math.hypot(ma, mb)
    hue = math.degrees(math.atan2(mb, ma)) % 360 if tint > 0.004 else MONO_DEFAULT_HUE
    chroma = float(np.clip(tint * 3, *MONO_TINT))
    return describe(fit_in_gamut(tone, chroma, hue))


def _is_skin_pink_path(h, s, v):
    return (h >= 352 or h <= 38) and s <= 0.35 and v >= 0.45


def _pink_measure(img):
    return classify(
        img,
        reject_pale_skin=True,
        skin=_is_skin_pink_path,
        skin_hue=SKIN_HUE_V15,
        warm_damp=(*WARM_ZONE, WARM_SAT_MAX, WARM_FACTOR),
        warm_damp_light=SKIN_SHADOW_ZONE,
    )


def _pink_seed(images):
    global PALE_WEIGHT, POOL_POW
    PALE_WEIGHT, POOL_POW = 0.5, 0.5
    gm = [x for x in (measure(i, _pink_measure) for i in images) if x is not None]
    if not gm:
        return None
    entries = [(x, 1.0) for x in gm]
    # Aim where the *pale* pinks are: on this path they are the identity, and the
    # saturated evidence at 0-20 degrees is mostly skin shadow and red details.
    pale_hist = A._pool_histogram(entries, "pale")
    lo, hi = PINK_AIM
    cands = [i for i in range(A.HUE_BINS) if _in_zone((i + 0.5) * 5, lo, hi)]
    hue = (max(cands, key=lambda i: band_sum(pale_hist, (i + 0.5) * 5, 15)) + 0.5) * 5
    core, _ = shade_v15(entries, hue, V8)
    bh = bright_half(entries, hue, V8)
    if core is None or bh is None:
        return core
    r, g, b = (int(core["seed"][i : i + 2], 16) / 255 for i in (1, 3, 5))
    L, C, h = A.rgb_to_oklch(r, g, b)
    a0, b0 = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    t = PINK_BLEND
    mix = ((1 - t) * L + t * bh[0], (1 - t) * a0 + t * bh[1], (1 - t) * b0 + t * bh[2])
    mc = max(math.hypot(mix[1], mix[2]), PALE_MIN_CHROMA)
    mh = math.degrees(math.atan2(mix[2], mix[1])) % 360
    return describe(fit_in_gamut(mix[0], mc, mh))


def v30(portrait, gallery, trace=None):
    _, fg = _segmented(portrait, gallery, drop_scenes=True)
    prof = colour_profile(fg)
    tag = f"profile chromatic {prof['chromatic']:.2f} pink {prof['pink']:.2f} pale-in-pink {prof['pale_in_pink']:.2f}"
    if fg and prof["chromatic"] < MONO_MAX_CHROMATIC:
        r = _mono_seed(fg)
        if r is not None:
            if trace is not None:
                trace.append(f"monochrome path: {tag}")
            return r
    if fg and prof["pink"] >= PINK_MIN_SHARE and prof["pale_in_pink"] >= PINK_MIN_PALE:
        r = _pink_seed(fg)
        if r is not None:
            if trace is not None:
                trace.append(f"pale-pink path: {tag}")
            return r
    local: list[str] = []
    r = v29(portrait, gallery, local)
    if trace is not None:
        trace.append(f"standard path ({tag}); " + (local[0] if local else ""))
    return r


def method_v30(portrait, gallery):
    return v30(portrait, gallery)


# ---- V31: the owner's review of V30 ----------------------------------------------------------
#
# Monochrome:
# - Pick a side. The owner wants 2B and A2 to be black or white, not a bluish mid
#   grey: whichever of near-white (S < 0.15, V > 0.8) and near-black (V < 0.3)
#   covers more of the character sets the tone (Will Auceptin: white).
# - Tint only as far as the art leans. The tint's strength scales with how
#   consistently the greys lean cool (The Sandman's 94% keeps a slate; 2B's 57% is
#   no lean). A near-neutral seed needs the frontend to accept seeds under chroma
#   0.025 -- today it falls back to the site accent.
# - A strong highlight wins. Ken Kaneki is black and white with red: when one
#   saturated hue family covers >= MONO_HIGHLIGHT_COV of the character on average
#   and shows in >= MONO_HIGHLIGHT_PRESENCE of images, it becomes the accent.
#   (2B, A2 and Will stay under 1%; Kaneki's red is 4.4%.)
# Pale pink:
# - The path also needs real pale pink present: hue 315-355, S 0.15-0.45, V >= 0.7
#   covering >= PP_MIN_COV of the character (median) or appearing in >= PP_MIN_IMAGES
#   of images. Semiramis, Annie Leonhart, Himiko Toga and Evernight Goddess had none
#   -- their "pink" was warm-lit skin.
# - Shaded from a narrower band (+-15 degrees), so less skin-adjacent colour mixes in.

MONO_LIGHT_L, MONO_DARK_L = 0.93, 0.22
MONO_TINT_FROM, MONO_TINT_FULL, MONO_TINT_MAX = 0.55, 0.95, 0.045
MONO_HIGHLIGHT_COV, MONO_HIGHLIGHT_PRESENCE = 0.02, 0.15
PP_MIN_COV, PP_MIN_IMAGES = 0.008, 0.15


def _hsv_arrays(f):
    a = np.asarray(f.convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
    a = a[~np.all(a >= 0.999, axis=1)]
    mx, mn = a.max(1), a.min(1)
    d = np.maximum(mx - mn, 1e-9)
    r, g, b = a.T
    h = (
        np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
        * 60
    )
    s = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0)
    return a, h, s, mx


def pale_pink_presence(images):
    covs = []
    for f in images:
        _, h, s, v = _hsv_arrays(f)
        if len(h) < 50:
            continue
        pp = (h >= 315) & (h <= 355) & (s >= 0.15) & (s <= 0.45) & (v >= 0.7)
        covs.append(float(pp.mean()))
    if not covs:
        return 0.0, 0.0
    return float(np.median(covs)), float(np.mean([c >= 0.04 for c in covs]))


def _mono_highlight(images):
    """A saturated hue family prominent across images, as a seed; or None."""
    covs, cells = [], []
    for f in images:
        a, h, s, v = _hsv_arrays(f)
        if len(h) < 50:
            continue
        hs = (s >= 0.55) & (v >= 0.35) & ~((h >= 12) & (h <= 40))
        fam = ((h + 15) % 360 // 30).astype(int)
        covs.append(np.bincount(fam[hs], minlength=12) / len(h))
        cells.append((a[hs], h[hs], fam[hs]))
    if not covs:
        return None
    covs = np.array(covs)
    top = int(np.argmax(covs.mean(0)))
    if (
        covs.mean(0)[top] < MONO_HIGHLIGHT_COV
        or (covs[:, top] > 0.01).mean() < MONO_HIGHLIGHT_PRESENCE
    ):
        return None
    rgb = np.concatenate([c[0][c[2] == top] for c in cells])
    if len(rgb) < 50:
        return None
    img = Image.fromarray((rgb.reshape(1, -1, 3) * 255).astype(np.uint8))
    L, C, hh = _to_oklch(img)
    order = np.argsort(-C)[: max(1, len(C) // 2)]
    a_ = (C * np.cos(np.radians(hh)))[order].mean()
    b_ = (C * np.sin(np.radians(hh)))[order].mean()
    return describe(
        fit_in_gamut(
            float(L[order].mean()), math.hypot(a_, b_), math.degrees(math.atan2(b_, a_)) % 360
        )
    )


def _mono_seed_v31(images):
    light = dark = 0.0
    cool_shares, cool_ab = [], []
    for f in images:
        _, h, s, v = _hsv_arrays(f)
        if len(h) < 50:
            continue
        light += float(((s < 0.15) & (v > 0.8)).mean())
        dark += float((v < 0.3).mean())
        L, C, oh = _to_oklch(f)
        rgb = np.asarray(f.convert("RGB")).reshape(-1, 3)
        neutral = ~np.all(rgb >= 254, axis=1) & (L > 0.12) & (L < 0.97) & (C < 0.08)
        cool = neutral & ~((oh >= 0) & (oh <= 100))
        if neutral.sum() > 30:
            cool_shares.append(cool.sum() / neutral.sum())
        if cool.sum() > 30:
            cool_ab.append(
                (
                    (C * np.cos(np.radians(oh)))[cool].mean(),
                    (C * np.sin(np.radians(oh)))[cool].mean(),
                )
            )
    if not cool_shares:
        return None, "no usable pixels"
    tone = MONO_LIGHT_L if light >= dark else MONO_DARK_L
    share = float(np.mean(cool_shares))
    strength = min(1.0, max(0.0, (share - MONO_TINT_FROM) / (MONO_TINT_FULL - MONO_TINT_FROM)))
    if cool_ab and strength > 0:
        ma, mb = float(np.mean([x[0] for x in cool_ab])), float(np.mean([x[1] for x in cool_ab]))
        hue = math.degrees(math.atan2(mb, ma)) % 360
    else:
        hue = MONO_DEFAULT_HUE
    chroma = strength * MONO_TINT_MAX
    side = "white" if tone == MONO_LIGHT_L else "black"
    return describe(
        fit_in_gamut(tone, chroma, hue) if chroma > 0.005 else oklab_to_hex(tone, 0, 0)
    ), (
        f"{side} side (light {light / len(cool_shares):.2f} vs dark {dark / len(cool_shares):.2f}), "
        f"greys lean cool {share:.0%} -> tint {chroma:.3f}"
    )


def v31(portrait, gallery, trace=None):
    global V8
    _, fg = _segmented(portrait, gallery, drop_scenes=True)
    prof = colour_profile(fg)
    tag = f"profile chromatic {prof['chromatic']:.2f} pink {prof['pink']:.2f} pale-in-pink {prof['pale_in_pink']:.2f}"
    if fg and prof["chromatic"] < MONO_MAX_CHROMATIC:
        hl = _mono_highlight(fg)
        if hl is not None:
            if trace is not None:
                trace.append(f"monochrome path, highlight colour: {tag}")
            return hl
        r, why = _mono_seed_v31(fg)
        if r is not None:
            if trace is not None:
                trace.append(f"monochrome path, {why}: {tag}")
            return r
    if fg and prof["pink"] >= PINK_MIN_SHARE and prof["pale_in_pink"] >= PINK_MIN_PALE:
        cov, presence = pale_pink_presence(fg)
        if cov >= PP_MIN_COV or presence >= PP_MIN_IMAGES:
            saved = V8
            V8 = {**V8, "conf_span": 15}
            try:
                r = _pink_seed(fg)
            finally:
                V8 = saved
            if r is not None:
                if trace is not None:
                    trace.append(
                        f"pale-pink path (pale pink {cov:.3f}, in {presence:.0%} of images): {tag}"
                    )
                return r
        tag += f"; pale pink absent ({cov:.3f}, {presence:.0%}) -> not the pale-pink path"
    local: list[str] = []
    r = v29(portrait, gallery, local)
    if trace is not None:
        trace.append(f"standard path ({tag}); " + (local[0] if local else ""))
    return r


def method_v31(portrait, gallery):
    return v31(portrait, gallery)


# ---- V32: V31 with each pink shaded from its own vivid pinks ---------------------------------
#
# V31's pinks converged (#da91a3, #da92a5, #dd90a4, #dc93a6): most had their chroma
# lifted to exactly the 0.09 floor, which erased the real difference between, say,
# Mori Calliope's vivid pink and Sylveon's pastel. The pale-pink shade now comes
# from the character's own pink pixels only -- hue 320-355, pale and saturated
# together, so red and skin cannot mix in -- taking the most chromatic
# PINK_CORE share, with no floor.

PINK_ZONE = (320, 355)
PINK_CORE = 0.35
PINK_BRIGHT = True


def _pink_seed_v32(images):
    rgbs = []
    for f in images:
        a, h, s, v = _hsv_arrays(f)
        if len(h) < 50:
            continue
        sel = (h >= PINK_ZONE[0]) & (h <= PINK_ZONE[1]) & (s >= 0.15) & (v >= 0.45)
        if sel.sum() < 20:
            continue
        pix = a[sel]
        # equal weight per image: resample each image's pink pixels to a fixed count
        idx = np.linspace(0, len(pix) - 1, 400).astype(int)
        rgbs.append(pix[idx])
    if not rgbs:
        return None
    rgb = np.concatenate(rgbs)
    img = Image.fromarray((rgb.reshape(1, -1, 3) * 255).astype(np.uint8))
    L, C, hh = _to_oklch(img)
    pool = np.arange(len(C))
    if PINK_BRIGHT:
        pool = pool[np.median(L) <= L]  # pink is light: the deep shading is not the colour
    order = pool[np.argsort(-C[pool])][: max(1, int(len(pool) * PINK_CORE))]
    a_ = float((C * np.cos(np.radians(hh)))[order].mean())
    b_ = float((C * np.sin(np.radians(hh)))[order].mean())
    return describe(
        fit_in_gamut(
            float(L[order].mean()), math.hypot(a_, b_), math.degrees(math.atan2(b_, a_)) % 360
        )
    )


def v32(portrait, gallery, trace=None):
    global _pink_seed
    saved = _pink_seed
    _pink_seed = _pink_seed_v32  # v31 calls it by name
    try:
        return v31(portrait, gallery, trace)
    finally:
        _pink_seed = saved


def method_v32(portrait, gallery):
    return v32(portrait, gallery)


# ---- V33: the owner's review of V32 ----------------------------------------------------------
#
# - Monochrome tone. Light-side characters (Will Auceptin, Sora Kasugano) stay
#   near-white and neutral. Dark-side ones go back to V30's tinted mid tone, which the
#   owner preferred for Himeno, Mei Mei and Akira Asai (V32's near-black was a
#   downgrade). 2B and A2 measure the same as Mei Mei and Himeno -- dark-dominant, 57%
#   cool lean -- so their preferred white needs the override.
# - Highlight must recur. Ken Kaneki's red and Gu Yue Fang Yuan's both come mostly
#   from two images; the difference is the tail: Kaneki's red clears 1% coverage in 4
#   images, Gu Yue's in 2. The highlight now needs >= HIGHLIGHT_MIN_IMAGES such images.
# - A tie candidate must be a real colour of the gallery. Semiramis's main image
#   (lavender background) picked a lavender that exists in her gallery only as faint
#   pale tints. Candidates need saturated coverage >= TIE_MIN_COV.

HIGHLIGHT_MIN_IMAGES = 3
TIE_MIN_COV = 0.01


def v33(portrait, gallery, trace=None):
    global _mono_highlight, _mono_seed_v31, windows
    saved = (_mono_highlight, _mono_seed_v31, windows)
    base_highlight, base_seed, base_windows = saved
    _, fg = _segmented(portrait, gallery, drop_scenes=True)
    cov_of = {}

    def windows_v33(hist):
        # the gallery's saturated coverage per window, from the V29 measurement
        out = base_windows(hist)
        return [
            (c, s) for c, s in out if cov_of.get("fn", lambda _c: 1.0)(c) >= TIE_MIN_COV
        ] or out[:1]

    gm = [x for x in (measure(i, _v29_measure(True)) for i in fg) if x is not None]
    if gm:
        cov_of["fn"] = lambda c: sum(band_sum(g.hist_cov, c, WINDOW) for g in gm) / len(gm)

    def seed_v33(images):
        r, why = base_seed(images)
        if r is not None and why.startswith("white"):
            return r, why
        return _mono_seed(images), "dark side: tinted mid tone (V30)"

    _mono_highlight = lambda images: _mono_highlight_v33_with(images, base_highlight)  # noqa: E731
    _mono_seed_v31 = seed_v33
    windows = windows_v33
    try:
        return v32(portrait, gallery, trace)
    finally:
        _mono_highlight, _mono_seed_v31, windows = saved


def _mono_highlight_v33_with(images, base):
    covs = []
    for f in images:
        _, h, s, v = _hsv_arrays(f)
        if len(h) < 50:
            continue
        hs = (s >= 0.55) & (v >= 0.35) & ~((h >= 12) & (h <= 40))
        fam = ((h + 15) % 360 // 30).astype(int)
        covs.append(np.bincount(fam[hs], minlength=12) / len(h))
    if not covs:
        return None
    covs = np.array(covs)
    top = int(np.argmax(covs.mean(0)))
    if int((covs[:, top] > 0.01).sum()) < HIGHLIGHT_MIN_IMAGES:
        return None
    return base(images)


def method_v33(portrait, gallery):
    return v33(portrait, gallery)
