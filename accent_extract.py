"""The colour a character is "about", measured on the server.

Naive approaches all fail on anime art. An average colour returns mud. The most
common colour returns the background. A portrait is mostly three large flat
regions -- paper-white background, skin, and black line work -- and none of
them is what a person means when they say "Miku is teal". So the regions that
cannot be an accent are rejected outright, and what survives is ranked by
chromatic presence rather than by area.

Two lessons the first (browser-side) implementation learned the hard way:

*One portrait is not enough.* Some characters are drawn by their community in
a colour the reference portrait does not carry at all -- Audrey Hall's canon
art is blonde and cream with a red accent, and her eyes are the only green
pixel in it, yet her fan art is green without exception. Per-image "confident
winner" votes were tried and rejected too few images to matter (25 of Audrey's
28 thumbnails declined individually while their winning hues said green almost
unanimously). What works is pooling: every image contributes a *normalised*
hue histogram -- equal weight per image, so resolution and crop cannot bias --
and the confidence and margin decisions are made once, on the pool, where
per-image noise has averaged out.

*Saturated is not the same as identifying.* Lucy (Cyberpunk: Edgerunners) is
read by the eye as a pale blue-white -- that is her hair, present in every
image -- while the saturated blue of her backgrounds wins any
saturation-only ranking. Pixels are therefore sorted into two classes,
saturated and pale, and when the pale class carries the winning hue band too,
the seed is taken from it. This follows Vibrant.js, which treats a "light
muted" swatch as a first-class candidate, and Material Color Utilities, whose
score ranks by population as much as chroma rather than by chroma alone.

The winner is still declined outright when the artwork is honestly
two-coloured or greyscale: a colour decided by rounding noise is worse than
the system accent. Roughly one character in twenty declines.

Only the seed colour is computed here. Turning it into the eight contrast-
fitted CSS tokens is a display concern and stays in the frontend
(`frontend/src/utils/accentFromImage.js`).
"""

from __future__ import annotations

import colorsys
import io
import math
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from PIL import Image

import logs
import thumbnails
from remote_images import (
    MAX_FILE_SIZE,
    _allowed_portrait_url,
    _get_with_validated_redirects,
)

log = logs.get(__name__)

HUE_BINS = 72  # 5 degrees per bin
SAT_STEPS = 20  # 0.05 per step
VAL_STEPS = 20
SAMPLE_MAX_SIDE = 200

# Anime skin sits in this hue band. It is a large flat region in almost every
# portrait, so without an explicit rejection it wins on area alone.
SKIN_HUE = (12, 48)

# The pale class: tinted-but-soft pixels the saturated floor rejects. Lower
# than the old 0.22 cutoff but above the paper-white background's ~0.04.
SATURATED_SAT_MIN = 0.22
PALE_SAT_MIN = 0.05
PALE_VAL_MIN = 0.5
# Pale pixels carry less chromatic signal each, so within one image a pale
# pixel counts for less than a saturated one. Between images both classes are
# normalised to 1 anyway; this only shapes a single image's pale histogram.
PALE_VOTE_WEIGHT = 0.5

# Below this share of pooled weight the winning hue is not a decision, it is
# noise, and the character keeps the system accent.
MIN_CONFIDENCE = 0.05
# An OKLCH chroma this low is a grey wearing a hue label.
MIN_CHROMA = 0.025

# Some characters are honestly two-coloured -- Nico Robin's art peaks on blue
# and orange within a percent of each other. When the top two hues are that
# close the winner is decided by rounding noise rather than by the artwork,
# and those characters get the system accent instead.
RIVAL_SEPARATION = 60
MIN_MARGIN = 1.25

# Enough images to detect overwhelming agreement without decoding a 256-image
# gallery on a request; evenly spaced so the sample does not depend on where
# the gallery happens to start.
POOL_SAMPLE_CAP = 60

# The pale class only becomes the identity under two narrow conditions.
#
# One: it is far more coherent than the saturated pool and both point at the
# same hue -- a pale identity that agrees with itself where the saturated
# content is scattered neon.
#
# Two: the saturated decision is weak (confidence barely over the floor, the
# signature of backgrounds and props rather than a character) while the
# winning hue band carries a large share of pale mass -- the soft tint that is
# present in every image because it is her hair. Lucy (Cyberpunk: Edgerunners)
# is the case: her saturated pool is scattered neon at 5% confidence, her
# blue-white hair is the one colour every image agrees on. Miku's teal clears
# the confidence bar comfortably and keeps its saturated seed; Reimu's pale
# skies sit in a band her red does not win.
PALE_CONF_MULT = 2.0
PALE_AGREEMENT = 60
PALE_REP_MIN_SHARE = 0.4
PALE_REP_MAX_SAT_CONF = 0.07

# Percentiles, not means: a mean returns a region's shadow.
SAT_PERCENTILE = 0.6
VAL_PERCENTILE = 0.55
# +/- degrees around the winning hue considered "the same colour".
BAND_SPAN = 22.5

# Smoothing for the hue histogram: sigma in bins (8 degrees), truncated.
_SMOOTH_SIGMA = 1.6
_SMOOTH_RADIUS = 5


def _clamp(n, lo, hi):
    return min(hi, max(lo, n))


def _light_pref(v):
    """1 across the usable lightness range, fading to 0 at both extremes."""
    lo = _clamp((v - 0.18) / 0.12, 0.0, 1.0)
    hi = _clamp((0.97 - v) / 0.07, 0.0, 1.0)
    return lo * hi


def _hue_distance(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


# ---- colour spaces ----------------------------------------------------------
# The same OKLCH maths the frontend uses to fit contrast; duplicated rather
# than shared because the two runtimes share nothing else, and because the
# server only ever needs rgb->oklch (the chroma floor), never the reverse.


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_oklch(r, g, b):
    lr, lg, lb = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    l_cone = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3)
    m_cone = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3)
    s_cone = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3)
    L = 0.2104542553 * l_cone + 0.793617785 * m_cone - 0.0040720468 * s_cone
    A = 1.9779984951 * l_cone - 2.428592205 * m_cone + 0.4505937099 * s_cone
    B = 0.0259040371 * l_cone + 0.7827717662 * m_cone - 0.808675766 * s_cone
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


# ---- per-image measurement ---------------------------------------------------

# A grid cell is (hue_bin, sat_step, val_step) -> weight. Hue marginals of the
# grid are the histogram; the cells themselves are what the representative
# colour's percentiles are read from. Quantising at measurement time (5 degrees
# x 0.05 x 0.05) keeps an image's contribution to the pool O(bins) instead of
# O(pixels), so a 60-image pool fits in a dict.


class ImageGrids:
    """One image's normalised contribution to the pool."""

    __slots__ = ("saturated", "pale")

    def __init__(self, saturated: dict, pale: dict):
        self.saturated = saturated
        self.pale = pale


def measure_image(img: Image.Image) -> ImageGrids | None:
    """Classify every pixel of an (already composited, RGB) image.

    Returns None when the image carries no chromatic signal at all -- flat or
    greyscale art -- which makes it contribute nothing rather than dilute.
    """
    img = img.convert("RGB")
    sat_grid: dict[tuple[int, int, int], float] = {}
    pale_grid: dict[tuple[int, int, int], float] = {}
    sat_total = 0.0
    pale_total = 0.0
    kept = 0

    for r8, g8, b8 in img.getdata():
        r, g, b = r8 / 255, g8 / 255, b8 / 255
        mx = max(r, g, b)
        mn = min(r, g, b)
        d = mx - mn
        sat = d / mx if mx > 1e-9 else 0.0
        val = mx

        if val < 0.15:  # line work and deep shadow
            continue
        if val >= 0.95 and sat <= 0.15:  # blown-out background
            continue
        if d < 1e-9:
            continue

        hue, s, v = colorsys.rgb_to_hsv(r, g, b)
        hue *= 360

        is_skin = (
            SKIN_HUE[0] <= hue <= SKIN_HUE[1] and 0.12 <= s <= 0.55 and v >= 0.6
        )
        if is_skin:
            continue

        if s >= SATURATED_SAT_MIN:
            # Chroma carries the signal, so saturation dominates. Lightness is
            # a flat window with soft edges rather than a preference curve: a
            # near-black or near-white cannot serve as an accent, but a deep
            # forest-green dress is exactly the identifying colour of the
            # character wearing it, and a Gaussian centred on mid-lightness
            # would vote for her blonde hair over it every time.
            w = s**1.6 * _light_pref(v)
            key = (
                _clamp(int(hue / 360 * HUE_BINS), 0, HUE_BINS - 1),
                _clamp(int(s * SAT_STEPS), 0, SAT_STEPS - 1),
                _clamp(int(v * VAL_STEPS), 0, VAL_STEPS - 1),
            )
            sat_grid[key] = sat_grid.get(key, 0.0) + w
            sat_total += w
            kept += 1
        elif s >= PALE_SAT_MIN and v >= PALE_VAL_MIN:
            w = s * PALE_VOTE_WEIGHT
            key = (
                _clamp(int(hue / 360 * HUE_BINS), 0, HUE_BINS - 1),
                _clamp(int(s * SAT_STEPS), 0, SAT_STEPS - 1),
                _clamp(int(v * VAL_STEPS), 0, VAL_STEPS - 1),
            )
            pale_grid[key] = pale_grid.get(key, 0.0) + w
            pale_total += w
            kept += 1

    if kept < 24:
        return None

    # Normalised per image and per class: this is what makes the pool immune to
    # resolution and crop, and what lets the pale class stand beside the
    # saturated one despite carrying far fewer raw pixels.
    sat_grid = {k: w / sat_total for k, w in sat_grid.items()} if sat_total > 0 else {}
    pale_grid = {k: w / pale_total for k, w in pale_grid.items()} if pale_total > 0 else {}
    if not sat_grid and not pale_grid:
        return None
    return ImageGrids(sat_grid, pale_grid)


# ---- pooling and the decision ------------------------------------------------


def _pool_histogram(grids: Iterable[tuple[ImageGrids, float]], attr: str) -> list[float]:
    """One class's hue histogram over the pool, one normalised image at a time."""
    hist = [0.0] * HUE_BINS
    for g, weight in grids:
        for (hb, _, _), w in getattr(g, attr).items():
            hist[hb] += w * weight
    return hist


def _smooth(hist: Sequence[float]) -> tuple[list[float], float]:
    smooth = [0.0] * HUE_BINS
    total = 0.0
    for i in range(HUE_BINS):
        acc = 0.0
        for j in range(-_SMOOTH_RADIUS, _SMOOTH_RADIUS + 1):
            acc += hist[(i + j) % HUE_BINS] * math.exp(-(j * j) / (2 * _SMOOTH_SIGMA**2))
        smooth[i] = acc
        total += acc
    return smooth, total


def _dominant_hue(
    hist: Sequence[float], min_confidence: float, require_margin: bool
) -> tuple[float, float] | None:
    """Winning hue and its confidence, or None when there is no confident winner."""
    smooth, total = _smooth(hist)
    if total <= 0:
        return None
    win = max(range(HUE_BINS), key=lambda i: smooth[i])
    confidence = smooth[win] / total
    if confidence < min_confidence:
        return None
    win_deg = (win + 0.5) * (360 / HUE_BINS)
    if require_margin:
        rival = 0.0
        for i in range(HUE_BINS):
            deg = (i + 0.5) * (360 / HUE_BINS)
            if _hue_distance(deg, win_deg) < RIVAL_SEPARATION:
                continue
            rival = max(rival, smooth[i])
        if rival > 0 and smooth[win] / rival < MIN_MARGIN:
            return None
    return win_deg, confidence


def _grid_percentile(cells: list[tuple[float, float]], q: float) -> float:
    """Weighted percentile over (centre_value, weight) pairs."""
    total = sum(w for _, w in cells)
    if total <= 0:
        return 0.0
    run = 0.0
    for value, w in sorted(cells):
        run += w
        if run >= total * q:
            return value
    return cells[-1][0] if cells else 0.0


def _representative(grid: dict, centre: float, span: float) -> tuple[float, float, float] | None:
    """(hue, sat, val) of a grid's mass within `span` degrees of `centre`."""
    cells: list[tuple[float, float, float, float]] = []  # hue, sat, val, weight
    for (hb, sb, vb), w in grid.items():
        hue = (hb + 0.5) * (360 / HUE_BINS)
        if _hue_distance(hue, centre) > span:
            continue
        cells.append((hue, (sb + 0.5) / SAT_STEPS, (vb + 0.5) / VAL_STEPS, w))
    if not cells:
        return None
    sum_sin = sum(math.sin(math.radians(h)) * w for h, _, _, w in cells)
    sum_cos = sum(math.cos(math.radians(h)) * w for h, _, _, w in cells)
    hue = math.degrees(math.atan2(sum_sin, sum_cos)) % 360
    sat = _grid_percentile([(s, w) for _, s, _, w in cells], SAT_PERCENTILE)
    val = _grid_percentile([(v, w) for _, _, v, w in cells], VAL_PERCENTILE)
    return hue, sat, val


def _merged_band_grid(
    entries: Iterable[tuple[ImageGrids, float]], centre: float, span: float, attr: str
) -> dict:
    merged: dict[tuple[int, int, int], float] = {}
    for g, weight in entries:
        for key, w in getattr(g, attr).items():
            hue = (key[0] + 0.5) * (360 / HUE_BINS)
            if _hue_distance(hue, centre) > span + 10:
                continue
            merged[key] = merged.get(key, 0.0) + w * weight
    return merged


def _seed_from_representative(rep) -> dict | None:
    hue, sat, val = rep
    r, g, b = colorsys.hsv_to_rgb(hue / 360, _clamp(sat, 0, 1), _clamp(val, 0, 1))
    L, C, h = rgb_to_oklch(r, g, b)
    if C < MIN_CHROMA:
        return None
    seed = f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"
    return {"seed": seed, "hue": h, "chroma": C, "lightness": L}


def _decide_from(entries: Sequence[tuple[ImageGrids, float]]) -> dict | None:
    """The seed for one set of images (a gallery, or a lone portrait).

    The saturated pool decides first: it is the intentional colour of the art.
    The pale pool gets to take the seed only under the narrow conditions in
    PALE_CONF_MULT -- a pale identity that is coherent where the saturated
    content is scattered, pointing at the same hue. When the saturated pool
    declines outright (two-colour or greyscale art), a confident pale pool is
    still an answer: some characters are nothing but soft tints.
    """
    if not entries:
        return None

    sat_win = _dominant_hue(_pool_histogram(entries, "saturated"), MIN_CONFIDENCE, True)
    pale_win = _dominant_hue(_pool_histogram(entries, "pale"), MIN_CONFIDENCE, True)

    if sat_win is not None:
        hue, confidence = sat_win
        sat_mass = sum(_merged_band_grid(entries, hue, BAND_SPAN, "saturated").values())
        pale_band = _merged_band_grid(entries, hue, BAND_SPAN, "pale")
        pale_mass = sum(pale_band.values())
        pale_identity = False
        if pale_mass > 0:
            share = pale_mass / (pale_mass + sat_mass)
            coherent = (
                pale_win is not None
                and _hue_distance(pale_win[0], hue) <= PALE_AGREEMENT
                and pale_win[1] >= PALE_CONF_MULT * confidence
            )
            weak_sat = share >= PALE_REP_MIN_SHARE and confidence < PALE_REP_MAX_SAT_CONF
            pale_identity = coherent or weak_sat
        attr = "pale" if pale_identity else "saturated"
    elif pale_win is not None:
        hue = pale_win[0]
        attr = "pale"
    else:
        return None

    rep = _representative(_merged_band_grid(entries, hue, BAND_SPAN, attr), hue, BAND_SPAN)
    result = _seed_from_representative(rep) if rep is not None else None
    if result is None and attr == "pale":
        # A pale identity too grey to seed (chroma floor) is not a reason to
        # decline the character outright; the saturated band still holds a
        # colour, just a louder one than the art's true identity.
        rep = _representative(_merged_band_grid(entries, hue, BAND_SPAN, "saturated"), hue, BAND_SPAN)
        result = _seed_from_representative(rep) if rep is not None else None
    return result


def decide(
    portrait: ImageGrids | None,
    gallery: Sequence[ImageGrids],
) -> dict | None:
    """The seed colour for one character, or None when the art declines.

    The gallery decides when there is one: it is the community's consensus on
    what colour this character is, and it is where characters like Audrey Hall
    live -- her canon portrait is blonde and cream with a red accent, her eyes
    the only green pixel in it, while her fan art wears the green dress
    without exception. The portrait is the fallback for characters with no
    gallery yet, and the last resort for galleries too small or too scattered
    to decide.

    `portrait` may be None (no portrait, or an unreadable one) and `gallery`
    may be empty; either alone can carry the answer.
    """
    result = _decide_from([(g, 1.0) for g in gallery])
    if result is not None:
        result["source"] = "gallery"
        return result
    if portrait is not None:
        result = _decide_from([(portrait, 1.0)])
        if result is not None:
            result["source"] = "portrait"
            return result
    return None


# ---- image loading ------------------------------------------------------------


def load_local_image(path: str | os.PathLike) -> Image.Image | None:
    """Open, downsample and composite-on-white, the way measurement wants it."""
    try:
        with Image.open(path) as img:
            return _prepare(img)
    except Exception:
        return None


def load_image_bytes(raw: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            return _prepare(img)
    except Exception:
        return None


def _prepare(img: Image.Image) -> Image.Image:
    # Transparent PNGs must resolve against white, the surface the portrait
    # sits on in the page, or every transparent pixel reads as black and drags
    # the whole measurement dark.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    img.thumbnail((SAMPLE_MAX_SIDE, SAMPLE_MAX_SIDE), Image.LANCZOS)
    return img


def fetch_portrait_bytes(main_image_url: str) -> bytes | None:
    """Raw bytes of a character's portrait, fetched remotely. None on any failure."""
    if not main_image_url:
        return None
    if not main_image_url.startswith(("http://", "https://")):
        return None
    if not _allowed_portrait_url(main_image_url):
        return None
    try:
        response = _get_with_validated_redirects(main_image_url, timeout=30, allow_redirects=False)
        if response.status_code != 200 or len(response.content) > MAX_FILE_SIZE:
            return None
        return response.content
    except Exception as e:
        log.warning(
            "accent.portrait_fetch_failed", url=main_image_url, error=f"{type(e).__name__}: {e}"
        )
        return None


def evenly_sample(rows: Sequence, cap: int) -> list:
    """`cap` entries spread evenly across `rows` (matches the old client sampler)."""
    if len(rows) <= cap:
        return list(rows)
    step = len(rows) / cap
    return [rows[int(i * step)] for i in range(cap)]


def extract_seed(
    portrait_url: str | None,
    gallery_thumb_paths: Sequence[Path],
) -> dict | None:
    """Measure one character: portrait URL plus the thumbnail paths on disk.

    Returns the `decide()` result dict, or None. Whether some thumbnails were
    missing is the caller's bookkeeping (`accent_partial`), not this
    function's: it measures exactly what it was given.
    """
    portrait_grids = None
    if portrait_url:
        raw = fetch_portrait_bytes(portrait_url)
        if raw is not None:
            img = load_image_bytes(raw)
            if img is not None:
                portrait_grids = measure_image(img)

    gallery_grids: list[ImageGrids] = []
    for path in gallery_thumb_paths:
        img = load_local_image(path)
        if img is None:
            continue
        g = measure_image(img)
        if g is not None:
            gallery_grids.append(g)

    if portrait_grids is None and not gallery_grids:
        return None
    return decide(portrait_grids, gallery_grids)


# ---- database orchestration ---------------------------------------------------


def gallery_fingerprint(char_name: str) -> tuple[int, str | None, list[int]]:
    """(count, newest added_at, ordered image ids) of the active thumbnailable gallery."""
    import db

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT i.id AS id, i.url AS url, i.added_at AS added_at"
        "  FROM custom_images i JOIN characters c ON c.id = i.character_id"
        " WHERE c.name = ? AND i.state = 'active'"
        " ORDER BY i.position, i.id",
        (char_name,),
    ).fetchall()
    rows = [r for r in rows if thumbnails.is_thumbnailable(r["url"])]
    latest = max((r["added_at"] or "" for r in rows), default=None)
    return len(rows), (latest or None), [int(r["id"]) for r in rows]


def accent_state(char_name: str) -> dict | None:
    import db

    conn = db.get_connection()
    row = conn.execute(
        "SELECT accent_seed, accent_hue, accent_gallery_count, accent_gallery_latest,"
        "       accent_portrait_url, accent_partial, accent_updated_at, main_image_url"
        "  FROM characters WHERE name = ?",
        (char_name,),
    ).fetchone()
    return dict(row) if row else None


def _store_accent(
    char_name: str,
    result: dict | None,
    fingerprint: tuple[int, str | None, list[int]],
    portrait_url: str | None,
    partial: bool,
) -> None:
    import db

    count, latest, _ = fingerprint
    with db.transaction() as conn:
        conn.execute(
            "UPDATE characters SET accent_seed = ?, accent_hue = ?, accent_source = ?,"
            " accent_gallery_count = ?, accent_gallery_latest = ?, accent_portrait_url = ?,"
            " accent_partial = ?, accent_updated_at = ? WHERE name = ?",
            (
                result["seed"] if result else None,
                result["hue"] if result else None,
                result.get("source") if result else None,
                count,
                latest,
                portrait_url,
                1 if partial else 0,
                db._now(),
                char_name,
            ),
        )


def recompute_accent(char_name: str, *, fetch_missing: bool = False) -> dict | None:
    """Re-measure one character and store the result. Returns the seed dict or None.

    Thumbnails that are not on disk are skipped rather than fetched -- this runs
    inside gallery requests, and pulling dozens of originals from ImgChest there
    would be far worse than a seed that upgrades itself on a later visit (which
    is what `accent_partial` records). `fetch_missing=True` is for the offline
    backfill script, which has all the time in the world.
    """
    import db

    portrait = db.get_character_portrait(char_name)
    portrait_url = portrait[1] if portrait else None

    count, latest, image_ids = gallery_fingerprint(char_name)
    sampled_ids = evenly_sample(image_ids, POOL_SAMPLE_CAP)
    paths: list[Path] = []
    missing = 0
    for image_id in sampled_ids:
        path = thumbnails.cache_path(image_id)
        if path.is_file():
            paths.append(path)
        else:
            missing += 1
            if fetch_missing:
                _materialise_thumbnail(image_id)
                if path.is_file():
                    paths.append(path)
                    missing -= 1

    try:
        result = extract_seed(portrait_url, paths)
    except Exception:
        log.exception("accent.recompute_failed", character=char_name)
        return None

    _store_accent(char_name, result, (count, latest, image_ids), portrait_url, partial=missing > 0)
    log.info(
        "accent.recomputed",
        character=char_name,
        seed=result["seed"] if result else None,
        source=result["source"] if result else None,
        images=len(paths),
        missing=missing,
    )
    return result


def _materialise_thumbnail(image_id: int) -> None:
    """Fetch and cache one thumbnail, exactly as the serving endpoint would."""
    import db

    source = db.get_image_url(image_id)
    if not source or not thumbnails.is_thumbnailable(source):
        return
    try:
        response = _get_with_validated_redirects(source, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            return
        thumbnails.store(image_id, thumbnails.render(response.content))
    except Exception as e:
        log.warning(
            "accent.thumbnail_fetch_failed", image_id=image_id, error=f"{type(e).__name__}: {e}"
        )


def ensure_accent(char_name: str) -> str | None:
    """The character's current seed, recomputing only when its inputs changed.

    Called from the gallery listing endpoint. A matching fingerprint with
    `accent_partial = 0` is a hit -- no disk work at all. A partial entry is
    retried only once every sampled thumbnail has actually landed on disk, so
    a gallery still rendering its images does not put a recompute on every
    request. Recompute failures are logged and fall through to whatever is
    stored; the listing must never fail because a colour could not be measured.
    """
    state = accent_state(char_name)
    if state is None:
        return None

    count, latest, _ = gallery_fingerprint(char_name)
    fresh = (
        state["accent_updated_at"] is not None
        and state["accent_gallery_count"] == count
        and state["accent_gallery_latest"] == latest
        and (state["accent_portrait_url"] or None) == (state["main_image_url"] or None)
    )
    if fresh and not state["accent_partial"]:
        return state["accent_seed"]

    if fresh and state["accent_partial"]:
        _, _, image_ids = gallery_fingerprint(char_name)
        sampled = evenly_sample(image_ids, POOL_SAMPLE_CAP)
        if not all(thumbnails.cache_path(i).is_file() for i in sampled):
            return state["accent_seed"]

    try:
        result = recompute_accent(char_name)
    except Exception:
        log.exception("accent.ensure_failed", character=char_name)
        return state["accent_seed"]
    return result["seed"] if result else None
