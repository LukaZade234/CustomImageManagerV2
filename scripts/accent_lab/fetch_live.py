"""Pull one character off the live site into the lab: every gallery thumbnail
(the same WebPs the grid shows) and the Mudae portrait.

    uv run python -m scripts.accent_lab.fetch_live "Lynae" "Reze"

Read-only and public: the gallery listing, the catalog record and the image
CDN, exactly what an anonymous visitor's browser fetches. Nothing touches the
origin box or the database directly. Re-running refreshes the id list and only
downloads thumbnails that are missing.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

from .lab import LIVE, slug

API = "https://api.lukazade.dev"
IMAGES = "https://images.lukazade.dev"
HEADERS = {"Content-Type": "application/json", "User-Agent": "accent-lab/1"}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r


def fetch(name: str) -> None:
    folder = LIVE / slug(name)
    (folder / "thumbs").mkdir(parents=True, exist_ok=True)

    quoted = urllib.parse.quote(name, safe="")
    listing = _get(f"{API}/api/custom-image/{quoted}").json()
    record = _get(f"{API}/api/catalog/character?name={quoted}").json().get("character") or {}
    rows = listing.get("rows") or []

    def thumb(row):
        path = folder / "thumbs" / f"{row['id']}.webp"
        key = row.get("thumb")
        if path.is_file() or not key:
            return
        url = f"{API}{key}" if key.startswith("/") else f"{IMAGES}/{key}"
        path.write_bytes(_get(url).content)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(thumb, rows))

    # The extractor measures main_image_url (the Mudae original), so prefer it;
    # the R2 mirror is the fallback when Mudae refuses the request.
    portrait = record.get("image")
    try:
        data = _get(portrait).content if portrait else None
        ext = portrait.rsplit(".", 1)[-1].split("?")[0] if portrait else "png"
    except requests.RequestException:
        data, ext = None, "webp"
    if data is None and record.get("image_thumb"):
        data, ext = _get(f"{IMAGES}/{record['image_thumb']}").content, "webp"
    if data:
        for old in folder.glob("portrait.*"):
            old.unlink()
        (folder / f"portrait.{ext}").write_bytes(data)

    meta = {
        "name": name,
        "image_ids": [row["id"] for row in rows if row.get("thumb")],
        "live_accent_seed": listing.get("accentSeed"),
        "accent_manual": listing.get("accentManual"),
        "portrait_url": portrait,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"{name}: {len(meta['image_ids'])} images, live seed {meta['live_accent_seed']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="+")
    for name in parser.parse_args().names:
        fetch(name)


if __name__ == "__main__":
    main()
