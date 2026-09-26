"""The accent sample page: main image, gallery images and the chosen accent per character.

    uv run python -m scripts.accent_lab.sample              # pick the random characters
    uv run python -m scripts.accent_lab.fetch_live ...       # fetch them (sample prints names)
    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.showcase

Reads `.data/sample.json` and `.data/problem_names.txt` (one name per line: the
characters from the owner's reviews), runs `method_v24` on every image of each,
and writes a self-contained HTML page (images embedded) to `.data/accent-sample.html`.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re

from PIL import Image

from . import lab
from . import methods as M

D = lab.DATA


def compute():
    sample = json.loads((D / "sample.json").read_text())
    problems = [n.strip() for n in (D / "problem_names.txt").read_text().splitlines() if n.strip()]
    entries = [(p["band"], p["name"]) for p in sample["picked"]] + [
        ("problem", n) for n in problems
    ]

    def uri(path, box):
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail(box, Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=72)
        return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()

    out = []
    for band, name in entries:
        _, p, g = lab.load_character(f"live:{name}", None)
        tr = []
        r = M.v24(p, g, tr)
        meta = json.loads((lab.LIVE / lab.slug(name) / "meta.json").read_text())
        picks = g[:: max(1, len(g) // 4)][:4] if len(g) > 4 else g
        out.append(
            {
                "band": band,
                "name": name,
                "count": len(g),
                "seed": r["seed"] if r else None,
                "L": round(r["lightness"], 2) if r else None,
                "C": round(r["chroma"], 3) if r else None,
                "live_seed": meta.get("live_accent_seed"),
                "why": tr[0] if tr else "",
                "main": uri(p.info["src"], (220, 300)),
                "customs": [uri(i.info["src"], (240, 240)) for i in picks],
            }
        )
        print(band, name, len(g), r and r["seed"], flush=True)
    return {"seed": sample["seed"], "library": sample["library"], "rows": out}


def render(data):
    rows = data["rows"]

    BANDS = [
        ("top 10%", "Top 10%", "Ranks 1–76"),
        ("10-20%", "10–20%", "Ranks 77–153"),
        ("20-30%", "20–30%", "Ranks 154–229"),
        ("30-50%", "30–50%", "Ranks 230–382"),
        ("50-70%", "50–70%", "Ranks 383–535"),
        ("problem", "Characters from today’s review", "The ones that were wrong at some point"),
    ]

    def reason(why: str) -> str:
        """Short plain-English version of the trace."""
        src = "main image fallback" if why.startswith("main image") else "gallery"
        body = why.split(": ", 1)[-1]
        parts = [p.strip() for p in body.split(";")]
        decision = parts[0]
        if decision.startswith("clear winner"):
            decision = "clear winner"
        elif decision.startswith("tie broken by main image"):
            decision = "tie, broken by the main image"
        elif decision.startswith("two-colour tie, no main image"):
            decision = "tie, no main image: took the stronger side"
        shade = next((p for p in parts if "shaded from" in p), "")
        cls = "pale shade" if "pale" in shade.rsplit("shaded from", 1)[-1] else "saturated shade"
        lifted = any("chroma lifted" in p for p in parts)
        bits = [src, decision, cls + (", boosted" if lifted else "")]
        return " · ".join(bits)

    def card(r):
        seed = r["seed"] or "#999999"
        live = r["live_seed"]
        customs = "".join(
            f'<img class="custom" src="{u}" alt="Gallery image {i + 1} of {html.escape(r["name"])}" loading="lazy">'
            for i, u in enumerate(r["customs"])
        )
        live_chip = (
            f'<span class="live"><i style="background:{live}"></i>on site now {live}</span>'
            if live
            else '<span class="live muted">on site now: none</span>'
        )
        return f"""
    <article class="char">
      <header class="char-head">
        <h3>{html.escape(r["name"])}</h3>
        <span class="count">{r["count"]} image{"s" if r["count"] != 1 else ""}</span>
      </header>
      <div class="char-body">
        <figure class="main">
          <img src="{r["main"]}" alt="Main image of {html.escape(r["name"])}">
          <figcaption>Main image</figcaption>
        </figure>
        <div class="customs">{customs}</div>
        <figure class="accent">
          <div class="swatch" style="background:{seed}" aria-label="Accent colour {seed}"></div>
          <figcaption><strong>{seed}</strong><span>L {r["L"]} · C {r["C"]}</span></figcaption>
        </figure>
      </div>
      <footer class="char-foot">
        <span class="why">{html.escape(reason(r["why"]))}</span>
        {live_chip}
      </footer>
    </article>"""

    sections = []
    for key, title, sub in BANDS:
        members = [r for r in rows if r["band"] == key]
        if not members:
            continue
        counts = [r["count"] for r in members]
        extra = (
            f"{sub} · sampled here: {min(counts)}–{max(counts)} images" if key != "problem" else sub
        )
        sections.append(
            f'<section class="band" id="{re.sub("[^a-z0-9]+", "-", key)}"><div class="band-head"><h2>{title}</h2><p>{extra}</p></div><div class="grid">'
            + "".join(card(r) for r in members)
            + "</div></section>"
        )

    nav = "".join(
        f'<a href="#{re.sub("[^a-z0-9]+", "-", k)}">{t if k != "problem" else "Today’s characters"}</a>'
        for k, t, _ in BANDS
    )

    page = f"""<title>Accent Sample Check</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
    <style>
    :root {{
      --ground: #f5f7f9; --surface: #ffffff; --hairline: #e2e6ec; --hairline-strong: #c8cdd7;
      --ink: #1c2029; --ink-2: #5c6575; --ink-3: #7c8595; --accent: #0b7285;
      --chip: #f1f3f6;
      --sans: Geist, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        color-scheme: dark;
        --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
        --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
      }}
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --ground: #14171d; --surface: #1a1e26; --hairline: #2e3440; --hairline-strong: #444c5a;
      --ink: #e8ebf0; --ink-2: #a2aab8; --ink-3: #7c8595; --accent: #3fb3c7; --chip: #222732;
    }}
    * {{ box-sizing: border-box; }}
    body {{ background: var(--ground); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.5;
      margin: 0; padding-inline: max(16px, 3vw); padding-block: 28px 56px; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; display: flex; flex-direction: column; gap: 36px; }}
    .intro {{ display: flex; flex-direction: column; gap: 10px; }}
    .intro h1 {{ font-size: clamp(1.5rem, 3.2vw, 1.875rem); font-weight: 700; letter-spacing: -0.015em; line-height: 1.25; margin: 0; text-wrap: balance; }}
    .intro p {{ margin: 0; color: var(--ink-2); max-width: 70ch; }}
    .facts {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; }}
    .facts b {{ color: var(--ink); font-weight: 500; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    nav a {{ font-size: 12.5px; color: var(--ink-2); text-decoration: none; padding: 4px 10px; border: 1px solid var(--hairline); border-radius: 999px; background: var(--surface); }}
    nav a:hover {{ color: var(--ink); border-color: var(--hairline-strong); }}
    nav a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .note {{ font-size: 13px; color: var(--ink-2); border-left: 2px solid var(--hairline-strong); padding: 2px 0 2px 12px; max-width: 80ch; }}
    .band {{ display: flex; flex-direction: column; gap: 14px; scroll-margin-top: 16px; }}
    .band-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; border-bottom: 1px solid var(--hairline); padding-bottom: 8px; }}
    .band-head h2 {{ font-size: 1.125rem; font-weight: 600; letter-spacing: -0.01em; margin: 0; }}
    .band-head p {{ margin: 0; color: var(--ink-3); font-size: 12.5px; font-variant-numeric: tabular-nums; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 10px; }}
    .char {{ background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }}
    .char-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
    .char-head h3 {{ font-size: 0.95rem; font-weight: 600; margin: 0; letter-spacing: -0.01em; }}
    .count {{ font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .char-body {{ display: grid; grid-template-columns: 112px minmax(0, 1fr) 128px; gap: 14px; align-items: start; }}
    figure {{ margin: 0; display: flex; flex-direction: column; gap: 6px; }}
    figcaption {{ font-size: 11.5px; color: var(--ink-3); }}
    .main img {{ width: 112px; height: 160px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }}
    .customs {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }}
    .custom {{ width: 100%; height: 160px; object-fit: cover; border-radius: 6px; border: 1px solid var(--hairline); display: block; }}
    .swatch {{ width: 128px; height: 128px; border-radius: 8px; border: 1px solid var(--hairline); }}
    .accent figcaption {{ display: flex; flex-direction: column; gap: 1px; font-family: var(--mono); font-variant-numeric: tabular-nums; }}
    .accent strong {{ color: var(--ink); font-weight: 500; font-size: 13px; }}
    .char-foot {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 16px; font-size: 12px; color: var(--ink-3); border-top: 1px solid var(--hairline); padding-top: 8px; }}
    .live {{ display: inline-flex; align-items: center; gap: 6px; font-family: var(--mono); font-size: 11.5px; }}
    .live i {{ width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--hairline-strong); display: inline-block; }}
    .live.muted {{ color: var(--ink-3); }}
    @media (max-width: 760px) {{
      .char-body {{ grid-template-columns: 96px minmax(0, 1fr); }}
      .main img {{ width: 96px; height: 136px; }}
      .customs {{ grid-template-columns: repeat(2, minmax(0, 1fr)); grid-column: 1 / -1; grid-row: 2; }}
      .custom {{ height: 120px; }}
      .accent {{ grid-column: 2; grid-row: 1; }}
      .swatch {{ width: 100%; height: 96px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
    html {{ scroll-behavior: smooth; }}
    </style>
    <div class="wrap">
      <div class="intro">
        <h1>Accent Sample Check</h1>
        <p>Accent colours from the current candidate extractor (V24 in the accent lab) for five random characters from each image-count band of the live library, plus the characters from today’s review. Each row shows the main image, four gallery images spread across the character’s gallery, and the accent the extractor picked.</p>
        <div class="facts">
          <span><b>{data["library"]}</b> characters ranked by image count</span>
          <span>Random seed <b>{data["seed"]}</b></span>
          <span>Only characters whose main image loads were sampled</span>
          <span>Every image measured, not a sample</span>
        </div>
      </div>
      <nav aria-label="Bands">{nav}</nav>
      <p class="note">Worth checking by eye: 8 of the 25 random picks landed on a red. Some are right, but blush and lips sit in the same hue range and the skin damping does not reach them. The small chip on each row is the colour the site shows today, for comparison.</p>
      {"".join(sections)}
    </div>
    """
    return page


def main() -> None:
    out = D / "accent-sample.html"
    out.write_text(render(compute()))
    print(out)


if __name__ == "__main__":
    main()
