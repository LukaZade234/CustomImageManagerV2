"""Contact sheet: each character's art beside one swatch per method.

    uv run python -m scripts.accent_lab.sheet current,v8,v12 [--ids 2,59,live:Lynae]

Reads `.data/library.json` (from library.py); writes `.data/sheet.png`.
Colours are judged by eye here -- the panel only checks hue ranges.
"""

from __future__ import annotations

import argparse
import json

from PIL import Image, ImageDraw

from . import lab

TW, TH, SW = 90, 110, 110


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("methods")
    parser.add_argument("--ids", default="", help="comma-separated ids to show (default: all)")
    args = parser.parse_args()
    names = args.methods.split(",")
    rows = json.loads((lab.DATA / "library.json").read_text())
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        rows = [r for r in rows if str(r["id"]) in wanted]
    width = 6 * TW + len(names) * (SW + 10) + 220
    sheet = Image.new("RGB", (width, len(rows) * (TH + 6) + 30), "white")
    d = ImageDraw.Draw(sheet)
    for j, m in enumerate(names):
        d.text((6 * TW + 10 + j * (SW + 10), 8), m, fill="black")
    for k, r in enumerate(rows):
        y = 30 + k * (TH + 6)
        _, _, gallery = lab.load_character(r["id"], None)
        for j, t in enumerate(gallery[:: max(1, len(gallery) // 6)][:6]):
            t = t.copy()
            t.thumbnail((TW - 4, TH))
            sheet.paste(t, (j * TW, y))
        for j, m in enumerate(names):
            x = 6 * TW + 10 + j * (SW + 10)
            s = r.get(m)
            if s:
                sheet.paste(Image.new("RGB", (SW - 10, TH - 30), s["seed"]), (x, y))
                d.text((x, y + TH - 26), f"{s['seed']} L{s['lightness']:.2f}", fill="black")
            else:
                d.rectangle((x, y, x + SW - 10, y + TH - 30), outline="gray")
                d.text((x + 20, y + 30), "declined", fill="gray")
        d.text((width - 210, y + 30), f"{r['name'][:28]}\n{r['n']} imgs", fill="black")
    out = lab.DATA / "sheet.png"
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
