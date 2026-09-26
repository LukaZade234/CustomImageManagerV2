"""Shared plumbing for the accent experiments: where data lives, loading
characters, describing a seed, the calibration panel, and the shipped method.

Two sources of characters:

- **Local**: the working library in `data/` (the v1-era snapshot and its cached
  thumbnails), addressed by integer character id. Old, but it has the panel.
- **Live**: characters pulled off the production site by `fetch_live`, stored
  under `.data/live/<slug>/`, addressed as `"live:<Name>"`. Use these for
  anything reported against the current library.

Every loaded image carries `img.info["src"]`, the full-resolution file it came
from, so segmentation (`seg.py`) can run on the 600px thumbnail rather than the
200px measurement copy — the model misses most characters at 200px.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import accent_extract as A  # noqa: E402

LAB = Path(__file__).resolve().parent
DATA = Path(os.environ.get("ACCENT_LAB_DATA", LAB / ".data"))
LIVE = DATA / "live"
DB = REPO / "data" / "imgmanager.db"
THUMBS = REPO / "data" / "thumbs"
PORTRAITS = REPO / "data" / "portrait_samples"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def hue_gap(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def describe(hexs):
    """A seed hex as the dict the panel expectations read (OKLCH hue/C/L)."""
    if hexs is None:
        return None
    r, g, b = (int(hexs[i : i + 2], 16) / 255 for i in (1, 3, 5))
    L, C, h = A.rgb_to_oklch(r, g, b)
    return {"seed": hexs, "hue": h, "chroma": C, "lightness": L}


# Expectations are in OKLCH hue. Two changes from tests/test_accent_extract.py:
# Lynae is added (teal/mint, not sky blue -- the owner's call, 2026-09-26), and
# "live:Reze" measures her whole live gallery. Reze's violet expectation is kept
# for comparison, but see docs/ACCENT.md 16: it came from her portrait's
# background, and her hair is too muted to vote.
PANEL = {
    1001: ("Audrey Hall", lambda r: r is not None),
    445: ("Tsumugi Kotobuki", lambda r: r is not None),
    92: (
        "Lucy",
        lambda r: (
            r is not None
            and 240 <= r["hue"] <= 290
            and r["lightness"] >= 0.7
            and r["chroma"] <= 0.06
        ),
    ),
    2: ("Hatsune Miku", lambda r: r is not None and 170 <= r["hue"] <= 240),
    592: ("Reimu Hakurei", lambda r: r is not None and hue_gap(r["hue"], 10) < 40),
    13: ("2B", lambda r: r is None or r["chroma"] < 0.06),
    59: ("Reze", lambda r: r is not None and 270 <= r["hue"] <= 320),
    6: (
        "Saber",
        lambda r: r is not None and 240 <= r["hue"] <= 290 and r["lightness"] < 0.6,
    ),
    156: ("Madoka Kaname", lambda r: r is not None and hue_gap(r["hue"], 350) < 30),
    "live:Lynae": (
        "Lynae (teal/mint)",
        lambda r: (
            r is not None
            and 150 <= r["hue"] <= 205
            and r["chroma"] >= 0.09
            and r["lightness"] >= 0.55
        ),
    ),
    "live:Reze": ("Reze (live)", lambda r: r is not None and 270 <= r["hue"] <= 320),
}


def tagged(path):
    """Load for measurement, remembering the source file for full-res masks."""
    img = A.load_local_image(path)
    if img is not None:
        img.info["src"] = str(path)
    return img


def load_character(cid, cap=60):
    """(name, portrait image or None, [gallery images]) in gallery order.

    `cap` is the shipped 60-image `evenly_sample`; `cap=None` measures every
    image, which is what docs/ACCENT.md 15.5 recommends.
    """
    if isinstance(cid, str) and cid.startswith("live:"):
        return load_live(cid.split(":", 1)[1], cap)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        name = conn.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()[0]
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id, url FROM custom_images WHERE character_id=? AND state='active'"
                " ORDER BY position, id",
                (cid,),
            )
            if not r[1].lower().split("?")[0].endswith(".gif")
        ]
    finally:
        conn.close()
    chosen = ids if cap is None else A.evenly_sample(ids, cap)
    imgs = [tagged(p) for p in (THUMBS / f"{i}.webp" for i in chosen) if p.is_file()]
    portrait_path = PORTRAITS / f"{cid}.webp"
    portrait = tagged(portrait_path) if portrait_path.is_file() else None
    return name, portrait, [i for i in imgs if i is not None]


def load_live(name, cap=60):
    """A character fetched by `fetch_live`, in the live gallery's order."""
    folder = LIVE / slug(name)
    meta = json.loads((folder / "meta.json").read_text())
    ids = [str(i) for i in meta["image_ids"]]
    chosen = ids if cap is None else A.evenly_sample(ids, cap)
    imgs = [tagged(folder / "thumbs" / f"{i}.webp") for i in chosen]
    portrait = None
    for candidate in sorted(folder.glob("portrait.*")):
        portrait = tagged(candidate)
        break
    return meta["name"], portrait, [i for i in imgs if i is not None]


def live_names():
    """Names of every character fetched into .data/live, sorted."""
    return sorted(json.loads(m.read_text())["name"] for m in LIVE.glob("*/meta.json"))


def library_ids(min_thumbs=6, limit=None):
    """Local characters with at least `min_thumbs` cached thumbnails."""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT character_id, group_concat(id) FROM custom_images"
            " WHERE state='active' GROUP BY character_id"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for cid, ids in rows:
        n = sum((THUMBS / f"{i}.webp").is_file() for i in ids.split(","))
        if n >= min_thumbs:
            out.append(cid)
    out.sort()
    return out[:limit]


def method_current(portrait, gallery):
    """The shipped extractor, unchanged."""
    p = A.measure_image(portrait) if portrait is not None else None
    g = [x for x in (A.measure_image(i) for i in gallery) if x is not None]
    if p is None and not g:
        return None
    r = A.decide(p, g)
    return describe(r["seed"]) if r else None


def portrait_schedule(entries_fn, portrait, gallery):
    """Apply the shipped portrait-share schedule to any pooled method."""
    n = len(gallery)
    share = A._portrait_share(n)
    entries = [(g, 1.0) for g in gallery]
    if portrait is not None and share > 0:
        if n == 0:
            entries = [(portrait, 1.0)]
        else:
            entries.append((portrait, share / (1 - share) * n))
    if not entries:
        return None
    return entries_fn(entries)


def fmt(r):
    if not r:
        return "None".ljust(30)
    return f"{r['seed']} h{r['hue']:5.1f} C{r['chroma']:.3f} L{r['lightness']:.2f}"


# The owner's review of the V12 contact sheet (2026-09-26), as checks. All live.
# OKLCH hue ranges; "any" means only "has a colour" (the owner wants a fallback
# over a decline). Lynae's cyan was accepted, so her range here is wider than in
# PANEL.
def _hue_in(lo, hi):
    return lambda r: (
        r is not None and (lo <= r["hue"] <= hi if lo < hi else (r["hue"] >= lo or r["hue"] <= hi))
    )


def _has_colour(r):
    return r is not None


REVIEW = {
    "live:Lynae": ("Lynae: cyan/teal", lambda r: _hue_in(150, 215)(r) and r["chroma"] >= 0.09),
    "live:Reze": ("Reze: violet", _hue_in(270, 320)),
    "live:Ceres Fauna": ("Ceres Fauna: mint green", _hue_in(135, 180)),
    "live:Rebecca": ("Rebecca: teal/cyan/green hair", _hue_in(140, 215)),
    "live:Himeno": ("Himeno: blue-grey/navy/dark teal", _hue_in(200, 275)),
    "live:Panty Anarchy": (
        "Panty: clear yellow",
        lambda r: _hue_in(80, 115)(r) and r["chroma"] >= 0.08,
    ),
    "live:Nico Robin": ("Nico Robin: has a colour", _has_colour),
    "live:Yuta Okkotsu": ("Yuta: has a colour", _has_colour),
    "live:Alisa Mikhailovna Kujou": ("Alisa: has a colour", _has_colour),
    "live:Will Auceptin": ("Will Auceptin: has a colour", _has_colour),
    "live:The Sandman": ("The Sandman: has a colour", _has_colour),
    "live:Columbina": (
        "Columbina: pink or light blue",
        lambda r: _hue_in(330, 20)(r) or _hue_in(230, 280)(r),
    ),
    "live:Hiyuki": ("Hiyuki: red or blue", lambda r: _hue_in(0, 50)(r) or _hue_in(220, 280)(r)),
    "live:Vertin": ("Vertin: grey-blue or purple", _hue_in(220, 320)),
    "live:Hatsune Miku": ("Miku: teal", _hue_in(170, 240)),
    "live:Madoka Kaname": ("Madoka: pink", lambda r: _hue_in(330, 25)(r) and r["chroma"] >= 0.08),
    "live:Artoria Pendragon (Alter)": (
        "Artoria (Alter): red",
        lambda r: _hue_in(0, 40)(r) and r["chroma"] >= 0.08,
    ),
    "live:Lucy": ("Lucy: pale blue", lambda r: _hue_in(230, 290)(r) and r["lightness"] >= 0.7),
    "live:Saber": ("Saber: deep blue", lambda r: _hue_in(240, 290)(r) and r["lightness"] < 0.6),
    "live:Reimu Hakurei": ("Reimu: red", _hue_in(350, 50)),
    "live:2B": ("2B: grey or none", lambda r: r is None or r["chroma"] < 0.06),
    "live:Audrey Hall": ("Audrey Hall: has a colour", _has_colour),
    "live:Tsumugi Kotobuki": ("Tsumugi: has a colour", _has_colour),
}
