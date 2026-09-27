"""Skin/body-part model research (ACCENT.md §30): speed, memory, and what each model marks.

Models live in `.data/skin/` (gitignored). Fetch and convert them once (needs torch):
  mkdir -p scripts/accent_lab/.data/skin && cd scripts/accent_lab/.data/skin
  curl -LO https://github.com/siyeong0/Anime-Face-Segmentation/raw/main/model/UNet.pth
  curl -LO https://raw.githubusercontent.com/siyeong0/Anime-Face-Segmentation/main/network.py
  curl -L -o face_n.onnx https://huggingface.co/deepghs/anime_face_detection/resolve/main/face_detect_v1.4_n/model.onnx
  (segformer/: config.json, model.safetensors, preprocessor_config.json from
   huggingface.co/isjackwild/segformer-b0-finetuned-segments-skin-hair-clothing)
  uv run --no-project --with torch --with torchvision --with transformers --with onnx \
      --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
      --index-strategy unsafe-best-match python ../../skinbench.py export

Then, from the repo root:
  uv run --no-project --with numpy --with onnxruntime --with pillow --with requests \
      python -m scripts.accent_lab.skinbench speed | mem <face_n|face_parse|segformer|isnetis> | sheet
"""

import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(__file__).parent / ".data"
HERE = DATA / "skin"
LIVE = DATA / "live"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# face-parse channels (util.PALETTE order, which is how the training masks were read)
BG, HAIR, EYE, MOUTH, FACE, SKIN, CLOTHES = range(7)
COL = {
    HAIR: (230, 40, 40),
    EYE: (40, 80, 255),
    MOUTH: (255, 255, 255),
    FACE: (40, 220, 60),
    SKIN: (250, 230, 30),
    CLOTHES: (220, 40, 220),
}
SF_COL = {1: (250, 230, 30), 2: (230, 40, 40), 3: (220, 40, 220)}  # segformer skin, hair, clothing

CHARS = [
    "himiko-toga",
    "jotaro-kujo",
    "sukuna",
    "aoi-todo",
    "anya-forger",
    "sharron",
    "kim-soleum",
    "izumi-miyamura",
    "chizuru-ichinose",
    "tetsurou-kuroo",
    "jiu-niangzi",
    "loki-loki-laufeyson",
    "makoto-kino",
    "tooth-fairy",
    "eiki-shiki",
    "reze",
    "mitsuri-kanroji",
    "tohru",
]


def session(name, threads=0):
    import onnxruntime as ort

    o = ort.SessionOptions()
    if threads:
        o.intra_op_num_threads = threads
        o.inter_op_num_threads = 1
    return ort.InferenceSession(str(HERE / f"{name}.onnx"), o, providers=["CPUExecutionProvider"])


def square(arr, size, fill=0.0):
    """Letterbox HxWx3 float array into size×size; return canvas, scale, pad."""
    h, w = arr.shape[:2]
    s = size / max(h, w)
    nh, nw = max(1, round(h * s)), max(1, round(w * s))
    img = (
        np.asarray(
            Image.fromarray((arr * 255).astype(np.uint8)).resize((nw, nh), Image.BILINEAR),
            np.float32,
        )
        / 255
    )
    c = np.full((size, size, 3), fill, np.float32)
    py, px = (size - nh) // 2, (size - nw) // 2
    c[py : py + nh, px : px + nw] = img
    return c, s, py, px, nh, nw


def detect_faces(sess, arr, thr=0.278):
    c, s, py, px, _, _ = square(arr, 640, 0.5)
    out = sess.run(None, {"images": c.transpose(2, 0, 1)[None]})[0][0]
    if out.shape[0] < out.shape[1]:
        out = out.T  # (anchors, 5)
    out = out[out[:, 4] > thr]
    boxes = []
    for cx, cy, w, h, conf in sorted(out[:, :5].tolist(), key=lambda r: -r[4]):
        b = (
            (cx - w / 2 - px) / s,
            (cy - h / 2 - py) / s,
            (cx + w / 2 - px) / s,
            (cy + h / 2 - py) / s,
            conf,
        )
        if all(_iou(b, k) < 0.5 for k in boxes):
            boxes.append(b)
    return boxes


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def parse_whole(sess, arr):
    c, s, py, px, nh, nw = square(arr, 512, 1.0)
    p = sess.run(None, {"x": c.transpose(2, 0, 1)[None]})[0][0].argmax(0)[
        py : py + nh, px : px + nw
    ]
    return np.asarray(Image.fromarray(p.astype(np.uint8)).resize(arr.shape[1::-1], Image.NEAREST))


def parse_faces(sess, arr, boxes, grow=2.2):
    """Face parser on a square crop around each face box; labels painted back (0 elsewhere)."""
    h, w = arr.shape[:2]
    lab = np.zeros((h, w), np.uint8)
    for x0, y0, x1, y1, _ in boxes:
        side = max(x1 - x0, y1 - y0) * grow
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.1
        X0, Y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
        X1, Y1 = X0 + int(round(side)), Y0 + int(round(side))
        crop = np.ones((Y1 - Y0, X1 - X0, 3), np.float32)
        sx0, sy0, sx1, sy1 = max(0, X0), max(0, Y0), min(w, X1), min(h, Y1)
        crop[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0] = arr[sy0:sy1, sx0:sx1]
        inp = (
            np.asarray(
                Image.fromarray((crop * 255).astype(np.uint8)).resize((512, 512), Image.BILINEAR),
                np.float32,
            )
            / 255
        )
        p = sess.run(None, {"x": inp.transpose(2, 0, 1)[None]})[0][0].argmax(0).astype(np.uint8)
        p = np.asarray(Image.fromarray(p).resize((X1 - X0, Y1 - Y0), Image.NEAREST))
        region = p[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0]
        cur = lab[sy0:sy1, sx0:sx1]
        cur[region > 0] = region[region > 0]
    return lab


def segformer(sess, arr):
    c, s, py, px, nh, nw = square(arr, 512, 1.0)
    x = (c - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
        [0.229, 0.224, 0.225], np.float32
    )
    p = (
        sess.run(None, {"x": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
        .argmax(0)
        .astype(np.uint8)
    )
    p = np.asarray(Image.fromarray(p).resize((512, 512), Image.NEAREST))[py : py + nh, px : px + nw]
    return np.asarray(Image.fromarray(p).resize(arr.shape[1::-1], Image.NEAREST))


def skin_from_face(arr, lab, fg):
    """Learn this image's skin colour from the parsed face/skin, mark matching pixels everywhere.

    Skin sample = FACE+SKIN pixels, trimmed to their central 80% by lightness. A pixel
    is skin when it lies within the sample's spread in a (L, a, b)-like space.
    """
    face = (lab == FACE) | (lab == SKIN)
    if face.sum() < 150:
        return None
    rgb = arr.reshape(-1, 3)
    # cheap opponent space: lightness + two chroma axes, enough to separate skin from hair/clothes
    L = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    A = rgb[:, 0] - rgb[:, 1]
    B = (rgb[:, 0] + rgb[:, 1]) / 2 - rgb[:, 2]
    f = face.reshape(-1)
    Ls, As, Bs = L[f], A[f], B[f]
    lo, hi = np.percentile(Ls, [10, 90])
    keep = (Ls >= lo) & (Ls <= hi)
    ma, mb = np.median(As[keep]), np.median(Bs[keep])
    ra = max(0.04, 2.5 * np.median(np.abs(As[keep] - ma)))
    rb = max(0.04, 2.5 * np.median(np.abs(Bs[keep] - mb)))
    lmin = max(0.0, np.percentile(Ls[keep], 2) - 0.25)  # shaded skin is allowed darker
    m = ((A - ma) / ra) ** 2 + ((B - mb) / rb) ** 2 <= 1.0
    m &= lmin <= L
    return m.reshape(lab.shape) & fg


def images(slug, n=None):
    meta = json.loads((LIVE / slug / "meta.json").read_text())
    ids = meta["image_ids"]
    paths = [LIVE / slug / "thumbs" / f"{i}.webp" for i in ids]
    paths = [p for p in paths if p.is_file()]
    if n:
        step = max(1, len(paths) // n)
        paths = paths[::step][:n]
    return meta["name"], paths


def load(p):
    return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255


def cmd_speed():
    """Per-image latency at 1, 4 and all threads, on real 600px thumbnails."""
    paths = [p for s in CHARS for p in images(s, 3)[1]][:40]
    arrs = [load(p) for p in paths]
    print(
        f"{len(arrs)} thumbnails, median size {sorted(a.shape[:2] for a in arrs)[len(arrs) // 2]}"
    )
    for threads in (1, 4, 0):
        det, par = session("face_n", threads), session("face_parse", threads)
        sf = session("segformer", threads)
        for a in arrs[:3]:  # warm-up
            parse_faces(par, a, detect_faces(det, a))
            parse_whole(par, a)
            segformer(sf, a)
        t = {
            "detect": 0.0,
            "parse_crops": 0.0,
            "parse_whole": 0.0,
            "segformer": 0.0,
            "palette": 0.0,
        }
        nfaces = 0
        for a in arrs:
            t0 = time.perf_counter()
            boxes = detect_faces(det, a)
            t1 = time.perf_counter()
            lab = parse_faces(par, a, boxes)
            t2 = time.perf_counter()
            parse_whole(par, a)
            t3 = time.perf_counter()
            segformer(sf, a)
            t4 = time.perf_counter()
            skin_from_face(a, lab, np.ones(lab.shape, bool))
            t5 = time.perf_counter()
            t["detect"] += t1 - t0
            t["parse_crops"] += t2 - t1
            t["parse_whole"] += t3 - t2
            t["segformer"] += t4 - t3
            t["palette"] += t5 - t4
            nfaces += len(boxes)
        n = len(arrs)
        print(
            f"threads={threads or 'all'}: "
            + ", ".join(f"{k} {1000 * v / n:.0f} ms" for k, v in t.items())
            + f"  (faces/img {nfaces / n:.2f})"
        )


def cmd_mem(which):
    """Peak RSS of one model, loaded and run on 5 thumbnails, over the baseline."""
    import onnxruntime  # noqa: F401  (baseline includes the runtime itself)

    arrs = [load(p) for p in images("reze", 5)[1]]
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    threads = int(os.environ.get("T", "4"))
    if which == "isnetis":
        os.environ["ACCENT_LAB_ORT_THREADS"] = str(threads)
        from scripts.accent_lab import seg

        seg.CACHE = HERE / "nocache"  # force a real run
        for p in images("reze", 5)[1]:
            seg.mask_for(Image.open(p))
    else:
        s = session(which, threads)
        for a in arrs:
            if which == "face_n":
                detect_faces(s, a)
            elif which == "face_parse":
                parse_whole(s, a)
            else:
                segformer(s, a)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(
        f"{which} threads={threads}: baseline {base / 1024:.0f} MB, peak {peak / 1024:.0f} MB, model adds {(peak - base) / 1024:.0f} MB"
    )


def overlay(arr, lab, colours, fg=None):
    out = arr.copy() * 0.35 + 0.65 * arr.mean(2, keepdims=True) * 0.6
    if fg is not None:
        out[~fg] *= 0.35
    for k, c in colours.items():
        m = lab == k
        out[m] = 0.35 * arr[m] + 0.65 * np.array(c, np.float32) / 255
    return out


def cmd_sheet():
    from scripts.accent_lab import seg

    det, par, sf = session("face_n"), session("face_parse"), session("segformer")
    rows, stats = [], []
    W = 190
    for slug in CHARS:
        name, paths = images(slug, 3)
        for p in paths:
            a = load(p)
            fg = seg.mask_for(Image.open(p)) > 0.5
            boxes = detect_faces(det, a)
            lab_c = parse_faces(par, a, boxes)
            lab_w = parse_whole(par, a)
            lab_s = segformer(sf, a)
            pal = skin_from_face(a, lab_c, fg)
            tiles = [
                a,
                np.where(fg[..., None], a, 1.0),
                overlay(a, lab_c, COL, fg),
                overlay(a, lab_w, COL, fg),
                overlay(a, lab_s, SF_COL, fg),
            ]
            pv = a.copy() * 0.3
            if pal is not None:
                pv[pal] = 0.35 * a[pal] + 0.65 * np.array([250, 230, 30], np.float32) / 255
            tiles.append(pv)
            ims = []
            for t in tiles:
                im = Image.fromarray((np.clip(t, 0, 1) * 255).astype(np.uint8))
                im.thumbnail((W, W * 1.5))
                ims.append(im)
            rows.append((name, ims))
            n = fg.sum() or 1
            stats.append(
                {
                    "char": name,
                    "img": p.name,
                    "faces": len(boxes),
                    "crop_skin": float(((lab_c == FACE) | (lab_c == SKIN))[fg].sum() / n),
                    "whole_skin": float(((lab_w == FACE) | (lab_w == SKIN))[fg].sum() / n),
                    "segformer_skin": float((lab_s == 1)[fg].sum() / n),
                    "palette_skin": float(pal.sum() / n) if pal is not None else None,
                }
            )
    H = max(max(i.height for i in ims) for _, ims in rows)
    from PIL import ImageDraw

    head = 22
    sheet = Image.new("RGB", (6 * (W + 6) + 150, head + len(rows) * (H + 6)), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, lbl in enumerate(
        [
            "image",
            "cut-out",
            "face parse (crops)",
            "face parse (whole)",
            "segformer",
            "skin from face",
        ]
    ):
        d.text((150 + i * (W + 6), 5), lbl, fill=(230, 230, 230))
    for r, (name, ims) in enumerate(rows):
        y = head + r * (H + 6)
        d.text((6, y + 6), name, fill=(230, 230, 230))
        for i, im in enumerate(ims):
            sheet.paste(im, (150 + i * (W + 6), y))
    sheet.save(HERE / "sheet.png")
    (HERE / "sheet_stats.json").write_text(json.dumps(stats, indent=1))
    print(f"sheet {sheet.size}, {len(rows)} rows")


def cmd_export():
    """PyTorch weights → ONNX (the server would need only onnxruntime)."""
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))
    import network
    import torch
    import torchvision

    # avoid downloading ImageNet weights: the state dict overwrites them anyway
    network.MobileNet_V2_Weights = type("W", (), {"IMAGENET1K_V1": None})
    orig = torchvision.models.mobilenet_v2
    torchvision.models.mobilenet_v2 = lambda weights=None: orig(weights=None)
    m = network.UNet()
    m.load_state_dict(torch.load("UNet.pth", map_location="cpu"))
    m.eval()
    print("unet params", sum(p.numel() for p in m.parameters()))
    torch.onnx.export(
        m,
        torch.rand(1, 3, 512, 512),
        "face_parse.onnx",
        input_names=["x"],
        output_names=["y"],
        opset_version=17,
        dynamo=False,
    )
    from transformers import SegformerForSemanticSegmentation

    s = SegformerForSemanticSegmentation.from_pretrained("segformer").eval()
    print("segformer params", sum(p.numel() for p in s.parameters()))

    class W(torch.nn.Module):
        def __init__(s2, s):
            super().__init__()
            s2.s = s

        def forward(s2, x):
            return s2.s(pixel_values=x).logits

    torch.onnx.export(
        W(s),
        torch.rand(1, 3, 512, 512),
        "segformer.onnx",
        input_names=["x"],
        output_names=["y"],
        opset_version=17,
        dynamo=False,
    )


if __name__ == "__main__":
    {"speed": cmd_speed, "sheet": cmd_sheet, "export": cmd_export}.get(
        sys.argv[1], lambda: cmd_mem(sys.argv[2])
    )()
