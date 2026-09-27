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
    "live:Lynae": (
        "Lynae: vivid cyan (approved #34b0c1)",
        lambda r: _hue_in(190, 225)(r) and r["lightness"] <= 0.78 and r["chroma"] >= 0.09,
    ),
    "live:Reze": ("Reze: violet", _hue_in(270, 320)),
    # "Mint" was loose: the pale yellow-green V18 gave (#ddefab) was approved.
    "live:Ceres Fauna": ("Ceres Fauna: yellow-green", _hue_in(100, 150)),
    "live:Rebecca": ("Rebecca: teal/cyan/green hair", _hue_in(140, 215)),
    "live:Himeno": ("Himeno: blue-grey/navy/dark teal", _hue_in(200, 275)),
    "live:Panty Anarchy": (
        "Panty: clear yellow",
        lambda r: _hue_in(80, 115)(r) and r["chroma"] >= 0.08,
    ),
    "live:Nico Robin": ("Nico Robin: has a colour", _has_colour),
    "live:Yuta Okkotsu": ("Yuta: has a colour", _has_colour),
    "live:Alisa Mikhailovna Kujou": ("Alisa: has a colour", _has_colour),
    # Second review: gold is a minority for these; red (or dark) should win.
    # Third review: the near-white V31 gave is closer than gold; red also fine.
    "live:Will Auceptin": (
        "Will Auceptin: near-white or red",
        lambda r: (
            r is not None and (r["lightness"] >= 0.85 and r["chroma"] < 0.03 or _hue_in(340, 45)(r))
        ),
    ),
    "live:Ishtar": (
        "Ishtar: red or dark, not gold",
        lambda r: r is not None and not _hue_in(60, 110)(r),
    ),
    "live:Osamu Dazai": (
        "Osamu Dazai: red/brown/navy, not gold",
        lambda r: r is not None and not _hue_in(60, 110)(r),
    ),
    "live:Poison Ivy (Pamela Isley)": (
        "Poison Ivy: green or red",
        lambda r: _hue_in(340, 45)(r) or _hue_in(120, 160)(r),
    ),
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
        "Artoria (Alter): red or raspberry",
        lambda r: _hue_in(340, 40)(r) and r["chroma"] >= 0.08,
    ),
    "live:Lucy": ("Lucy: pale blue", lambda r: _hue_in(230, 290)(r) and r["lightness"] >= 0.7),
    "live:Saber": ("Saber: deep blue", lambda r: _hue_in(240, 290)(r) and r["lightness"] < 0.6),
    "live:Reimu Hakurei": ("Reimu: red", _hue_in(350, 50)),
    "live:2B": ("2B: grey or none", lambda r: r is None or r["chroma"] < 0.06),
    "live:Audrey Hall": ("Audrey Hall: has a colour", _has_colour),
    "live:Tsumugi Kotobuki": ("Tsumugi: has a colour", _has_colour),
}


def _near(seed, dh=20, dl=0.12):
    """Close to an approved seed: hue within dh degrees, lightness within dl."""
    ref = describe(seed)
    return lambda r: (
        r is not None
        and hue_gap(r["hue"], ref["hue"]) <= dh
        and abs(r["lightness"] - ref["lightness"]) <= dl
    )


def _pinkish(min_l):
    return lambda r: _hue_in(330, 18)(r) and r["lightness"] >= min_l


# The owner's review of the random sample (2026-09-26, third round). "Approved"
# rows must stay near the colour the owner saw and accepted.
SAMPLE_REVIEW = {
    "live:Sandrone": ("Sandrone: approved", _near("#a84347")),
    "live:Sukuna": ("Sukuna: approved", _near("#b15741")),
    "live:Kasane Teto": ("Kasane Teto: approved", _near("#cb3f55")),
    # Fifth review: the brown V28+ gives Nephis is fine.
    "live:Nephis": ("Nephis: approved (V29+ brown)", _near("#a38f6a", dh=30)),
    "live:Akane Kurokawa": ("Akane Kurokawa: approved", _near("#354b86")),
    "live:Mitsuri Kanroji": ("Mitsuri: pink, no contest", _pinkish(0.6)),
    "live:Zero Two": ("Zero Two: approved", _near("#c03f49")),
    "live:Sakurako Kawawa": (
        "Sakurako: creamy with hints of pink",
        lambda r: _hue_in(330, 60)(r) and r["lightness"] >= 0.68,
    ),
    "live:Hiyuki": ("Hiyuki: red or blue", lambda r: _hue_in(340, 50)(r) or _hue_in(220, 280)(r)),
    "live:Shiki Ryougi": ("Shiki Ryougi: approved", _near("#404b8d")),
    # Fifth review: V29's deeper pink is fine too.
    "live:Narumi Momose": (
        "Narumi Momose: approved",
        lambda r: _near("#f3b3db")(r) or _near("#d872af")(r),
    ),
    "live:Mystia Lorelei": ("Mystia Lorelei: approved", _near("#bd6071")),
    "live:Superman (Clark Kent)": ("Superman: approved", _near("#c22d2b")),
    "live:Hornet": ("Hornet: approved", _near("#b63c4b")),
    "live:Tohru": ("Tohru: nearer orange", _hue_in(38, 75)),
    "live:Mirio Togata": ("Mirio: yellow/orange", _hue_in(40, 100)),
    "live:Nadeko Sengoku": ("Nadeko: reddish pink, leaning pink", _pinkish(0.58)),
    "live:The Sandman": ("The Sandman: approved", _near("#364453")),
    "live:Lisa": ("Lisa: approved", _near("#513b96")),
    "live:Tewi Inaba": ("Tewi: pink", _pinkish(0.62)),
    "live:Hange Zoë": ("Hange: approved", _near("#a88b50")),
    "live:Aurore Lee": ("Aurore Lee: approved", _near("#466893")),
    "live:Nagatoro-san": ("Nagatoro: not red", lambda r: r is not None and not _hue_in(0, 45)(r)),
    "live:Luka": ("Luka: approved", _near("#8be6d9")),
    "live:Daki": ("Daki: approved", _near("#b32d3a")),
}


def _tinted_grey(r):
    return r is not None and 0.03 <= r["chroma"] <= 0.06 and 0.3 <= r["lightness"] <= 0.75


# The owner's review of the colour-profile paths (2026-09-27, fourth and fifth rounds).
PROFILE_REVIEW = {
    "live:Himeno": ("Himeno: V30's tinted blue-grey", _near("#465664", dh=30, dl=0.1)),
    "live:Mei Mei": ("Mei Mei: V30's tinted grey", _near("#6f768d", dh=30, dl=0.1)),
    "live:Akira Asai": ("Akira Asai: tinted grey, not too dark", _tinted_grey),
    "live:Osaragi": (
        "Osaragi: dark, at most a slight tint",
        lambda r: r is not None and r["lightness"] <= 0.45 and r["chroma"] <= 0.05,
    ),
    "live:Will Auceptin": (
        "Will: near-white",
        lambda r: r is not None and r["lightness"] >= 0.85 and r["chroma"] < 0.03,
    ),
    "live:Ken Kaneki": ("Kaneki: his red highlight", _hue_in(0, 45)),
    "live:Gu Yue Fang Yuan": (
        "Gu Yue Fang Yuan: not the red of two images",
        lambda r: r is not None and not _hue_in(340, 45)(r),
    ),
    "live:Semiramis": (
        "Semiramis: warm grey, not lavender",
        lambda r: r is not None and not _hue_in(240, 320)(r),
    ),
    "live:Annie Leonhart": ("Annie Leonhart: blonde (brown second)", _hue_in(50, 110)),
    "live:Evernight Goddess": ("Evernight Goddess: red", _hue_in(0, 35)),
    "live:Himiko Toga": (
        "Himiko Toga: cream",
        lambda r: r is not None and r["lightness"] >= 0.75 and _hue_in(40, 110)(r),
    ),
    "live:2B": (
        "2B: white preferred (override), no tint",
        lambda r: r is not None and r["lightness"] >= 0.85 and r["chroma"] < 0.03,
    ),
    "live:A2": (
        "A2: white preferred (override), no tint",
        lambda r: r is not None and r["lightness"] >= 0.85 and r["chroma"] < 0.03,
    ),
}


def _greenish(min_c=0.05, max_l=1.0, min_l=0.0):
    return lambda r: (
        _hue_in(118, 175)(r) and r["chroma"] >= min_c and min_l <= r["lightness"] <= max_l
    )


# The owner's review of the full 4+ check (2026-09-27), the themes V34 targets:
# greens, the main image's background, highlights and never-empty.
FULL_REVIEW = {
    "live:Maki Zenin": ("Maki Zenin: dark green", _greenish(max_l=0.62)),
    "live:Nefer": ("Nefer: darker green", _greenish(max_l=0.7)),
    "live:Maomao": ("Maomao: darker green", _greenish(max_l=0.7)),
    "live:Roronoa Zoro": ("Zoro: green", _greenish()),
    "live:N": ("N: light green", _greenish(min_l=0.6)),
    "live:Noriaki Kakyoin": (
        "Noriaki: green (or wine red)",
        lambda r: _greenish()(r) or _hue_in(350, 20)(r),
    ),
    "live:Sanae Kochiya": ("Sanae: green", _greenish()),
    "live:Daiyousei": ("Daiyousei: green", _greenish()),
    "live:Green Lantern (John Stewart)": ("Green Lantern: strong green", _greenish(min_c=0.12)),
    "live:Jiu Niangzi": (
        "Jiu Niangzi: green or earthy brown",
        lambda r: _greenish()(r) or (_hue_in(40, 90)(r) and r["lightness"] < 0.6),
    ),
    "live:Kyouka Jirou": ("Kyouka Jirou: purple", _hue_in(275, 325)),
    "live:Suika Ibuki": (
        "Suika Ibuki: not the main image's purple",
        lambda r: r is not None and not _hue_in(275, 330)(r),
    ),
    "live:Usagi Tsukino": (
        "Usagi: blonde yellow or bow red",
        lambda r: _hue_in(70, 110)(r) or _hue_in(0, 40)(r),
    ),
    "live:Alpha": (
        "Alpha: yellow, navy or black -- not pink",
        lambda r: r is not None and not _hue_in(320, 20)(r),
    ),
    "live:Shizuku Murasaki": (
        "Shizuku: dark grey or red, not blue",
        lambda r: r is not None and not _hue_in(220, 280)(r),
    ),
    "live:Ellen Joe": (
        "Ellen Joe: hot pink/red or dark, not the background",
        lambda r: r is not None and (_hue_in(340, 30)(r) or r["lightness"] < 0.35),
    ),
    "live:Rio Futaba": (
        "Rio Futaba: not pink",
        lambda r: r is not None and not _hue_in(330, 20)(r),
    ),
    "live:Tsukatsuki Rio": ("Tsukatsuki Rio: red highlight", _hue_in(0, 45)),
    "live:Alucard (Hellsing)": ("Alucard: red highlight", _hue_in(0, 45)),
    "live:Griffith": (
        "Griffith: a colour (light blue from the main image)",
        lambda r: r is not None,
    ),
    "live:Cheongmyeong": ("Cheongmyeong: a colour", lambda r: r is not None),
}


# The owner's review of V36 (2026-09-27).
V36_REVIEW = {
    "live:Yotsuba Nakano": ("Yotsuba Nakano: orange", _hue_in(35, 70)),
    "live:David Martinez": ("David Martinez: pure yellow", _hue_in(80, 105)),
    "live:Yuuki (SYMK)": (
        "Yuuki (SYMK): white/blue-white, not wine red",
        lambda r: r is not None and r["lightness"] >= 0.8,
    ),
    "live:Kaine": (
        "Kaine: white",
        lambda r: r is not None and r["lightness"] >= 0.85 and r["chroma"] < 0.03,
    ),
    "live:Ruka Urushibara": ("Ruka Urushibara: teal (as before)", _hue_in(180, 230)),
    "live:Xurkitree": ("Xurkitree: blue (as before)", _hue_in(220, 270)),
    "live:Jotaro Kujo": (
        "Jotaro Kujo: navy or gold, not skin",
        lambda r: (
            _hue_in(240, 290)(r)
            or (_hue_in(70, 100)(r) and r["chroma"] >= 0.1 and r["lightness"] < 0.85)
        ),
    ),
    "live:Nephis": ("Nephis: approved brown", _near("#a38f6a", dh=30)),
    "live:Maki Zenin": (
        "Maki Zenin: V36's dark teal (or dark green)",
        lambda r: _near("#163948", dh=40, dl=0.15)(r) or _greenish(max_l=0.62)(r),
    ),
}


# The owner's review of the V38e trial (2026-09-27): the 34 characters whose colour
# visibly changed from V37 when parsed hair counts twice.
V38_REVIEW = {
    # Old green preferred at first; with her main image the tie goes to her red hair,
    # which the owner then accepted as "still characteristic of her enough".
    "live:Daphnis et Chloé": (
        "Daphnis et Chloe: red (main image) or green",
        lambda r: _greenish()(r) or _near("#b15041")(r),
    ),
    "live:Izumi Miyamura": (
        "Izumi Miyamura: either (cream or dark red)",
        lambda r: _near("#e8d792")(r) or _near("#7c2217")(r),
    ),
    "live:Lillie": (
        "Lillie: old paler yellow (nitpick)",
        lambda r: _near("#fbe7a1", dh=15)(r) and r["lightness"] >= 0.88,
    ),
    "live:Tanya Degurechaff": (
        "Tanya: either (blonde or blood red)",
        lambda r: _near("#e9cf8c")(r) or _near("#9b312f")(r),
    ),
    "live:Anya Forger": (
        "Anya Forger: pink (clearer is better)",
        lambda r: _hue_in(330, 25)(r) and r["chroma"] >= 0.1,
    ),
    "live:Ellen Joe": ("Ellen Joe: V38e red, very good", _near("#c5546d")),
    "live:Omaru Polka": (
        "Omaru Polka: old paler yellow (nitpick)",
        lambda r: _near("#f5e39d", dh=15)(r) and r["lightness"] >= 0.88,
    ),
    "live:Panty Anarchy": (
        "Panty: vibrant yellow, not washed out",
        lambda r: _hue_in(75, 110)(r) and r["chroma"] >= 0.12,
    ),
    "live:Kyouka Jirou": ("Kyouka Jirou: V38e purple", _near("#63529c")),
    "live:Aemeath": ("Aemeath: V38e pink", _near("#c86e8b")),
    "live:Ibuki Mioda": (
        "Ibuki Mioda: blue or purple-pink (slight preference purple)",
        lambda r: _near("#6988c2")(r) or _near("#d2559d")(r),
    ),
    "live:Jade (HSR)": ("Jade (HSR): V38e lilac", _near("#d5a2d4")),
}
