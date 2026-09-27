"""Run the candidate extractor over a large slice of the live library and build
review pages: main image, four gallery images, the chosen accent, and the colour
the site shows today.

    uv run python -m scripts.accent_lab.fetch_live ...        # names in .data/full_fetch.txt
    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.fullcheck compute
    uv run python -m scripts.accent_lab.fullcheck render

`compute` reads `.data/full_list.json` ([{name, count}]) and writes one result per
character to `.data/full/<slug>.json`, so it can be stopped and resumed. It runs
in parallel worker processes, each with a few onnxruntime threads: several
workers with fewer threads each get through the cut-outs faster than one process
using every thread. `render` builds one page per image-count band, sized to stay
under the 16 MB publish limit.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import time
from multiprocessing import Pool

from PIL import Image

from . import lab

D = lab.DATA
OUT = D / "full"  # results of METHOD; COMPARE_DIR holds the version shown beside it
METHOD = "v33"
COMPARE_DIR = None
COMPARE_LABEL = None
PAGES = [("4–9 images", 4, 9, "full-4-9.html"), ("10+ images", 10, 10**9, "full-10plus.html")]


def _init_worker(threads):
    os.environ["ACCENT_LAB_ORT_THREADS"] = str(threads)


def _one(name):
    from . import methods as M

    target = OUT / f"{lab.slug(name)}.json"
    if target.is_file():
        return name, "cached"
    t = time.perf_counter()
    try:
        _, p, g = lab.load_character(f"live:{name}", None)
    except FileNotFoundError:
        return name, "not fetched"
    meta = json.loads((lab.LIVE / lab.slug(name) / "meta.json").read_text())
    tr: list[str] = []
    r = getattr(M, METHOD)(p, g, tr) if g else None
    why = tr[0] if tr else ""
    path = (
        "monochrome"
        if why.startswith("monochrome")
        else "pale-pink"
        if why.startswith("pale-pink")
        else "standard"
    )
    target.write_text(
        json.dumps(
            {
                "name": name,
                "count": len(g),
                "seed": r["seed"] if r else None,
                "L": round(r["lightness"], 2) if r else None,
                "C": round(r["chroma"], 3) if r else None,
                "path": path,
                "why": why,
                "live_seed": meta.get("live_accent_seed"),
                "portrait": p is not None,
            }
        )
    )
    return name, f"{len(g)} images in {time.perf_counter() - t:.0f}s"


def compute(workers, threads):
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sorted(json.loads((D / "full_list.json").read_text()), key=lambda c: -c["count"])
    names = [c["name"] for c in todo]
    start = time.perf_counter()
    with Pool(workers, initializer=_init_worker, initargs=(threads,)) as pool:
        for k, (name, status) in enumerate(pool.imap_unordered(_one, names, chunksize=1), 1):
            print(
                f"{k}/{len(names)} {time.perf_counter() - start:6.0f}s  {name}: {status}",
                flush=True,
            )
    print("DONE", flush=True)


def _uri(path, box, quality=58):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail(box, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=quality)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def _reason(r):
    why = r["why"]
    if r["path"] == "monochrome":
        if "highlight" in why:
            return "monochrome · highlight colour"
        if "white side" in why:
            return "monochrome · near-white"
        return "monochrome · tinted tone"
    if r["path"] == "pale-pink":
        return "pale pink"
    body = why.split("; ", 1)[-1] if "standard path" in why else why
    if "main image (fallback)" in body:
        return "main-image fallback"
    if "tie broken by main image" in body:
        return "tie, decided by the main image"
    if "no main image" in body:
        return "tie, no main image"
    return "clear winner" if "clear winner" in body or "single colour" in body else "standard"


def _card(r):
    folder = lab.LIVE / lab.slug(r["name"])
    meta = json.loads((folder / "meta.json").read_text())
    ids = [str(i) for i in meta["image_ids"]]
    picks = ids[:: max(1, len(ids) // 4)][:4]
    customs = "".join(
        f'<img class="custom" src="{_uri(folder / "thumbs" / f"{i}.webp", (200, 200))}" alt="" loading="lazy">'
        for i in picks
        if (folder / "thumbs" / f"{i}.webp").is_file()
    )
    portraits = sorted(folder.glob("portrait.*"))
    main = (
        f'<img class="main" src="{_uri(portraits[0], (150, 210))}" alt="Main image of {html.escape(r["name"])}">'
        if portraits
        else '<div class="main nomain">No main image yet</div>'
    )
    seed = r["seed"]
    old = None
    if COMPARE_DIR is not None and (COMPARE_DIR / f"{lab.slug(r['name'])}.json").is_file():
        old = json.loads((COMPARE_DIR / f"{lab.slug(r['name'])}.json").read_text()).get("seed")

    def one(label, sd, strong):
        if not sd:
            return f'<div class="sw"><div class="swatch none">none</div><span>{label}</span></div>'
        return (
            f'<div class="sw{" strong" if strong else ""}"><div class="swatch" style="background:{sd}"></div>'
            f"<span>{label}</span><strong>{sd}</strong></div>"
        )

    if COMPARE_DIR is not None:
        swatch = one(COMPARE_LABEL, old, False) + one(METHOD.upper(), seed, old != seed)
    else:
        swatch = one(METHOD.upper(), seed, False)
    live = r["live_seed"]
    live_chip = (
        f'<span class="live"><i style="background:{live}"></i>site today {live}</span>'
        if live
        else '<span class="live">site today: none</span>'
    )
    return (
        f'<article class="char" data-path="{r["path"]}" data-changed="{"1" if COMPARE_DIR is not None and old != seed else "0"}" data-name="{html.escape(r["name"].lower())}">'
        f'<header><h3>{html.escape(r["name"])}</h3><span class="count">{r["count"]} images</span></header>'
        f'<div class="body">{main}<div class="customs">{customs}</div><div class="accent">{swatch}</div></div>'
        f'<footer><span class="tag tag-{r["path"]}">{html.escape(_reason(r))}</span>{live_chip}</footer>'
        "</article>"
    )


CSS = """
:root {
  --ground: #f5f7f9; --surface: #ffffff; --hairline: #e2e6ec; --hairline-strong: #c8cdd7;
  --ink: #1c2029; --ink-2: #5c6575; --ink-3: #7c8595; --accent: #0b7285; --chip: #f1f3f6;
  --mono-tag: #444c5a; --pink-tag: #a3456a;
  --sans: Geist, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark; --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
    --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
    --mono-tag: #c8cdd7; --pink-tag: #e58fb2;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark; --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
  --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
  --mono-tag: #c8cdd7; --pink-tag: #e58fb2;
}
* { box-sizing: border-box; }
body { background: var(--ground); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.5;
  margin: 0; padding-inline: max(16px, 3vw); padding-block: 24px 56px; }
.wrap { max-width: 1240px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
.intro { display: flex; flex-direction: column; gap: 8px; }
h1 { font-size: clamp(1.4rem, 3vw, 1.75rem); font-weight: 700; letter-spacing: -0.015em; margin: 0; }
.intro p { margin: 0; color: var(--ink-2); max-width: 78ch; }
.facts { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.facts b { color: var(--ink); font-weight: 500; }
.tools { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 2; display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding-block: 10px; background: var(--ground); border-bottom: 1px solid var(--hairline); }
.tools button { font: inherit; font-size: 12.5px; color: var(--ink-2); background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 999px; padding: 4px 11px; cursor: pointer; }
.tools button[aria-pressed="true"] { color: var(--ink); border-color: var(--ink); font-weight: 500; }
.tools button:focus-visible, .tools input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.tools input { font: inherit; font-size: 13px; color: var(--ink); background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 6px; padding: 5px 10px; min-width: 0; flex: 1 1 200px; max-width: 320px; }
.tools .shown { margin-left: auto; font-size: 12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 560px), 1fr)); gap: 10px; }
.char { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px; }
.char header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.char h3 { font-size: 0.92rem; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
.count { font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; white-space: nowrap; }
.body { display: grid; grid-template-columns: 78px minmax(0, 1fr) auto; gap: 10px; align-items: start; }
.main { width: 78px; height: 112px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }
.nomain { display: grid; place-items: center; text-align: center; font-size: 11px; color: var(--ink-3); background: var(--chip); }
.customs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; }
.custom { width: 100%; height: 112px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }
.accent { display: flex; gap: 8px; font-family: var(--mono); font-size: 11px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.sw { display: flex; flex-direction: column; gap: 2px; width: 84px; }
.sw strong { color: var(--ink); font-weight: 500; font-size: 11.5px; }
.sw.strong .swatch { border: 2px solid var(--ink); }
.swatch { width: 84px; height: 72px; border-radius: 8px; border: 1px solid var(--hairline); }
.swatch.none { display: grid; place-items: center; background: var(--chip); font-family: var(--sans); }
.char footer { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; border-top: 1px solid var(--hairline); padding-top: 7px; font-size: 11.5px; color: var(--ink-3); }
.tag { padding: 0 8px; border-radius: 999px; border: 1px solid var(--hairline-strong); color: var(--ink-2); }
.tag-monochrome { color: var(--mono-tag); border-color: var(--mono-tag); }
.tag-pale-pink { color: var(--pink-tag); border-color: var(--pink-tag); }
.live { margin-left: auto; display: inline-flex; align-items: center; gap: 5px; font-family: var(--mono); }
.live i { width: 11px; height: 11px; border-radius: 3px; border: 1px solid var(--hairline-strong); display: inline-block; }
.empty { color: var(--ink-3); font-size: 13px; }
@media (max-width: 520px) {
  .body { grid-template-columns: 70px minmax(0, 1fr); }
  .customs { grid-column: 1 / -1; grid-row: 2; }
  .main { width: 70px; height: 100px; }
  .accent { grid-column: 2; grid-row: 1; }
  .sw { width: 50%; }
  .swatch { width: 100%; height: 60px; }
}
"""

JS = """
(() => {
  const cards = [...document.querySelectorAll('.char')];
  const buttons = [...document.querySelectorAll('.tools button')];
  const search = document.getElementById('search');
  const shown = document.getElementById('shown');
  let path = 'all';
  const apply = () => {
    const q = search.value.trim().toLowerCase();
    let n = 0;
    for (const c of cards) {
      const byPath = path === 'all' || c.dataset.path === path || (path === 'changed' && c.dataset.changed === '1');
      const ok = byPath && (!q || c.dataset.name.includes(q));
      c.hidden = !ok;
      if (ok) n++;
    }
    shown.textContent = n + ' of ' + cards.length + ' shown';
    document.getElementById('empty').hidden = n > 0;
  };
  for (const b of buttons) b.addEventListener('click', () => {
    path = b.dataset.path;
    for (const o of buttons) o.setAttribute('aria-pressed', String(o === b));
    apply();
  });
  search.addEventListener('input', apply);
  apply();
})();
"""


def render():
    rows = [json.loads(p.read_text()) for p in sorted(OUT.glob("*.json"))]
    outputs = []
    for title, lo, hi, fname in PAGES:
        members = sorted(
            (r for r in rows if lo <= r["count"] <= hi), key=lambda r: (r["count"], r["name"])
        )
        n_mono = sum(r["path"] == "monochrome" for r in members)
        n_pink = sum(r["path"] == "pale-pink" for r in members)
        n_nomain = sum(not r["portrait"] for r in members)
        n_none = sum(not r["seed"] for r in members)
        n_changed = 0
        if COMPARE_DIR is not None:
            for r in members:
                f = COMPARE_DIR / f"{lab.slug(r['name'])}.json"
                if f.is_file() and json.loads(f.read_text()).get("seed") != r["seed"]:
                    n_changed += 1
        cards = "".join(_card(r) for r in members)
        page = f"""<title>Accent Check · {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <div class="intro">
    <h1>Accent Check · {title}</h1>
    <p>The candidate extractor ({METHOD.upper()}) on every character in the library with {title.replace("images", "gallery images")}, ordered by image count. Each card shows the main image, four gallery images spread across the gallery, {("the previous version (" + COMPARE_LABEL + ") beside the new one — a bold border marks a colour that changed — and ") if COMPARE_DIR is not None else "the chosen accent and "}the colour the site shows today. Near-white and near-black accents need a small frontend change before the site can display them.</p>
    <div class="facts">
      <span><b>{len(members)}</b> characters</span>
      <span><b>{n_mono}</b> monochrome path</span>
      <span><b>{n_pink}</b> pale-pink path</span>
      <span><b>{n_nomain}</b> without a main image yet</span>
      <span><b>{n_none}</b> with no accent</span>
      {f"<span><b>{n_changed}</b> changed from {COMPARE_LABEL}</span>" if COMPARE_DIR is not None else ""}
    </div>
  </div>
  <div class="tools" role="toolbar" aria-label="Filter characters">
    <button type="button" data-path="all" aria-pressed="true">All</button>
    <button type="button" data-path="monochrome" aria-pressed="false">Monochrome</button>
    <button type="button" data-path="pale-pink" aria-pressed="false">Pale pink</button>
    <button type="button" data-path="standard" aria-pressed="false">Standard</button>
    {'<button type="button" data-path="changed" aria-pressed="false">Changed</button>' if COMPARE_DIR is not None else ""}
    <input id="search" type="search" placeholder="Find a character" aria-label="Find a character">
    <span class="shown" id="shown"></span>
  </div>
  <p class="empty" id="empty" hidden>No characters match. Clear the search or choose All.</p>
  <div class="grid">{cards}</div>
</div>
<script>{JS}</script>
"""
        (D / fname).write_text(page)
        outputs.append((fname, len(members), len(page) / 1e6))
    for fname, n, mb in outputs:
        print(f"{fname}: {n} characters, {mb:.1f} MB")


def main() -> None:
    global METHOD, OUT, COMPARE_DIR, COMPARE_LABEL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", default="v33")
    parser.add_argument("--out", default="full", help="results folder in .data for --method")
    parser.add_argument(
        "--compare", default=None, help="results folder of the version to show beside it"
    )
    parser.add_argument("--compare-label", default="previous")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compute")
    c.add_argument("--workers", type=int, default=6)
    c.add_argument("--threads", type=int, default=4, help="onnxruntime threads per worker")
    sub.add_parser("render")
    args = parser.parse_args()
    METHOD, OUT = args.method, D / args.out
    if args.compare:
        COMPARE_DIR, COMPARE_LABEL = D / args.compare, args.compare_label
    if args.cmd == "compute":
        compute(args.workers, args.threads)
    else:
        render()


if __name__ == "__main__":
    main()
