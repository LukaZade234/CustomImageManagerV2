"""Precompute the V43 accents on a desktop, then move them onto the server.

The V43 accent needs two models per image (accent_models.py). The server's worker
would get through the whole library eventually, but on four ARM cores that is
hours of background work; a desktop does it in minutes. So the library is
measured here and the result carried over. Three steps, in order:

  snapshot   Desktop, read-only. Every character with a gallery, from the public
             API and the image CDN -- exactly what a visitor's browser fetches.
             Thumbnails and main images land in the working directory.
  compute    Desktop. Runs the models on every image and V43 on every character,
             into one bundle file (SQLite). Re-runs reuse what is already in the
             bundle; --lab-cache reuses the accent lab's cut-out and face caches.
  review     Desktop. A page of the result beside what the site shows today
             (read from the public catalog), for the owner to look over first.
  import     Server. Writes the bundle into the database: each image's model
             data, and each character's seed -- but a seed only where the
             character's gallery and main image are exactly what was measured.
             Anything that changed since the snapshot is queued for the worker
             instead. Hand-picked colours are never touched. A dry run unless
             --apply is given; --queue-rest also queues every character the
             bundle did not cover (those without a gallery), for the worker.

    uv run python scripts/accent_backfill.py snapshot
    uv run python scripts/accent_backfill.py compute [--lab-cache scripts/accent_lab/.data]
    uv run python scripts/accent_backfill.py review [--reviewed scripts/accent_lab/.data/full_v43]
    # copy data/accent_backfill/bundle.db to the server, then there:
    python scripts/accent_backfill.py import bundle.db            # dry run
    python scripts/accent_backfill.py import bundle.db --apply --queue-rest

See docs/ACCENT.md section 29 for where this sits in the rollout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API = "https://api.lukazade.dev"
IMAGES = "https://images.lukazade.dev"
HEADERS = {"User-Agent": "imgmanager-accent-backfill/1"}
WORK = Path("data/accent_backfill")

BUNDLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS image_data (
    image_id INTEGER PRIMARY KEY, version TEXT, data BLOB, face_hair TEXT, n_faces INTEGER);
CREATE TABLE IF NOT EXISTS main_data (
    url TEXT PRIMARY KEY, version TEXT, data BLOB, face_hair TEXT, n_faces INTEGER);
CREATE TABLE IF NOT EXISTS seeds (
    name TEXT PRIMARY KEY, seed TEXT, hue REAL, source TEXT, path TEXT, reason TEXT,
    image_ids TEXT, main_url TEXT, missing INTEGER, computed_at TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


# ---- snapshot (desktop) --------------------------------------------------------------


def _get(url):
    import requests

    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def snapshot(work: Path) -> None:
    """Write work/manifest.json and download every thumbnail and main image."""
    thumbs, mains = work / "thumbs", work / "main"
    thumbs.mkdir(parents=True, exist_ok=True)
    mains.mkdir(parents=True, exist_ok=True)
    names, page = [], 1
    while True:
        listing = _get(f"{API}/api/customs?page={page}&per_page=100&sort=name_asc").json()
        names += [item["name"] for item in listing["items"]]
        if page >= listing["total_pages"]:
            break
        page += 1
    print(f"{len(names)} characters with a gallery")

    manifest = []
    for n, name in enumerate(names, 1):
        quoted = urllib.parse.quote(name, safe="")
        rows = _get(f"{API}/api/custom-image/{quoted}").json().get("rows") or []
        record = _get(f"{API}/api/catalog/character?name={quoted}").json().get("character") or {}
        rows = [r for r in rows if r.get("thumb")]

        def fetch_thumb(row):
            path = thumbs / f"{row['id']}.webp"
            if not path.is_file():
                key = row["thumb"]
                url = f"{API}{key}" if key.startswith("/") else f"{IMAGES}/{key}"
                path.write_bytes(_get(url).content)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(fetch_thumb, rows))

        main_url = record.get("image")
        main_file = None
        if main_url:
            main_file = mains / (hashlib.sha1(main_url.encode()).hexdigest()[:16] + ".img")
            if not main_file.is_file():
                try:
                    main_file.write_bytes(_get(main_url).content)
                except Exception:
                    main_file = None
        manifest.append(
            {
                "name": name,
                "image_ids": [r["id"] for r in rows],
                "main_url": main_url,
                "main_file": main_file.name if main_file else None,
            }
        )
        if n % 50 == 0:
            print(f"  {n}/{len(names)}", flush=True)
    (work / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"snapshot: {sum(len(m['image_ids']) for m in manifest)} images -> {work}")


# ---- compute (desktop) --------------------------------------------------------------


def _open_full(path: Path):
    from PIL import Image

    import accent_models

    with Image.open(path) as img:
        img.load()
        return accent_models.composite(img)


def _from_lab_cache(full, lab: Path):
    """ImageData from the accent lab's cut-out and face caches, when both hold this image."""
    import numpy as np

    import accent_models

    rgb = full.convert("RGB")
    key = hashlib.sha1(rgb.tobytes() + repr(rgb.size).encode()).hexdigest()[:16]
    mask_path, parse_path = lab / "masks" / f"{key}.npy", lab / "faceparse" / f"{key}.npz"
    if not mask_path.is_file() or not parse_path.is_file():
        return None
    parsed = np.load(parse_path)
    if "f" not in parsed:
        return None
    return accent_models.reduce(full, np.load(mask_path), parsed["l"], parsed["f"])


def _data_row(conn, table, key_col, key, full, models, lab):
    import accent_models

    row = conn.execute(
        f"SELECT version, data, face_hair, n_faces FROM {table} WHERE {key_col} = ?", (key,)
    ).fetchone()
    if row and row[0] == accent_models.DATA_VERSION:
        return accent_models.ImageData.from_row(row[1], row[2], row[3], row[0])
    data = _from_lab_cache(full, lab) if lab else None
    if data is None:
        data = accent_models.prepare(models, full)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({key_col}, version, data, face_hair, n_faces)"
        " VALUES (?, ?, ?, ?, ?)",
        (key, data.version, data.to_blob(), data.hair_json(), data.n_faces),
    )
    return data


def compute(work: Path, lab: Path | None) -> None:
    import numpy as np

    import accent_models
    import accent_v43

    accent_models.ensure_models()
    models = accent_models.Models()
    manifest = json.loads((work / "manifest.json").read_text())
    conn = sqlite3.connect(work / "bundle.db")
    conn.executescript(BUNDLE_SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO meta VALUES ('data_version', ?)", (accent_models.DATA_VERSION,)
    )
    started = time.monotonic()
    for n, entry in enumerate(manifest, 1):
        gallery, missing = [], 0
        for image_id in entry["image_ids"]:
            path = work / "thumbs" / f"{image_id}.webp"
            if not path.is_file():
                missing += 1
                continue
            full = _open_full(path)
            data = _data_row(conn, "image_data", "image_id", image_id, full, models, lab)
            rgb = np.asarray(accent_models.measurement_copy(full))
            gallery.append(data.prepared(rgb))
        main = None
        if entry["main_file"]:
            full = _open_full(work / "main" / entry["main_file"])
            data = _data_row(conn, "main_data", "url", entry["main_url"], full, models, lab)
            main = data.prepared(np.asarray(accent_models.measurement_copy(full)))
        result = accent_v43.decide(main, gallery)
        seed = result.seed or {}
        source = result.source if result.path == "standard" else result.path
        conn.execute(
            "INSERT OR REPLACE INTO seeds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                entry["name"], seed.get("seed"), seed.get("hue"), source if seed else None,
                result.path, result.reason, json.dumps(entry["image_ids"]), entry["main_url"],
                missing,
            ),
        )  # fmt: skip
        conn.commit()
        if n % 25 == 0 or n == len(manifest):
            mins = (time.monotonic() - started) / 60
            print(f"  {n}/{len(manifest)} characters, {mins:.1f} min", flush=True)
    conn.close()
    print(f"bundle: {work / 'bundle.db'}")


# ---- review (desktop) --------------------------------------------------------------


def _live_seeds(work: Path, names) -> dict:
    """What the site shows today, per character (the public catalog record; read-only)."""
    import requests

    path = work / "live_seeds.json"
    out = json.loads(path.read_text()) if path.is_file() else {}
    session = requests.Session()
    session.headers.update(HEADERS)
    for name in names:
        if name in out:
            continue
        quoted = urllib.parse.quote(name, safe="")
        for _ in range(6):
            r = session.get(f"{API}/api/catalog/character?name={quoted}", timeout=30)
            if r.status_code == 429:
                time.sleep(15)
                continue
            if r.ok:
                out[name] = (r.json().get("character") or {}).get("accent_seed")
            break
        time.sleep(0.5)
    path.write_text(json.dumps(out))
    return out


def _thumb_uri(path: Path, height=150):
    import base64
    import io

    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((height * 2, height))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def review(work: Path, reviewed: Path | None) -> None:
    import html

    from scripts.accent_lab.fullcheck import CSS, _oklab

    manifest = {m["name"]: m for m in json.loads((work / "manifest.json").read_text())}
    conn = sqlite3.connect(work / "bundle.db")
    seeds = {
        r[0]: r
        for r in conn.execute("SELECT name, seed, source, path, reason, image_ids FROM seeds")
    }
    live = _live_seeds(work, list(manifest))

    def dist(a, b):
        if not a or not b:
            return 9.0 if a != b else 0.0
        return sum((p - q) ** 2 for p, q in zip(_oklab(a), _oklab(b), strict=True)) ** 0.5

    def lab_seed(name):
        if reviewed is None:
            return None
        import re

        f = reviewed / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".json")
        return json.loads(f.read_text()).get("seed") if f.is_file() else None

    new, drifted, same_as_lab = [], [], 0
    for name, (_, seed, *_rest) in seeds.items():
        ref = lab_seed(name)
        if ref is None:
            new.append(name)
        elif ref == seed:
            same_as_lab += 1
        else:
            drifted.append(name)
    changed_live = sum(dist(live.get(n), seeds[n][1]) >= 0.08 for n in seeds)

    def card(name):
        _, seed, source, path, reason, ids_json = seeds[name]
        entry, old = manifest[name], live.get(name)
        ids = json.loads(ids_json)
        main = (
            f'<img class="main" src="{_thumb_uri(work / "main" / entry["main_file"])}" alt="">'
            if entry["main_file"]
            else '<div class="main nomain">No main image</div>'
        )
        step = max(1, len(ids) // 4)
        customs = "".join(
            f'<img class="custom" src="{_thumb_uri(work / "thumbs" / f"{i}.webp")}" alt="">'
            for i in ids[::step][:4]
            if (work / "thumbs" / f"{i}.webp").is_file()
        )

        def sw(label, sd, strong=False):
            if not sd:
                return (
                    f'<div class="sw"><div class="swatch none">none</div><span>{label}</span></div>'
                )
            cls = "sw strong" if strong else "sw"
            return (
                f'<div class="{cls}"><div class="swatch" style="background:{sd}"></div>'
                f"<span>{label}</span><strong>{sd}</strong></div>"
            )

        moved = dist(old, seed) >= 0.08
        why = html.escape((reason or "").split(";")[0][:90])
        return (
            f'<article class="char" data-path="{"changed" if moved else "same"}" data-changed="{int(moved)}"'
            f' data-name="{html.escape(name.lower())}">'
            f'<header><h3>{html.escape(name)}</h3><span class="count">{len(ids)} images</span></header>'
            f'<div class="body">{main}<div class="customs">{customs}</div>'
            f'<div class="accent">{sw("Site today", old)}{sw("V43", seed, moved)}</div></div>'
            f'<footer><span class="tag">{html.escape(path or "")}{" / " + html.escape(source) if source and source != path else ""}</span>'
            f'<span class="live">{why}</span></footer></article>'
        )

    def section(title, note, names):
        names = sorted(names, key=lambda n: -dist(live.get(n), seeds[n][1]))
        cards = "".join(card(n) for n in names)
        return (
            f'<section class="group"><div class="ghead"><h2>{html.escape(title)} <span>{len(names)}</span></h2>'
            f'<p>{html.escape(note)}</p></div><div class="grid">{cards}</div></section>'
        )

    body = section(
        "Never reviewed: galleries of 1-3 images",
        "The lab only measured characters with 4 or more images, so these are new to you. "
        "Largest change from the site's current colour first.",
        new,
    )
    if drifted:
        body += section(
            "Changed since you reviewed them",
            "Their gallery grew or changed after the lab's copy, so V43 now lands elsewhere.",
            drifted,
        )
    page = f"""<title>Accent Rollout Check</title>
<style>{CSS}
.group {{ display: flex; flex-direction: column; gap: 10px; }}
.ghead {{ display: flex; flex-direction: column; gap: 2px; padding-top: 8px; }}
.ghead h2 {{ font-size: 1.05rem; font-weight: 600; margin: 0; }}
.ghead h2 span {{ font-weight: 500; color: var(--ink-3); }}
.ghead p {{ margin: 0; color: var(--ink-2); font-size: 13px; max-width: 78ch; }}
</style>
<div class="wrap">
  <div class="intro">
    <h1>Accent rollout check</h1>
    <p>The V43 accents about to be imported, beside the colour each character shows on the site today. Of the {len(seeds)} characters with a gallery, {same_as_lab} are exactly what you reviewed in the lab; {changed_live} differ visibly from what the site shows now (the site still runs the original extractor). Shown here are only the ones you have not seen as V43.</p>
  </div>
  {body}
</div>
"""
    out = work / "review.html"
    out.write_text(page)
    print(f"review page: {out} ({len(new)} never reviewed, {len(drifted)} changed since reviewed)")


# ---- import (server) ----------------------------------------------------------------


def import_bundle(bundle: Path, *, apply: bool, queue_rest: bool) -> None:
    import accent_extract
    import accent_models
    import db

    src = sqlite3.connect(f"file:{bundle}?mode=ro", uri=True)
    version = dict(src.execute("SELECT key, value FROM meta").fetchall()).get("data_version")
    if version != accent_models.DATA_VERSION:
        sys.exit(f"bundle data version {version} != {accent_models.DATA_VERSION}; recompute it")

    conn = db.get_connection()
    live_ids = {r[0] for r in conn.execute("SELECT id FROM custom_images")}
    counts = dict.fromkeys(
        ("image data", "main data", "seeds written", "queued (changed)", "overrides kept",
         "unknown characters", "queued (not in bundle)"),
        0,
    )  # fmt: skip

    rows = [r for r in src.execute("SELECT * FROM image_data") if r[0] in live_ids]
    counts["image data"] = len(rows)
    mains = list(src.execute("SELECT * FROM main_data"))
    counts["main data"] = len(mains)
    if apply:
        # Short transactions: the site keeps writing while this runs, and a long
        # one would hold SQLite's write lock past the API's 5-second wait.
        for table, key, batch_rows in (
            ("accent_image_data", "image_id", rows),
            ("accent_main_data", "url", mains),
        ):
            for i in range(0, len(batch_rows), 200):
                with db.transaction() as c:
                    c.executemany(
                        f"INSERT OR REPLACE INTO {table}"
                        f" ({key}, version, data, face_hair, n_faces, computed_at)"
                        " VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                        batch_rows[i : i + 200],
                    )

    covered = set()
    for name, seed, hue, source, _path, _reason, ids_json, main_url, missing, _at in src.execute(
        "SELECT * FROM seeds"
    ):
        state = accent_extract.accent_state(name)
        if state is None:
            counts["unknown characters"] += 1
            continue
        covered.add(name)
        if state["accent_override"]:
            counts["overrides kept"] += 1
            continue
        fingerprint = accent_extract.gallery_fingerprint(name)
        unchanged = fingerprint[2] == json.loads(ids_json) and (
            state["main_image_url"] or None
        ) == (main_url or None)
        if unchanged:
            counts["seeds written"] += 1
            if apply:
                result = {"seed": seed, "hue": hue, "source": source} if seed else None
                accent_extract._store_accent(
                    name, result, fingerprint, main_url, partial=bool(missing),
                    version=accent_extract.V43,
                )  # fmt: skip
        else:
            counts["queued (changed)"] += 1
            if apply:
                db.enqueue_accent(name, priority=0)

    if queue_rest:
        for (name,) in conn.execute(
            "SELECT name FROM characters WHERE accent_override IS NULL"
            " AND (accent_version IS NULL OR accent_version != ?)",
            (accent_extract.V43,),
        ).fetchall():
            if name not in covered:
                counts["queued (not in bundle)"] += 1
                if apply:
                    db.enqueue_accent(name, priority=0)

    print(("APPLIED" if apply else "DRY RUN -- nothing written; add --apply") + ":")
    for k, v in counts.items():
        print(f"  {k:26s} {v}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--work", type=Path, default=WORK)
    c = sub.add_parser("compute")
    c.add_argument("--work", type=Path, default=WORK)
    c.add_argument("--lab-cache", type=Path, default=None, help="scripts/accent_lab/.data")
    r = sub.add_parser("review")
    r.add_argument("--work", type=Path, default=WORK)
    r.add_argument("--reviewed", type=Path, default=None, help="scripts/accent_lab/.data/full_v43")
    i = sub.add_parser("import")
    i.add_argument("bundle", type=Path)
    i.add_argument("--apply", action="store_true")
    i.add_argument("--queue-rest", action="store_true")
    args = parser.parse_args()
    if args.cmd == "snapshot":
        snapshot(args.work)
    elif args.cmd == "compute":
        compute(args.work, args.lab_cache)
    elif args.cmd == "review":
        review(args.work, args.reviewed)
    else:
        import logs

        logs.setup()
        import_bundle(args.bundle, apply=args.apply, queue_rest=args.queue_rest)


if __name__ == "__main__":
    main()
