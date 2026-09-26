"""Pick a reproducible random sample of live characters by image-count band.

    uv run python -m scripts.accent_lab.sample [--seed 20260926] [--per-band 5]

Ranks the whole library by image count (most first), cuts it into the bands in
BANDS (fractions of the ranking), and draws `--per-band` characters per band
whose main image actually loads -- an R2 mirror, or a Mudae link that answers
with an image. Writes `.data/sample.json` and prints the names so they can be
passed to `fetch_live`.
"""

from __future__ import annotations

import argparse
import json
import random
import time

import requests

from .lab import DATA

API = "https://api.lukazade.dev"
IMAGES = "https://images.lukazade.dev"
BANDS = [("top 10%", 0.0, 0.1), ("10-20%", 0.1, 0.2), ("20-30%", 0.2, 0.3),
         ("30-50%", 0.3, 0.5), ("50-70%", 0.5, 0.7)]  # fmt: skip
UA = {"User-Agent": "Mozilla/5.0 (accent-lab)"}


def library():
    out, page = [], 1
    while True:
        r = requests.get(
            f"{API}/api/customs",
            params={"page": page, "per_page": 100},
            headers={"Content-Type": "application/json"},
            timeout=60,
        ).json()
        items = r.get("items") or []
        out += items
        if len(items) < 100:
            return out
        page += 1
        time.sleep(0.5)


def main_image_ok(c) -> bool:
    if c.get("image_thumb"):
        url = f"{IMAGES}/{c['image_thumb']}"
    elif c.get("image"):
        url = c["image"]
    else:
        return False
    try:
        r = requests.get(url, headers=UA, timeout=30)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    except requests.RequestException:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260926)
    parser.add_argument("--per-band", type=int, default=5)
    args = parser.parse_args()
    chars = sorted(library(), key=lambda c: -int(c.get("count") or 0))
    rng = random.Random(args.seed)
    n = len(chars)
    picked = []
    for label, lo, hi in BANDS:
        band = chars[int(lo * n) : int(hi * n)]
        counts = [int(c["count"]) for c in band]
        pool = band[:]
        rng.shuffle(pool)
        chosen = []
        for c in pool:
            if main_image_ok(c):
                chosen.append(c)
            if len(chosen) == args.per_band:
                break
        print(f"{label}: ranks {int(lo * n) + 1}-{int(hi * n)}, {max(counts)}-{min(counts)} images")
        for c in chosen:
            print(f"   {c['name']} ({c['count']})")
            picked.append({"band": label, "name": c["name"], "count": int(c["count"])})
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "sample.json").write_text(
        json.dumps({"seed": args.seed, "library": n, "picked": picked}, indent=1)
    )


if __name__ == "__main__":
    main()
