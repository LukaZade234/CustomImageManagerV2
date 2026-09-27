"""Does the app's accent_v43.py reproduce the lab's V43, seed for seed?

    uv run --with numpy --with onnxruntime python -m scripts.accent_lab.portcheck [--limit N] ["Name|Name"]

Builds `accent_v43.Prepared` inputs from the lab's own caches -- the cut-out masks
and face-parser labels the lab measured with, resized exactly as the lab's
`foreground_only` resizes them -- runs `accent_v43.decide`, and compares the seed
with the lab's recorded V43 result (`.data/full_v43/`, written by
`fullcheck --method v43 --out full_v43 compute`). Any difference is printed with
both traces.

--fresh runs the app's own models (accent_models.prepare) instead of reading the
lab's caches: the end-to-end check, from thumbnail to seed.
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image

from . import faceparse as FP
from . import lab, seg
from . import methods as M

REF = lab.DATA / "full_v43"


def prepared(img):
    """The lab image as accent_v43 input: measurement copy, mask, labels and hair at 200px."""
    import accent_v43 as V

    src = img.info["src"]
    full = M._full_res(src)
    m = seg.mask_for(full)
    if m.shape[::-1] != img.size:
        m = (
            np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR))
            / 255.0
        )
    labels, faces = FP.labels_and_faces(full)
    shape = (img.size[1], img.size[0])
    if labels.shape != shape:
        labels = np.asarray(Image.fromarray(labels).resize(img.size, Image.NEAREST))
        faces = np.asarray(Image.fromarray(faces).resize(img.size, Image.NEAREST))
    hair, n = M._face_hair(src)
    return V.Prepared(
        rgb=np.asarray(img.convert("RGB")),
        mask=m >= M.FG_THRESHOLD,
        labels=labels,
        faces=faces,
        face_hair=hair,
        n_faces=n,
    )


FRESH = False
_models = None


def prepared_fresh(img):
    """The same input produced by the app's models, from the source file."""
    import accent_models

    global _models
    if _models is None:
        _models = accent_models.Models()
    full = M._full_res(img.info["src"])
    data = accent_models.prepare(_models, full)
    return data.prepared(np.asarray(accent_models.measurement_copy(full)))


def _one(name):
    import accent_v43 as V

    build = prepared_fresh if FRESH else prepared

    ref = REF / f"{lab.slug(name)}.json"
    if not ref.is_file():
        return name, None, None, "no reference"
    want = json.loads(ref.read_text()).get("seed")
    _, portrait, gallery = lab.load_character(f"live:{name}", None)
    p = build(portrait) if portrait is not None else None
    g = [build(i) for i in gallery]
    r = V.decide(p, g)
    got = r.seed["seed"] if r.seed else None
    return name, want, got, r.reason


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="?", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--fresh", action="store_true", help="run the app's models, no caches")
    args = parser.parse_args()
    global FRESH
    FRESH = args.fresh
    if args.names:
        names = args.names.split("|")
    else:
        names = [json.loads(f.read_text())["name"] for f in sorted(REF.glob("*.json"))]
    if args.limit:
        names = names[: args.limit]
    same = differ = 0
    with Pool(args.workers) as pool:
        for name, want, got, why in pool.imap_unordered(_one, names, chunksize=2):
            if want == got:
                same += 1
                continue
            differ += 1
            print(f"DIFF {name}: lab {want}  port {got}\n     port: {why}", flush=True)
    print(f"{same} identical, {differ} different, of {same + differ}")
    sys.exit(1 if differ else 0)


if __name__ == "__main__":
    main()
