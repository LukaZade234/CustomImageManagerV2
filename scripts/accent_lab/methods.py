"""Every extractor variant tried in docs/ACCENT.md sections 14-16.

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


def classify(img, *, gap=False, reject_pale_skin=False):
    """The shipped `measure_image`, with the two experimental switches."""
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
        if A.SKIN_HUE[0] <= hue <= A.SKIN_HUE[1] and 0.12 <= s <= 0.55 and v >= 0.6:
            continue
        if reject_pale_skin and s >= A.PALE_SAT_MIN and is_pale_skin(hue, s, v):
            continue
        key = (min(71, int(hue / 5)), min(19, int(s * 20)), min(19, int(v * 20)))
        if s >= A.SATURATED_SAT_MIN:
            w = s**1.6 * A._light_pref(v)
            sat_grid[key] = sat_grid.get(key, 0) + w
            st += w
            kept += 1
        elif s >= A.PALE_SAT_MIN and v >= A.PALE_VAL_MIN:
            w = s * A.PALE_VOTE_WEIGHT
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
