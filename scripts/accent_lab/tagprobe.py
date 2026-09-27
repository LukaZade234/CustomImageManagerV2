"""What colour tags does the WD tagger give each character's gallery? (ACCENT.md §41)

Model (378 MB, Apache-2.0) into scripts/accent_lab/.data/skin/:
  curl -L -o wd-vit.onnx https://huggingface.co/SmilingWolf/wd-vit-tagger-v3/resolve/main/model.onnx
  curl -L -o wd-tags.csv https://huggingface.co/SmilingWolf/wd-vit-tagger-v3/resolve/main/selected_tags.csv
Run from the repo root:
  uv run --no-project --with numpy --with onnxruntime --with pillow \
      python scripts/accent_lab/tagprobe.py "Gon Freecss|Audrey Hall"
"""

import csv
import json
import os
import re
import sys
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

D = "scripts/accent_lab/.data"
o = ort.SessionOptions()
o.intra_op_num_threads = 8
S = ort.InferenceSession(f"{D}/skin/wd-vit.onnx", o, providers=["CPUExecutionProvider"])
with open(f"{D}/skin/wd-tags.csv", newline="") as f:
    tags = [r["name"] for r in csv.DictReader(f)]
COLOURS = "red|orange|yellow|green|aqua|blue|purple|pink|brown|black|white|grey|blonde|silver|gold"
PARTS = "hair|eyes|dress|shirt|jacket|skirt|shorts|kimono|coat|bow|ribbon|hoodie|sweater|cape|gloves|bodysuit|leotard|headwear|hat|pants|necktie|scarf|clothes"
pat = re.compile(rf"^({COLOURS})_({PARTS})$")


def prep(p):
    im = Image.open(p).convert("RGB")
    s = max(im.size)
    c = Image.new("RGB", (s, s), (255, 255, 255))
    c.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    a = np.asarray(c.resize((448, 448), Image.BICUBIC), np.float32)[:, :, ::-1]
    return np.ascontiguousarray(a[None])


def slug(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


t_all = 0
n_all = 0
for name in sys.argv[1].split("|"):
    with open(f"{D}/live/{slug(name)}/meta.json") as f:
        meta = json.load(f)
    paths = [f"{D}/live/{slug(name)}/thumbs/{i}.webp" for i in meta["image_ids"]]
    paths = [p for p in paths if os.path.isfile(p)][:40]
    hits = {}
    for p in paths:
        t = time.perf_counter()
        y = S.run(None, {"input": prep(p)})[0][0]
        t_all += time.perf_counter() - t
        n_all += 1
        for i in np.nonzero(y >= 0.35)[0]:
            if pat.match(tags[i]):
                hits[tags[i]] = hits.get(tags[i], 0) + 1
    top = sorted(hits.items(), key=lambda x: -x[1])[:6]
    print(
        f"{name[:20]:20s} ({len(paths):2d}) "
        + ", ".join(f"{k} {v / len(paths):.0%}" for k, v in top)
    )
print(f"\n{1000 * t_all / n_all:.0f} ms per image (8 threads)")
