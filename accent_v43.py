"""The V43 accent: which colour a character is "about", from cut-out, face-parsed art.

This is the decision layer only -- no models, no database, no network. It takes
each image already prepared (`Prepared`: the 200px measurement copy, the cut-out
mask and the face parser's labels at that size, and each face's hair colour) and
returns the seed. `accent_models.py` produces the masks and labels, once per image;
`accent_extract.py` stores them and decides when to recompute.

It reproduces `scripts/accent_lab/methods.py:v43` exactly -- the candidate the owner
reviewed over nine rounds (docs/ACCENT.md, behaviour summarised in section 29) --
with every switch of that experimental chain fixed at its V43 value. The arithmetic
deliberately follows the lab's order of operations, so a seed computed here is
byte-identical to the lab's; `tests/test_accent_v43.py` holds it to that.

The shape of the decision:

1. Each gallery image is cut out (background painted white). An image whose
   cut-out missed the character, or could not separate the scene, is dropped.
2. The character's own hair (face parser) is counted twice in the colour vote; in
   an image with several faces only the face whose hair matches the character's
   solo images counts, unless the gallery is a "package deal" of the same pair.
3. A colour profile sends nearly colourless characters down a monochrome path and
   pale-pink characters down a pink path; everyone else takes the standard path:
   hue windows, the main image breaking two-colour ties, a vivid shade.
4. Never empty: fallbacks run through the main image and the gallery's tone.
"""

from __future__ import annotations

import colorsys
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

import accent_extract as A

# ---- constants (V43's settings) ---------------------------------------------------

HUE_BINS = A.HUE_BINS  # 72 bins of 5 degrees

# The cut-out
FG_MISSED = 0.03  # under this share of the frame the model missed the character
FG_SCENE = 0.85  # over it, a scene the model could not separate

# Face parser labels (siyeong0/Anime-Face-Segmentation channel order)
HAIR = 1
OWN_MIN_SOLO = 0.25  # solo images needed (share of images with a face), else a package deal
HAIR_BOOST = 1  # own hair counted this many extra times

# Pixel classes
LIGHT_LO = (0.18, 0.12)  # where the dark fade starts and its width
SKIN_HUE = (12, 38)  # skin, removed at skin saturation
SKIN_VAL = 0.6
PALE_SKIN_FROM = 352  # pale skin 352-38; 335-352 is skin only up to PINK_SKIN_SAT_MAX
PINK_SKIN_SAT_MAX = 0.25
WARM_ZONE = (10, 45)  # skin and brown: damped, not removed
WARM_SAT_MAX = 0.65
WARM_FACTOR = 0.25
WARM_DARK_V = 0.55  # dark warm pixels are damped however saturated
WARM_WHITE = (35, 70, 0.15)  # faint warm whites cast no hue vote
SKIN_SHADOW = (355, 10, 0.55)  # blush and skin shadow, damped by WARM_FACTOR

# Pooling and windows
PALE_WEIGHT = 0.5
POOL_POW = 0.5  # square-root pooling: a colour in most images beats one heavy in a few
WINDOW = 30
GREEN = (75, 170)  # HSV's wide green family
GREEN_SPAN = 45
GREEN_FLOOR = 50
AIM_GALLERY_POW = 2.0
TIE_RATIO = 1 / A.MIN_MARGIN
TIE_MIN_PRESENCE = 0.30  # a tie candidate must be in this share of images ...
PRESENCE_SHARE = 0.10  # ... holding this share of each one's colour
TIE_MIN_COV = 0.01  # and cover this much of the frame on average
MAIN_BG_WEIGHT = 0.25  # the main image's whole frame, beside its cut-out
MIN_WINDOW_SHARE = 0.15
CONF_SPAN = 22.5
MIN_COV = 0.03
CORE = 0.35
HUE_SPAN = 10
PALE_OVER_SAT = 1.5
SHADE_BLEND = 0.35
PALE_MIN_CHROMA = 0.09
PALE_LIFT_FROM = 0.035

# Colour-profile paths
MONO_MAX_CHROMATIC = 0.30
PINK_MIN_SHARE = 0.70
PINK_MIN_PALE = 0.10
PINK_RANGE = (320, 12)
PINK_ZONE = (320, 355)
PINK_CORE = 0.35
PP_MIN_COV, PP_MIN_IMAGES, PP_MIN_IMAGE_COUNT = 0.008, 0.15, 2
HIGHLIGHT_MIN_IMAGES = 3
HIGHLIGHT_MIN_MEAN = 0.01
MONO_LIGHT_L, MONO_DARK_L = 0.93, 0.22
MONO_TINT_FROM, MONO_TINT_FULL, MONO_TINT_MAX = 0.55, 0.95, 0.045
MONO_WARM = (0, 100)
MONO_TINT = (0.03, 0.045)
MONO_DEFAULT_HUE = 250
RECUR_MIN_SHARE, RECUR_PRESENCE, RECUR_TINT_MAX = 0.02, 0.85, 0.06

# ---- inputs -----------------------------------------------------------------------


@dataclass
class Prepared:
    """One image, ready to measure. Everything is at the 200px measurement size
    except `face_hair` and `n_faces`, which the face parser reads at full size."""

    rgb: np.ndarray  # (h, w, 3) uint8, composited on white
    mask: np.ndarray | None = None  # (h, w) bool cut-out, or None when not segmented
    labels: np.ndarray | None = None  # (h, w) uint8 face-parser label, 0 outside faces
    faces: np.ndarray | None = None  # (h, w) uint8 face index, 1-based
    face_hair: dict[int, np.ndarray] = field(default_factory=dict)  # face -> hair Oklab
    n_faces: int = 0


@dataclass
class Result:
    seed: dict | None  # {"seed", "hue", "chroma", "lightness"} or None
    path: str  # "standard", "monochrome", "pale-pink" or "none"
    source: str  # "gallery", "main image", "safety net" ...
    reason: str


# ---- colour helpers ----------------------------------------------------------------


def describe(seed: str | None) -> dict | None:
    if not seed:
        return None
    r, g, b = (int(seed[i : i + 2], 16) / 255 for i in (1, 3, 5))
    L, C, h = A.rgb_to_oklch(r, g, b)
    return {"seed": seed, "hue": h, "chroma": C, "lightness": L}


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


_M1 = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_M2 = np.array(
    [
        [0.2104542553, 0.793617785, -0.0040720468],
        [1.9779984951, -2.428592205, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.808675766],
    ]
)


def _oklch(px):
    """(L, C, hue) for an (n, 3) uint8 pixel array."""
    a = px.astype(np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    lab = np.cbrt(lin @ _M1.T) @ _M2.T
    L, a_, b_ = lab[:, 0], lab[:, 1], lab[:, 2]
    return L, np.hypot(a_, b_), np.degrees(np.arctan2(b_, a_)) % 360


def oklab(px_float):
    """Oklab of an (n, 3) float sRGB array in 0..1 (the hair-matching space)."""
    c = np.where(px_float <= 0.04045, px_float / 12.92, ((px_float + 0.055) / 1.055) ** 2.4)
    lms = np.cbrt(c @ _M1.T)
    return lms @ _M2.T


def _hsv(px):
    """(rgb 0..1, h, s, v, d) for an (n, 3) uint8 pixel array."""
    a = px.astype(np.float64) / 255.0
    mx, mn = a.max(1), a.min(1)
    d = mx - mn
    dd = np.maximum(d, 1e-9)
    r, g, b = a.T
    h = (
        np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4))
        * 60
    )
    s = np.where(mx > 1e-9, d / np.maximum(mx, 1e-9), 0.0)
    return a, h, s, mx, d


def _non_white(px):
    """The (n, 3) pixels that are not pure white (the painted-out background)."""
    return px[~np.all(px.astype(np.float64) / 255.0 >= 0.999, axis=1)]


def _hsv_arrays(px):
    """HSV of the non-white pixels: (rgb 0..1, h, s, v)."""
    a, h, s, v, _ = _hsv(_non_white(px))
    return a, h, s, v


def _zone(h, lo, hi):
    return (h >= lo) & (h <= hi) if lo <= hi else (h >= lo) | (h <= hi)


def _in_zone(hue, lo, hi):
    return lo <= hue <= hi if lo <= hi else (hue >= lo or hue <= hi)


def _cell_lch(hb, sb, vb):
    hue = (hb + 0.5) * 5
    s, v = (sb + 0.5) / A.SAT_STEPS, (vb + 0.5) / A.VAL_STEPS
    L, C, h = A.rgb_to_oklch(*colorsys.hsv_to_rgb(hue / 360, s, v))
    return L, C, h, s


# ---- per-image measurement ----------------------------------------------------------


class Grids:
    """One image's pixel classes (normalised per class) and hue coverage."""

    __slots__ = ("hist_cov", "pale", "saturated")

    def __init__(self, saturated, pale, hist_cov=None):
        self.saturated = saturated
        self.pale = pale
        self.hist_cov = hist_cov


def _classify(px, whites):
    """Saturated and pale grids of an (n, 3) uint8 pixel array, or None.

    whites=True is the hue measurement (faint warm whites cast no vote); False is
    the shade measurement.
    """
    _a, h, s, v, d = _hsv(px)
    keep = (v >= 0.15) & ~((v >= 0.95) & (s <= 0.15)) & (d >= 1e-9)
    keep &= ~((h >= SKIN_HUE[0]) & (h <= SKIN_HUE[1]) & (s >= 0.12) & (s <= 0.55) & (v >= SKIN_VAL))
    pale_skin = (v >= 0.45) & np.where(
        (h >= 335) & (h < PALE_SKIN_FROM),
        s <= PINK_SKIN_SAT_MAX,
        ((h >= PALE_SKIN_FROM) | (h <= 38)) & (s <= 0.35),
    )
    keep &= ~((s >= A.PALE_SAT_MIN) & pale_skin)
    sat = keep & (s >= A.SATURATED_SAT_MIN)
    pale = keep & ~sat & (s >= A.PALE_SAT_MIN) & (v >= A.PALE_VAL_MIN)
    light = np.clip((v - LIGHT_LO[0]) / LIGHT_LO[1], 0, 1) * np.clip((0.97 - v) / 0.07, 0, 1)
    w_sat = s**1.6 * light
    damp = _zone(h, *WARM_ZONE) & ((s <= WARM_SAT_MAX) | (v < WARM_DARK_V))
    w_sat = np.where(damp, w_sat * WARM_FACTOR, w_sat)
    shadow = _zone(h, SKIN_SHADOW[0], SKIN_SHADOW[1]) & (s <= SKIN_SHADOW[2]) & ~damp
    w_sat = np.where(shadow, w_sat * WARM_FACTOR, w_sat)
    if whites:
        pale &= ~(_zone(h, WARM_WHITE[0], WARM_WHITE[1]) & (s < WARM_WHITE[2]))
    w_pale = s * A.PALE_VOTE_WEIGHT
    w_pale = np.where(_zone(h, *WARM_ZONE), w_pale * WARM_FACTOR, w_pale)
    if int(sat.sum() + pale.sum()) < 24:
        return None
    k0 = np.minimum((h / 5).astype(int), 71)
    k1 = np.minimum((s * 20).astype(int), 19)
    k2 = np.minimum((v * 20).astype(int), 19)
    keys = k0 * 400 + k1 * 20 + k2

    def grid(mask, w):
        tot = float(w[mask].sum())
        if tot <= 0:
            return {}
        acc = np.bincount(keys[mask], weights=w[mask], minlength=72 * 400)
        nz = np.nonzero(acc)[0]
        return {(int(i // 400), int((i // 20) % 20), int(i % 20)): float(acc[i] / tot) for i in nz}

    sg, pg = grid(sat, w_sat), grid(pale, w_pale)
    if not sg and not pg:
        return None
    return Grids(sg, pg)


def _measure_hue(px):
    """The hue measurement plus coverage: share of all pixels per hue bin, saturated class."""
    g = _classify(px, True)
    if g is None:
        return None
    a, h, s, v, _ = _hsv(px)
    white = np.all(a >= 0.999, axis=1)
    ok = (v >= 0.15) & (s >= A.SATURATED_SAT_MIN) & ~white
    ok &= ~((h >= A.SKIN_HUE[0]) & (h <= A.SKIN_HUE[1]) & (s <= 0.55) & (v >= 0.6))
    bins = np.minimum((h / 5).astype(int), 71)
    cov = np.bincount(bins[ok], minlength=72) / len(h)
    g.hist_cov = [float(x) for x in cov]
    return g


# ---- cut-out and hair ---------------------------------------------------------------


@dataclass
class _Cut:
    """An image after the cut-out: its pixels as measured, with and without extra hair."""

    base: np.ndarray  # (n, 3) uint8, row-major: the painted cut-out (or the whole image)
    boosted: np.ndarray  # base + the own hair again + white padding to a full row
    share: float  # the scene test's share (non-white, before any extra hair)


def _painted(p: Prepared):
    """(h, w, 3) cut-out with the background painted white, or None if it missed."""
    if p.mask is None or p.mask.mean() < FG_MISSED:
        return None
    arr = p.rgb.copy()
    arr[~p.mask] = 255
    return arr


def _nonwhite_share(arr):
    return float((arr != 255).any(axis=2).mean())


def _cut(p: Prepared, own: set[int] | None, boost: bool) -> _Cut:
    arr = _painted(p)
    if arr is None:  # the cut-out missed: the whole image, measured as it is
        flat = p.rgb.reshape(-1, 3)
        return _Cut(flat, flat, _nonwhite_share(p.rgb))
    share = _nonwhite_share(arr)
    base = arr.reshape(-1, 3)
    if not boost or p.labels is None:
        return _Cut(base, base, share)
    mine = np.isin(p.faces, list(own)) if own else True
    hair = arr[(p.labels == HAIR) & p.mask & mine]
    if not len(hair):
        return _Cut(base, base, share)
    extra = np.concatenate([hair] * HAIR_BOOST)
    width = arr.shape[1]
    pad = (-len(extra)) % width
    extra = np.concatenate([extra, np.full((pad, 3), 255, arr.dtype)])
    return _Cut(base, np.concatenate([base, extra]), share)


def own_faces(images: Sequence[Prepared]) -> tuple[dict[int, set[int]], bool]:
    """Which face counts in each multi-face image, by index into `images`.

    The character's hair colour is the median of their hair in images with exactly
    one face; in an image with several faces only the nearest face is theirs. With
    too few solo images the gallery is a "package deal" and every face counts
    (returns ({}, True)).
    """
    with_faces = [p for p in images if p.n_faces > 0]
    solo = [next(iter(p.face_hair.values())) for p in with_faces if p.n_faces == 1 and p.face_hair]
    if not with_faces or len(solo) < max(2, OWN_MIN_SOLO * len(with_faces)):
        return {}, True
    ref = np.median(np.array(solo), axis=0)
    out: dict[int, set[int]] = {}
    for i, p in enumerate(images):
        if p.n_faces >= 2 and p.face_hair:
            d = {
                k: float(np.sqrt((0.5 * (c[0] - ref[0])) ** 2 + ((c[1:] - ref[1:]) ** 2).sum()))
                for k, c in p.face_hair.items()
            }
            out[i] = {min(d, key=d.get)}
    return out, False


# ---- pooling and windows ----------------------------------------------------------


def _hue_marginal(grid):
    h = [0.0] * HUE_BINS
    for (hb, _, _), w in grid.items():
        h[hb] += w
    return h


def evidence(entries):
    """Per image: saturated + PALE_WEIGHT x pale, normalised, square-root pooled."""
    pooled = [0.0] * HUE_BINS
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
        for i in range(HUE_BINS):
            pooled[i] += h[i] / t * w / wsum
    return pooled


def band_sum(hist, centre, span):
    return sum(hist[i] for i in range(HUE_BINS) if A._hue_distance((i + 0.5) * 5, centre) <= span)


def _is_green(c):
    return GREEN[0] <= c <= GREEN[1]


def _span(c):
    return max(WINDOW, GREEN_SPAN) if _is_green(c) else WINDOW


def _green_bounds(c):
    """A green window is wide, but never reaches down into blonde and orange."""
    span = max(WINDOW, GREEN_SPAN)
    return max(c - span, GREEN_FLOOR), c + span


def win_sum(hist, c):
    """Mass in the colour window centred at `c`."""
    if _is_green(c):
        lo, hi = _green_bounds(c)
        return sum(hist[i] for i in range(HUE_BINS) if lo <= (i + 0.5) * 5 <= hi)
    return band_sum(hist, c, WINDOW)


def _in_window(h, c):
    """Where the aim may land: a green window counts from GREEN_FLOOR but aims from 75."""
    if _is_green(c):
        lo, hi = _green_bounds(c)
        return max(lo, GREEN[0]) <= h <= hi
    return A._hue_distance(h, c) <= WINDOW


def _all_windows(hist):
    """[(centre_deg, share)] strongest first, windows not overlapping."""
    total = sum(hist) or 1.0
    w = [win_sum(hist, (i + 0.5) * 5) / total for i in range(HUE_BINS)]
    out: list[tuple[float, float]] = []
    for i in sorted(range(HUE_BINS), key=lambda i: -w[i]):
        c = (i + 0.5) * 5
        if all(A._hue_distance(c, o) >= _span(c) + _span(o) for o, _ in out):
            out.append((c, w[i]))
    return out


class _Gallery:
    """What the window filters need to know about the gallery."""

    def __init__(self, measured: list[Grids]):
        self.measured = measured
        self.per_image = [evidence([(g, 1.0)]) for g in measured]

    def presence(self, c):
        """Share of images where this colour holds >= PRESENCE_SHARE of the image's evidence."""
        if not self.measured:
            return 1.0
        hits = 0.0
        for ev in self.per_image:
            t = sum(ev) or 1.0
            hits += 1.0 * (win_sum(ev, c) / t >= PRESENCE_SHARE)
        return hits / len(self.measured)

    def coverage(self, c):
        return sum(band_sum(g.hist_cov, c, WINDOW) * 1.0 for g in self.measured) / len(
            self.measured
        )

    def windows(self, hist, with_coverage=True):
        out = _all_windows(hist)
        kept = [(c, s) for c, s in out if self.presence(c) >= TIE_MIN_PRESENCE]
        out = kept or out[:1]
        if not with_coverage or not self.measured:
            return out
        return [(c, s) for c, s in out if self.coverage(c) >= TIE_MIN_COV] or out[:1]


# ---- the shade ----------------------------------------------------------------------


def _peak_winner(hist):
    """Shipped peak location and margin; confidence measured as band share."""
    smooth, total = A._smooth(hist)
    if total <= 0:
        return None
    win = max(range(HUE_BINS), key=lambda i: smooth[i])
    wd = (win + 0.5) * 5
    rival = max(
        (
            smooth[i]
            for i in range(HUE_BINS)
            if A._hue_distance((i + 0.5) * 5, wd) >= A.RIVAL_SEPARATION
        ),
        default=0,
    )
    if rival > 0 and smooth[win] / rival < A.MIN_MARGIN:
        return None
    share = band_sum(hist, wd, CONF_SPAN) / sum(hist)
    if share < 0.2:
        return None
    return wd, share, smooth[win] / total


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


def _vivid_shade(grid, peak):
    """Hue pinned near the peak; L and C from the most colourful CORE of the band."""
    cells = []
    for (hb, sb, vb), w in grid.items():
        hue = (hb + 0.5) * 5
        if A._hue_distance(hue, peak) > CONF_SPAN:
            continue
        L, C, h, _s = _cell_lch(hb, sb, vb)
        cells.append((C, L, C, h, w, hue))
    if not cells:
        return None
    near = [c for c in cells if A._hue_distance(c[5], peak) <= HUE_SPAN] or cells
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
        if run >= total * CORE:
            break
    return fit_in_gamut(Lw / ww, Cw / ww, hue)


def _shade_core(entries, hue):
    """Vivid core of the saturated or the pale band, whichever carries the colour."""
    sat_total = sum(A._pool_histogram(entries, "saturated")) or 1.0
    pale_total = sum(A._pool_histogram(entries, "pale")) or 1.0
    sat_grid = A._merged_band_grid(entries, hue, CONF_SPAN, "saturated")
    pale_grid = A._merged_band_grid(entries, hue, CONF_SPAN, "pale")
    sat_share = sum(sat_grid.values()) / sat_total
    pale_share = sum(pale_grid.values()) / pale_total
    use_pale = pale_grid and (not sat_grid or pale_share >= PALE_OVER_SAT * sat_share)
    grid = pale_grid if use_pale else sat_grid
    if not grid:
        return None, "nothing in the band"
    result, cls = describe(_vivid_shade(grid, hue)), ("pale" if use_pale else "saturated")
    if cls == "saturated":
        # the shipped pale-identity rule may still claim the band
        win = _peak_winner(A._pool_histogram(entries, "saturated"))
        pale_win = A._dominant_hue(A._pool_histogram(entries, "pale"), A.MIN_CONFIDENCE, True)
        if (
            win
            and A._hue_distance(win[0], hue) <= 22.5
            and _pale_identity(entries, hue, win[2], pale_win)
        ):
            pale = A._merged_band_grid(entries, hue, CONF_SPAN, "pale")
            if pale:
                return describe(_vivid_shade(pale, hue)), "pale (shipped rule)"
    return result, cls


def _band_cells(entries, hue, span, cls, scale):
    grid = A._merged_band_grid(entries, hue, span, cls)
    total = sum(grid.values()) or 1.0
    out = []
    for (hb, sb, vb), w in grid.items():
        h = (hb + 0.5) * 5
        if A._hue_distance(h, hue) > span:
            continue
        L, C, oh, _ = _cell_lch(hb, sb, vb)
        out.append((L, C, oh, w / total * scale))
    return out


def _lab_mean(cells):
    ww = sum(c[3] for c in cells) or 1.0
    L = sum(c[0] * c[3] for c in cells) / ww
    a = sum(c[1] * math.cos(math.radians(c[2])) * c[3] for c in cells) / ww
    b = sum(c[1] * math.sin(math.radians(c[2])) * c[3] for c in cells) / ww
    return L, a, b


def _bright_half(entries, hue):
    """OKLab mean of the most chromatic half of the band's brighter-than-median pixels."""
    cells = _band_cells(entries, hue, CONF_SPAN, "saturated", 1.0)
    cells += _band_cells(entries, hue, CONF_SPAN, "pale", 0.5)
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


def _shade(entries, hue, blend=True):
    """The shade of `hue`: vivid core, blended toward the band's bright half."""
    result, cls = _shade_core(entries, hue)
    if not blend:
        return result, cls
    bh = _bright_half(entries, hue)
    if result is None or bh is None:
        return result, cls
    r, g, b = (int(result["seed"][i : i + 2], 16) / 255 for i in (1, 3, 5))
    L, C, h = A.rgb_to_oklch(r, g, b)
    a0, b0 = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    t = SHADE_BLEND
    mix = ((1 - t) * L + t * bh[0], (1 - t) * a0 + t * bh[1], (1 - t) * b0 + t * bh[2])
    mc = math.hypot(mix[1], mix[2])
    mh = math.degrees(math.atan2(mix[2], mix[1])) % 360
    return describe(fit_in_gamut(mix[0], mc, mh)), f"{cls}, blended {t}"


# ---- the standard path's decision ---------------------------------------------------


def _decide_from(entries, shade_entries, gallery: _Gallery, main=None):
    """(seed, reason) for pooled hue entries; `main` breaks a two-colour tie."""
    if not entries:
        return None, "no images"
    hist = evidence(entries)
    cands = gallery.windows(hist)
    if not cands or cands[0][1] <= 0:
        return None, "no chromatic evidence"
    top_c, top_s = cands[0]
    tied = [(c, s) for c, s in cands if s >= TIE_RATIO * top_s]
    if len(cands) < 2:
        reason = "single colour"
    else:
        reason = (
            f"clear winner {top_c:.0f}deg {top_s:.2f} vs {cands[1][0]:.0f}deg {cands[1][1]:.2f}"
        )
    if len(tied) > 1 and main is None:
        tied = tied[:1]
        reason = "two-colour tie, no main image: took the stronger side"
    if len(tied) > 1:
        # The main image chooses between the gallery's colours with its saturated
        # colour (its skin is mostly pale), and aims with its whole frame.
        ph_all = evidence([(main[-1][0], 1.0)])
        ph = A._pool_histogram(main, "saturated")
        pt = sum(ph) or 1.0
        scores = [(win_sum(ph, c) / pt, c) for c, _ in tied]
        best, chosen = max(scores)
        if best <= 0:
            return None, "two-colour tie, main image carries neither"
        gs, gt = A._smooth(hist)
        ps, pst = A._smooth(ph_all)
        near = [i for i in range(HUE_BINS) if _in_window((i + 0.5) * 5, chosen)]
        hue = (max(near, key=lambda i: (gs[i] / gt) ** AIM_GALLERY_POW * (ps[i] / pst)) + 0.5) * 5
        reason = "tie broken by main image: " + ", ".join(
            f"{c:.0f}deg {s:.2f}" for s, c in sorted(scores, reverse=True)
        )
    else:
        gs, _ = A._smooth(hist)
        near = [i for i in range(HUE_BINS) if _in_window((i + 0.5) * 5, top_c)]
        hue = (max(near, key=lambda i: gs[i]) + 0.5) * 5
    share = win_sum(hist, hue) / (sum(hist) or 1.0)
    if share < MIN_WINDOW_SHARE:
        return None, f"winning colour holds only {share:.2f}"
    wsum = sum(w for _, w in entries)
    cov = sum(band_sum(g.hist_cov, hue, CONF_SPAN) * w for g, w in entries) / wsum
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
    if cov < MIN_COV and pale_share < 0.25:
        return None, f"too little of the art wears it (coverage {cov:.3f})"
    result, cls = _shade(shade_entries, hue)
    return result, f"{reason}; {hue:.0f}deg shaded from {cls}"


# ---- colour profile and its paths ---------------------------------------------------


def colour_profile(images: list[np.ndarray]) -> dict:
    """Medians across images: chromatic share, pink/red share, pale share within it."""
    chrom, pink, pale_in = [], [], []
    for px in images:
        arr = _non_white(px).astype(np.float64) / 255.0
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


def _highlight(images: list[np.ndarray]):
    """A saturated hue family that recurs across images, as a seed; or None."""
    covs, cells = [], []
    for px in images:
        a, h, s, v = _hsv_arrays(px)
        if len(h) < 50:
            continue
        hs = (s >= 0.55) & (v >= 0.35) & ~((h >= 12) & (h <= 40))
        fam = ((h + 15) % 360 // 30).astype(int)
        covs.append(np.bincount(fam[hs], minlength=12) / len(h))
        cells.append((a[hs], fam[hs]))
    if not covs:
        return None
    covs = np.array(covs)
    top = int(np.argmax(covs.mean(0)))
    n_clear, n = int((covs[:, top] > 0.01).sum()), len(covs)
    if not (n_clear >= HIGHLIGHT_MIN_IMAGES or (n_clear >= 2 and n_clear / max(n, 1) >= 0.5)):
        return None
    if covs[:, top].mean() < HIGHLIGHT_MIN_MEAN:
        return None
    rgb = np.concatenate([c[0][c[1] == top] for c in cells])
    if len(rgb) < 50:
        return None
    L, C, hh = _oklch((rgb * 255).astype(np.uint8))
    order = np.argsort(-C)[: max(1, len(C) // 2)]
    a_ = (C * np.cos(np.radians(hh)))[order].mean()
    b_ = (C * np.sin(np.radians(hh)))[order].mean()
    return describe(
        fit_in_gamut(
            float(L[order].mean()), math.hypot(a_, b_), math.degrees(math.atan2(b_, a_)) % 360
        )
    )


def _mono_side(images: list[np.ndarray]):
    """Near-white or near-black, tinted only as far as the greys lean cool."""
    light = dark = 0.0
    cool_shares, cool_ab = [], []
    for px in images:
        _, h, s, v = _hsv_arrays(px)
        if len(h) < 50:
            continue
        light += float(((s < 0.15) & (v > 0.8)).mean())
        dark += float((v < 0.3).mean())
        L, C, oh = _oklch(px)
        neutral = ~np.all(px >= 254, axis=1) & (L > 0.12) & (L < 0.97) & (C < 0.08)
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


def _mono_tone(images: list[np.ndarray]):
    """Dominant tone of the non-skin figure with a faint tint (the dark side's answer)."""
    Ls, As, Bs, Ws = [], [], [], []
    for px in images:
        L, C, h = _oklch(px)
        keep = ~np.all(px >= 254, axis=1) & (L > 0.12) & (L < 0.97)
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


def _mono_seed(images: list[np.ndarray]):
    """White side: near-white. Dark side: the tinted mid tone."""
    r, why = _mono_side(images)
    if r is not None and why.startswith("white"):
        return r, why
    return _mono_tone(images), "dark side: tinted mid tone (V30)"


def _pale_pink_presence(images: list[np.ndarray]):
    covs = []
    for px in images:
        _, h, s, v = _hsv_arrays(px)
        if len(h) < 50:
            continue
        pp = (h >= 315) & (h <= 355) & (s >= 0.15) & (s <= 0.45) & (v >= 0.7)
        covs.append(float(pp.mean()))
    if not covs:
        return 0.0, 0.0, 0
    hits = [c >= 0.04 for c in covs]
    return float(np.median(covs)), float(np.mean(hits)), int(sum(hits))


def _pink_seed(images: list[np.ndarray]):
    """The character's own lighter pinks (320-355), the most chromatic PINK_CORE of them."""
    rgbs = []
    for px in images:
        a, h, s, v = _hsv_arrays(px)
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
    L, C, hh = _oklch((rgb * 255).astype(np.uint8))
    pool = np.arange(len(C))
    pool = pool[np.median(L) <= L]  # pink is light: the deep shading is not the colour
    order = pool[np.argsort(-C[pool])][: max(1, int(len(pool) * PINK_CORE))]
    a_ = float((C * np.cos(np.radians(hh)))[order].mean())
    b_ = float((C * np.sin(np.radians(hh)))[order].mean())
    return describe(
        fit_in_gamut(
            float(L[order].mean()), math.hypot(a_, b_), math.degrees(math.atan2(b_, a_)) % 360
        )
    )


def _recurring_tint(gallery: Sequence[Prepared]):
    """(OKLCH hue, strength, presence) of a non-warm hue family in nearly every image, or None.

    Read on the cut-out where it separates and on the whole image where it does not
    (Gon's forests), and required on the character in at least one cut-out.
    """
    shares, on_char, cells = [], [], []
    for p in gallery:
        # a cut-out that missed leaves the image unpainted; it is then judged whole
        arr = _painted(p)
        if arr is None:
            arr = p.rgb
        whole = _nonwhite_share(arr) > FG_SCENE
        px = (p.rgb if whole else arr).reshape(-1, 3)
        a, h, s, v = _hsv_arrays(px)
        if len(h) < 50:
            continue
        col = (s >= 0.10) & (v >= 0.15) & (h > 50)
        fam = ((h + 15) % 360 // 30).astype(int)
        share = np.bincount(fam[col], minlength=12) / len(h)
        shares.append(share)
        on_char.append(None if whole else share)
        cells.append((a[col], fam[col]))
    if len(shares) < 2:
        return None
    shares = np.array(shares)
    presence = (shares >= RECUR_MIN_SHARE).mean(0)
    ok = presence >= RECUR_PRESENCE
    if not ok.any():
        return None
    top = int(np.argmax(np.where(ok, shares.mean(0), -1)))
    if not any(c is not None and c[top] >= RECUR_MIN_SHARE for c in on_char):
        return None
    rgb = np.concatenate([c[0][c[1] == top] for c in cells])
    if len(rgb) < 50:
        return None
    _, C, hh = _oklch((rgb * 255).astype(np.uint8))
    hue = (
        math.degrees(
            math.atan2((C * np.sin(np.radians(hh))).sum(), (C * np.cos(np.radians(hh))).sum())
        )
        % 360
    )
    strength = min(1.0, max(0.0, (presence[top] - 0.8) / 0.2))
    return hue, strength, float(presence[top])


# ---- the whole decision -------------------------------------------------------------


def decide(portrait: Prepared | None, gallery: Sequence[Prepared]) -> Result:
    """The V43 accent for one character: its main image (or None) and its gallery."""
    images = ([portrait] if portrait is not None else []) + list(gallery)
    owners, _package_deal = own_faces(images)
    offset = 1 if portrait is not None else 0

    cuts: list[_Cut] = []
    for i, p in enumerate(gallery):
        c = _cut(p, owners.get(i + offset), boost=True)
        if c.share <= FG_SCENE:
            cuts.append(c)
    fp = _cut(portrait, owners.get(0), boost=True) if portrait is not None else None
    plain = [c.base for c in cuts]

    measured = [(_measure_hue(c.boosted), _classify(c.base, False)) for c in cuts]
    hue_only = [m for m, _ in measured if m is not None]
    pairs = [(a, b) for a, b in measured if a is not None and b is not None]
    gal = _Gallery(hue_only)

    prof = colour_profile(plain)
    tag = (
        f"profile chromatic {prof['chromatic']:.2f} pink {prof['pink']:.2f}"
        f" pale-in-pink {prof['pale_in_pink']:.2f}"
    )

    result = _profile_paths(cuts, plain, prof, tag)
    if result is None:
        result = _standard(portrait, fp, pairs, gal, tag)
    if result.seed is None and portrait is not None:
        seed = _main_dominant(portrait, fp, gal)
        if seed is not None:
            result = Result(
                seed,
                "standard",
                "safety net",
                f"{result.reason}; safety net: main image's dominant colour",
            )
    if result.seed is None and cuts:
        seed, how = _mono_side(plain)
        if seed is None or not how.startswith("white"):
            seed = _mono_tone(plain)
        result = Result(
            seed,
            "standard",
            "safety net",
            f"{result.reason}; safety net: the gallery's monochrome tone",
        )

    # A monochrome character whose art carries one colour in nearly every image (Gon's
    # green) takes it as a tint.
    if result.seed is not None and result.path == "monochrome" and "highlight" not in result.reason:
        t = _recurring_tint(gallery)
        if t is not None:
            hue, strength, presence = t
            chroma = strength * RECUR_TINT_MAX
            if chroma > result.seed["chroma"]:
                result = Result(
                    describe(fit_in_gamut(result.seed["lightness"], chroma, hue)),
                    result.path,
                    result.source,
                    f"{result.reason}; a colour recurs in {presence:.0%} of images"
                    f" -> tint {chroma:.3f} at {hue:.0f}deg",
                )
    return result


def _profile_paths(cuts, plain, prof, tag):
    if not cuts:
        return None
    if prof["chromatic"] < MONO_MAX_CHROMATIC:
        hl = _highlight(plain)
        if hl is not None:
            return Result(hl, "monochrome", "gallery", f"monochrome path, highlight colour: {tag}")
        r, why = _mono_seed(plain)
        if r is not None:
            return Result(r, "monochrome", "gallery", f"monochrome path, {why}: {tag}")
    if prof["pink"] >= PINK_MIN_SHARE and prof["pale_in_pink"] >= PINK_MIN_PALE:
        cov, presence, n_pp = _pale_pink_presence(plain)
        if cov >= PP_MIN_COV or (presence >= PP_MIN_IMAGES and n_pp >= PP_MIN_IMAGE_COUNT):
            r = _pink_seed(plain)
            if r is not None:
                return Result(
                    r,
                    "pale-pink",
                    "gallery",
                    f"pale-pink path (pale pink {cov:.3f}, in {presence:.0%} of images): {tag}",
                )
    return None


def _standard(portrait, fp, pairs, gal, tag):
    whole = _measure_hue(portrait.rgb.reshape(-1, 3)) if portrait is not None else None
    whole_shade = _classify(portrait.rgb.reshape(-1, 3), False) if portrait is not None else None
    seg_p = _measure_hue(fp.boosted) if fp is not None else None
    seg_p_shade = _classify(fp.base, False) if fp is not None else None
    n = len(pairs)
    share = A._portrait_share(n)
    hue_entries = [(a, 1.0) for a, _ in pairs]
    shade_entries = [(b, 1.0) for _, b in pairs]
    if seg_p is not None and seg_p_shade is not None and 0 < share < 1 and n:
        wt = share / (1 - share) * n
        hue_entries.append((seg_p, wt))
        shade_entries.append((seg_p_shade, wt))
    main = None
    if seg_p is not None and whole is not None:
        main = [(seg_p, 1.0), (whole, MAIN_BG_WEIGHT)]
    elif whole is not None:
        main = [(whole, 1.0)]
    seed, reason = _decide_from(hue_entries, shade_entries, gal, main)
    source = "gallery"
    if seed is None and whole is not None:
        fb, why = _decide_from([(whole, 1.0)], [(whole_shade, 1.0)], gal, None)
        if fb is not None:
            seed, source, reason = fb, "main image (fallback)", f"{reason}; fallback: {why}"
    if (
        seed is not None
        and "pale" in reason.rsplit("shaded from", 1)[-1]
        and PALE_LIFT_FROM <= seed["chroma"] < PALE_MIN_CHROMA
    ):
        seed = describe(fit_in_gamut(seed["lightness"], PALE_MIN_CHROMA, seed["hue"]))
        reason += f"; chroma lifted to {PALE_MIN_CHROMA}"
    return Result(seed, "standard", source, f"standard path ({tag}); {source}: {reason}")


def _main_dominant(portrait, fp, gal):
    """The main image's dominant colour, cut-out first, with no minimum coverage."""
    seg_p, whole = _measure_hue(fp.boosted), _measure_hue(portrait.rgb.reshape(-1, 3))
    seg_s, whole_s = _classify(fp.base, False), _classify(portrait.rgb.reshape(-1, 3), False)
    hue_e = [(g, w) for g, w in ((seg_p, 1.0), (whole, MAIN_BG_WEIGHT)) if g is not None]
    shade_e = [(g, w) for g, w in ((seg_s, 1.0), (whole_s, MAIN_BG_WEIGHT)) if g is not None]
    if not hue_e or not shade_e:
        return None
    hist = evidence(hue_e)
    cands = gal.windows(hist, with_coverage=False)
    if not cands or cands[0][1] <= 0:
        return None
    result, _ = _shade(shade_e, cands[0][0], blend=False)
    return result
