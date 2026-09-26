"""Scan characters for colour profiles and show what the V30 paths change.

    uv run python -m scripts.accent_lab.fetch_live ...   # the names in .data/scan.json
    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.profiles

Reads `.data/scan.json` (from the scan picker: every character with 10-30
images plus random draws from the other bands) and profiles each character on
its cut-out images: how much of the art carries real colour, how much of the
colour is pink/red, and how much of that pink/red is pale. It runs V29 and V30
on every one, writes `.data/profiles.json`, and builds `.data/profiles.html`:

- the characters V30 sends down the monochrome path,
- the characters it sends down the pale-pink path,
- near misses just short of either threshold, to judge where the lines sit,
- an unchanged sample, weighted toward 10-30 images.
"""

from __future__ import annotations

import base64
import html
import io
import json
import random

from PIL import Image

from . import lab
from . import methods as M

D = lab.DATA
EXTRA = [
    "2B",
    "A2",
    "The Sandman",
    "Tewi Inaba",
    "Nadeko Sengoku",
    "Sakurako Kawawa",
    "Mitsuri Kanroji",
]


def _uri(path, box):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail(box, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=70)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def _path(prof, has_images):
    """Which V30 path a profile selects (mirrors methods.v30)."""
    if not has_images:
        return "standard"
    if prof["chromatic"] < M.MONO_MAX_CHROMATIC:
        return "monochrome"
    if prof["pink"] >= M.PINK_MIN_SHARE and prof["pale_in_pink"] >= M.PINK_MIN_PALE:
        return "pale-pink"
    return "standard"


def scan(scan_file="scan.json"):
    """Profile every character (cheap); full colour runs happen only for those shown."""
    entries = json.loads((D / scan_file).read_text())
    seen = {e["name"] for e in entries}
    entries += [{"band": "known", "name": n, "count": None} for n in EXTRA if n not in seen]
    rows = []
    for k, e in enumerate(entries):
        try:
            name, p, g = lab.load_character(f"live:{e['name']}", None)
        except FileNotFoundError:
            continue
        if not g:
            continue
        _, fg = M._segmented(p, g, drop_scenes=True)
        prof = M.colour_profile(fg)
        rows.append({
            "band": e["band"], "name": name, "count": len(g), "portrait": bool(p),
            "profile": prof, "path": _path(prof, bool(fg)), "v29": None, "v30": None,
        })  # fmt: skip
        print(k, name, len(g), rows[-1]["path"], flush=True)
    shown = {r["name"] for _, _, _, members in _groups(rows) for r in members}
    for r in rows:
        if r["name"] not in shown:
            continue
        _, p, g = lab.load_character(f"live:{r['name']}", None)
        old = M.v29(p, g)
        tr: list[str] = []
        new = M.v30(p, g, tr) if r["path"] != "standard" else old
        r["v29"] = old["seed"] if old else None
        r["v30"] = new["seed"] if new else None
        print("colour", r["name"], r["path"], r["v29"], r["v30"], flush=True)
    (D / "profiles.json").write_text(json.dumps(rows, indent=1))
    return rows


def _groups(rows):
    mono = [r for r in rows if r["path"] == "monochrome"]
    pink = [r for r in rows if r["path"] == "pale-pink"]
    std = [r for r in rows if r["path"] == "standard"]
    near_mono = [r for r in std if r["profile"]["chromatic"] < M.MONO_MAX_CHROMATIC + 0.06]
    near_pink = [
        r
        for r in std
        if r["profile"]["pink"] >= M.PINK_MIN_SHARE - 0.1
        and r["profile"]["pale_in_pink"] >= M.PINK_MIN_PALE - 0.04
        and r not in near_mono
    ]
    rest = [r for r in std if r not in near_mono and r not in near_pink and r["band"] != "known"]
    rng = random.Random(7)
    sample = []
    for band, k in (("10-30", 16), ("5-9", 4), ("1-4", 3), ("31-60", 4), ("61+", 2)):
        pool = [r for r in rest if r["band"] == band]
        sample += rng.sample(pool, min(k, len(pool)))
    return [
        ("mono", "Monochrome path", f"Under {M.MONO_MAX_CHROMATIC:.0%} of the character's pixels carry real colour. The accent is the dominant tone with a faint tint.", mono),
        ("pink", "Pale-pink path", f"At least {M.PINK_MIN_SHARE:.0%} of the colour is pink/red and at least {M.PINK_MIN_PALE:.0%} of that is pale. Pale pink counts as the character's colour instead of skin.", pink),
        ("near", "Near misses", "Just short of either threshold, left on the standard path. These show where the lines sit.", near_mono + near_pink),
        ("rest", "Unchanged sample", "Standard path, drawn at random, weighted toward characters with 10–30 images. V29 and V30 give the same colour here.", sample),
    ]  # fmt: skip


def render(rows):
    groups = _groups(rows)
    n_mono = sum(r["path"] == "monochrome" for r in rows)
    n_pink = sum(r["path"] == "pale-pink" for r in rows)
    by_band = {}
    for r in rows:
        by_band.setdefault(r["band"], []).append(r)

    def card(r):
        folder = lab.LIVE / lab.slug(r["name"])
        meta = json.loads((folder / "meta.json").read_text())
        ids = [str(i) for i in meta["image_ids"]]
        picks = ids[:: max(1, len(ids) // 4)][:4]
        customs = "".join(
            f'<img class="custom" src="{_uri(folder / "thumbs" / f"{i}.webp", (240, 240))}" alt="Gallery image of {html.escape(r["name"])}" loading="lazy">'
            for i in picks
            if (folder / "thumbs" / f"{i}.webp").is_file()
        )
        portraits = sorted(folder.glob("portrait.*"))
        main = (
            f'<img src="{_uri(portraits[0], (220, 300))}" alt="Main image of {html.escape(r["name"])}">'
            if portraits
            else '<div class="nomain">No main image yet</div>'
        )
        p = r["profile"]
        changed = r["v29"] != r["v30"]

        def swatch(label, seed, strong):
            if not seed:
                return f'<figure class="sw"><div class="swatch none">none</div><figcaption>{label}</figcaption></figure>'
            d = lab.describe(seed)
            return (
                f'<figure class="sw{" strong" if strong else ""}"><div class="swatch" style="background:{seed}"></div>'
                f"<figcaption><span>{label}</span><strong>{seed}</strong><span>L {d['lightness']:.2f} · C {d['chroma']:.3f}</span></figcaption></figure>"
            )

        return f"""
<article class="char">
  <header class="char-head"><h3>{html.escape(r["name"])}</h3><span class="count">{r["count"]} images</span></header>
  <div class="char-body">
    <figure class="main">{main}</figure>
    <div class="customs">{customs}</div>
    <div class="swatches">{swatch("V29", r["v29"], False)}{swatch("V30", r["v30"], changed)}</div>
  </div>
  <footer class="char-foot">
    <span class="meter" title="share of pixels with real colour">colour <b>{p["chromatic"]:.0%}</b></span>
    <span class="meter" title="share of the colour that is pink or red">pink/red <b>{p["pink"]:.0%}</b></span>
    <span class="meter" title="share of the pink/red that is pale">pale within <b>{p["pale_in_pink"]:.0%}</b></span>
    <span class="path path-{r["path"]}">{r["path"]} path</span>
  </footer>
</article>"""

    sections = []
    for key, title, sub, members in groups:
        if not members:
            continue
        members = sorted(members, key=lambda r: r["count"] or 0)
        sections.append(
            f'<section class="band" id="{key}"><div class="band-head"><h2>{title} <span class="n">{len(members)}</span></h2><p>{sub}</p></div>'
            + "".join(card(r) for r in members)
            + "</section>"
        )
    nav = "".join(f'<a href="#{k}">{t}</a>' for k, t, _, m in groups if m)
    scanned = ", ".join(
        f"{b}: {len(by_band.get(b, []))}"
        for b in ("10-30", "5-9", "1-4", "31-60", "61+")
        if by_band.get(b)
    )
    return f"""<title>Colour Profile Paths</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
<style>
:root {{
  --ground: #f5f7f9; --surface: #ffffff; --hairline: #e2e6ec; --hairline-strong: #c8cdd7;
  --ink: #1c2029; --ink-2: #5c6575; --ink-3: #7c8595; --accent: #0b7285; --chip: #f1f3f6;
  --mono-tag: #444c5a; --pink-tag: #a3456a;
  --sans: Geist, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark; --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
    --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
    --mono-tag: #c8cdd7; --pink-tag: #e58fb2;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark; --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
  --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
  --mono-tag: #c8cdd7; --pink-tag: #e58fb2;
}}
* {{ box-sizing: border-box; }}
body {{ background: var(--ground); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.5;
  margin: 0; padding-inline: max(16px, 3vw); padding-block: 28px 56px; }}
.wrap {{ max-width: 1180px; margin: 0 auto; display: flex; flex-direction: column; gap: 32px; }}
.intro {{ display: flex; flex-direction: column; gap: 10px; }}
.intro h1 {{ font-size: clamp(1.5rem, 3.2vw, 1.875rem); font-weight: 700; letter-spacing: -0.015em; line-height: 1.25; margin: 0; }}
.intro p {{ margin: 0; color: var(--ink-2); max-width: 72ch; }}
.facts {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; }}
.facts b {{ color: var(--ink); font-weight: 500; }}
nav {{ display: flex; flex-wrap: wrap; gap: 6px; }}
nav a {{ font-size: 12.5px; color: var(--ink-2); text-decoration: none; padding: 4px 10px; border: 1px solid var(--hairline); border-radius: 999px; background: var(--surface); }}
nav a:hover {{ color: var(--ink); border-color: var(--hairline-strong); }}
nav a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.band {{ display: flex; flex-direction: column; gap: 10px; scroll-margin-top: 16px; }}
.band-head {{ display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid var(--hairline); padding-bottom: 8px; }}
.band-head h2 {{ font-size: 1.125rem; font-weight: 600; letter-spacing: -0.01em; margin: 0; display: flex; align-items: baseline; gap: 8px; }}
.band-head .n {{ font-size: 12px; font-weight: 500; color: var(--ink-3); font-variant-numeric: tabular-nums; }}
.band-head p {{ margin: 0; color: var(--ink-3); font-size: 12.5px; max-width: 90ch; }}
.char {{ background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }}
.char-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
.char-head h3 {{ font-size: 0.95rem; font-weight: 600; margin: 0; letter-spacing: -0.01em; }}
.count {{ font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.char-body {{ display: grid; grid-template-columns: 104px minmax(0, 1fr) 232px; gap: 14px; align-items: start; }}
figure {{ margin: 0; }}
.main img, .nomain {{ width: 104px; height: 150px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }}
.nomain {{ display: grid; place-items: center; font-size: 11px; color: var(--ink-3); text-align: center; background: var(--chip); }}
.customs {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }}
.custom {{ width: 100%; height: 150px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }}
.swatches {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.sw {{ display: flex; flex-direction: column; gap: 6px; }}
.swatch {{ width: 100%; aspect-ratio: 1; max-width: 100%; border-radius: 8px; border: 1px solid var(--hairline); }}
.swatch.none {{ display: grid; place-items: center; color: var(--ink-3); font-size: 12px; background: var(--chip); }}
.sw figcaption {{ display: flex; flex-direction: column; font-family: var(--mono); font-size: 11.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; }}
.sw figcaption strong {{ color: var(--ink); font-weight: 500; font-size: 12.5px; }}
.sw.strong .swatch {{ border: 2px solid var(--ink); }}
.char-foot {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; font-size: 12px; color: var(--ink-3); border-top: 1px solid var(--hairline); padding-top: 8px; font-variant-numeric: tabular-nums; }}
.meter b {{ color: var(--ink); font-weight: 500; }}
.path {{ margin-left: auto; font-size: 11.5px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--hairline-strong); color: var(--ink-2); }}
.path-monochrome {{ color: var(--mono-tag); border-color: var(--mono-tag); }}
.path-pale-pink {{ color: var(--pink-tag); border-color: var(--pink-tag); }}
@media (max-width: 760px) {{
  .char-body {{ grid-template-columns: 96px minmax(0, 1fr); }}
  .customs {{ grid-template-columns: repeat(2, minmax(0, 1fr)); grid-column: 1 / -1; grid-row: 2; }}
  .custom {{ height: 120px; }}
  .main img, .nomain {{ width: 96px; height: 136px; }}
}}
html {{ scroll-behavior: smooth; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
</style>
<div class="wrap">
  <div class="intro">
    <h1>Colour Profile Paths</h1>
    <p>V30 profiles each character before choosing an accent. Mostly black-and-white characters take a monochrome path, and characters whose colour is almost all pink with a real share of pale pink take a pale-pink path. Everyone else keeps V29. Each row shows V29 and V30 side by side; a bold border marks a colour V30 changed.</p>
    <div class="facts">
      <span><b>{len(rows)}</b> characters scanned ({scanned}, plus earlier examples)</span>
      <span><b>{n_mono}</b> on the monochrome path</span>
      <span><b>{n_pink}</b> on the pale-pink path</span>
      <span>Every image measured, on the cut-out character</span>
    </div>
  </div>
  <nav aria-label="Sections">{nav}</nav>
  {"".join(sections)}
</div>
"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true", help="reuse .data/profiles.json")
    parser.add_argument("--scan", default="scan.json", help="which scan list in .data to use")
    args = parser.parse_args()
    rows = json.loads((D / "profiles.json").read_text()) if args.render_only else scan(args.scan)
    out = D / "profiles.html"
    out.write_text(render(rows))
    print(out)


if __name__ == "__main__":
    main()
