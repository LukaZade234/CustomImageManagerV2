"""Every extractor variant tried in docs/ACCENT.md sections 14-17.

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
    v17   v16 tuned + chroma floor for tinted pale identities     21/23, the candidate
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


def classify(img, *, gap=False, reject_pale_skin=False, skin=None, skin_hue=None, skin_val=0.6):
    """The shipped `measure_image`, with the experimental switches.

    `skin` is the pale-skin predicate used when `reject_pale_skin` is set.
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
    reason = f"clear winner {top_c:.0f}deg {top_s:.2f} vs {cands[1][0]:.0f}deg {cands[1][1]:.2f}"
    if len(cands) < 2:
        reason = "single colour"
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


def v17(portrait, gallery, trace=None):
    global PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW
    PALE_WEIGHT, POOL_POW, WINDOW, AIM_GALLERY_POW = 0.5, 0.5, 30, 2.0
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


def v18(portrait, gallery, trace=None):
    global AIM_SPAN, TIE_WITHOUT_MAIN
    AIM_SPAN, TIE_WITHOUT_MAIN = 15, "top"
    try:
        return v17(portrait, gallery, trace)
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
