"""The WD tagger as a tie-breaker, simulated (ACCENT.md §41-42).

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.tagsim scan
    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.tagsim simulate

`scan` tags every character with a review verdict, plus any extra names given as
"A|B", on up to 20 images each (the model and tag list are fetched as in
tagprobe.py), and saves the share of images carrying each colour tag to
.data/tagscan.json. `simulate` runs V43 on each, records its candidate colour
windows, and asks what would change if the tags could choose among them: only
distinctive tags count (a hair colour other than black, white, grey, brown or
blonde in >= 40% of images, else a clothing colour in >= 60%), a tagged window must
be at least 0.4x the winner's strength, and no colour is ever added.

A first version that let blonde and brown hair choose backfired on Lynae, Saber,
Aurore Lee and Sandrone, whose identity is their clothes or effects, not their hair.
"""

from __future__ import annotations

import colorsys
import csv
import json
import os
import re
import sys

import numpy as np
from PIL import Image

from . import lab
from . import methods as M

SCAN = lab.DATA / "tagscan.json"
MODEL = lab.DATA / "skin" / "wd-vit.onnx"
TAGS = lab.DATA / "skin" / "wd-tags.csv"
THRESHOLD = 0.35
REVIEW_SETS = ["REVIEW", "SAMPLE_REVIEW", "PROFILE_REVIEW", "FULL_REVIEW", "V36_REVIEW", "V38_REVIEW"]  # fmt: skip
COLOUR_TAG = re.compile(
    r"^(red|orange|yellow|green|aqua|blue|purple|pink|brown|black|white|grey|blonde|silver)_"
    r"(hair|eyes|dress|shirt|jacket|skirt|shorts|kimono|coat|bow|ribbon|hoodie|sweater|cape|"
    r"gloves|bodysuit|leotard|headwear|hat|pants|necktie|scarf|bikini|footwear|thighhighs|"
    r"pantyhose|hairband|vest|sailor_collar|serafuku|neckerchief|cloak|robe|armor|capelet)$"
)
# HSV hue range each distinctive colour word covers
RANGE = {"red": (345, 15), "orange": (15, 40), "yellow": (40, 68), "green": (70, 165), "aqua": (160, 200), "blue": (195, 250), "purple": (250, 295), "pink": (295, 350)}  # fmt: skip


def _reviewed() -> set[str]:
    names: set[str] = set()
    for s in REVIEW_SETS:
        names |= {k[5:] for k in getattr(lab, s) if k.startswith("live:")}
    return names


def _prep(path):
    im = Image.open(path).convert("RGB")
    side = max(im.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    arr = np.asarray(canvas.resize((448, 448), Image.BICUBIC), np.float32)[:, :, ::-1]  # BGR
    return np.ascontiguousarray(arr[None])


def scan(extra: set[str]) -> None:
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 12
    sess = ort.InferenceSession(str(MODEL), opts, providers=["CPUExecutionProvider"])
    with open(TAGS, newline="") as f:
        names = [r["name"] for r in csv.DictReader(f)]
    out = json.loads(SCAN.read_text()) if SCAN.is_file() else {}
    for name in sorted(_reviewed() | extra):
        meta = lab.LIVE / lab.slug(name) / "meta.json"
        if name in out or not meta.is_file():
            continue
        ids = json.loads(meta.read_text())["image_ids"]
        paths = [lab.LIVE / lab.slug(name) / "thumbs" / f"{i}.webp" for i in ids]
        paths = [p for p in paths if p.is_file()]
        paths = paths[:: max(1, len(paths) // 20)][:20]
        hits: dict[str, int] = {}
        for p in paths:
            y = sess.run(None, {"input": _prep(p)})[0][0]
            for i in np.nonzero(y >= THRESHOLD)[0]:
                if COLOUR_TAG.match(names[i]):
                    hits[names[i]] = hits.get(names[i], 0) + 1
        out[name] = {k: v / len(paths) for k, v in hits.items()}
        SCAN.write_text(json.dumps(out))
    print(f"{len(out)} characters tagged -> {SCAN}")


def _within(h, rng, tol=5):
    lo, hi = rng
    return (lo - tol <= h <= hi + tol) if lo < hi else (h >= lo - tol or h <= hi + tol)


def _hsv_hue(seed):
    r, g, b = (int(seed[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _signature(tags):
    def ranked(pred):
        items = [
            (k.split("_")[0], v) for k, v in tags.items() if pred(k) and k.split("_")[0] in RANGE
        ]
        return sorted(items, key=lambda x: -x[1])

    hair = ranked(lambda k: k.endswith("_hair"))
    if hair and hair[0][1] >= 0.4:
        return hair[0], "hair"
    other = ranked(lambda k: not k.endswith(("_hair", "_eyes")))
    if other and other[0][1] >= 0.6:
        return other[0], "clothing"
    return None, None


def simulate() -> None:
    tagged = json.loads(SCAN.read_text())
    reviewed = _reviewed()
    rows: dict[str, list[str]] = {"change": [], "same": [], "none": []}
    for name, tags in sorted(tagged.items()):
        try:
            _, portrait, gallery = lab.load_character(f"live:{name}", None)
        except FileNotFoundError:
            continue
        calls: list = []
        base = M.windows
        M.windows = lambda h, base=base, calls=calls: calls.append(base(h)) or calls[-1]
        trace: list[str] = []
        try:
            r = M.candidate(portrait, gallery, trace)
        finally:
            M.windows = base
        who = "(reviewed)" if name in reviewed else "(open)    "
        sig, src = _signature(tags)
        if not sig:
            rows["none"].append(f"{name} {who}: no distinctive colour tag")
            continue
        label = f"{sig[0]} {src} {sig[1]:.0%}"
        cands = calls[0] if calls else []
        if not trace or not trace[0].startswith("standard") or not cands or r is None:
            rows["none"].append(f"{name} {who}: {label}, but not decided on the standard path")
            continue
        rng = RANGE[sig[0]]
        if _within(_hsv_hue(r["seed"]), rng):
            rows["same"].append(f"{name} {who}: {label}; accent {r['seed']} already {sig[0]}")
            continue
        alt = max(((h, s) for h, s in cands if _within(h, rng)), default=None, key=lambda x: x[1])
        if alt and alt[1] >= 0.4 * cands[0][1]:
            rows["change"].append(
                f"{name} {who}: {label}; accent {r['seed']} -> the {alt[0]:.0f}deg candidate"
                f" ({alt[1]:.3f} vs winner {cands[0][1]:.3f})"
            )
        else:
            why = "absent" if not alt else f"too weak ({alt[1]:.3f} vs {cands[0][1]:.3f})"
            rows["none"].append(f"{name} {who}: {label}; accent {r['seed']}, tagged colour {why}")
    for k in ("change", "same", "none"):
        print(f"\n== {k} ({len(rows[k])})")
        for row in rows[k]:
            print("  " + row)


if __name__ == "__main__":
    if sys.argv[1:2] == ["scan"]:
        scan(set(filter(None, (sys.argv[2] if len(sys.argv) > 2 else "").split("|"))))
    else:
        os.environ.setdefault("ACCENT_LAB_ORT_THREADS", "4")
        simulate()
