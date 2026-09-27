"""Face parsing for the skin trial (ACCENT.md §31): which pixels are face skin, and which hair.

An anime face detector (deepghs face_detect_v1.4_n) finds faces; a face parser
(siyeong0/Anime-Face-Segmentation, a UNet on 512px face crops) labels each crop.
Both run through onnxruntime; `skinbench.py` has the download and conversion.
Labels are cached per image content in `.data/faceparse/` (compressed; mostly
zeros, so a few KB each).
"""

from __future__ import annotations

import hashlib
import os

import numpy as np
from PIL import Image

from .lab import DATA

MODELS = DATA / "skin"
CACHE = DATA / "faceparse"

# channel order of the parser's output (util.PALETTE in the source repo)
BG, HAIR, EYE, MOUTH, FACE, SKIN, CLOTHES = range(7)
DETECT_THRESHOLD = 0.278  # the model card's F1-optimal threshold
CROP_GROW = 2.2  # crop side = face box side × this (hair and neck in frame)

_sessions: dict = {}


def _sess(name):
    if name not in _sessions:
        import onnxruntime as ort

        o = ort.SessionOptions()
        threads = int(os.environ.get("ACCENT_LAB_ORT_THREADS", "0")) or 4
        o.intra_op_num_threads = min(threads, 4)  # small models are slower on many threads
        o.inter_op_num_threads = 1
        _sessions[name] = ort.InferenceSession(
            str(MODELS / f"{name}.onnx"), o, providers=["CPUExecutionProvider"]
        )
    return _sessions[name]


def _letterbox(arr, size, fill):
    h, w = arr.shape[:2]
    s = size / max(h, w)
    nh, nw = max(1, round(h * s)), max(1, round(w * s))
    img = np.asarray(Image.fromarray(arr).resize((nw, nh), Image.BILINEAR), np.float32) / 255
    c = np.full((size, size, 3), fill, np.float32)
    py, px = (size - nh) // 2, (size - nw) // 2
    c[py : py + nh, px : px + nw] = img
    return c, s, py, px


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (union + 1e-9)


def faces(arr):
    """Face boxes (x0, y0, x1, y1, conf) in pixel coordinates, best first."""
    c, s, py, px = _letterbox(arr, 640, 0.5)
    out = _sess("face_n").run(None, {"images": c.transpose(2, 0, 1)[None]})[0][0]
    if out.shape[0] < out.shape[1]:
        out = out.T
    out = out[out[:, 4] > DETECT_THRESHOLD]
    boxes: list = []
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


def _parse(arr, boxes):
    h, w = arr.shape[:2]
    lab = np.zeros((h, w), np.uint8)
    for x0, y0, x1, y1, _ in boxes:
        side = max(x1 - x0, y1 - y0) * CROP_GROW
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.1
        X0, Y0 = round(cx - side / 2), round(cy - side / 2)
        X1, Y1 = X0 + round(side), Y0 + round(side)
        crop = np.full((Y1 - Y0, X1 - X0, 3), 255, np.uint8)
        sx0, sy0, sx1, sy1 = max(0, X0), max(0, Y0), min(w, X1), min(h, Y1)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        crop[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0] = arr[sy0:sy1, sx0:sx1]
        inp = np.asarray(Image.fromarray(crop).resize((512, 512), Image.BILINEAR), np.float32) / 255
        p = _sess("face_parse").run(None, {"x": inp.transpose(2, 0, 1)[None]})[0][0]
        p = np.asarray(
            Image.fromarray(p.argmax(0).astype(np.uint8)).resize(crop.shape[1::-1], Image.NEAREST)
        )
        region = p[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0]
        cur = lab[sy0:sy1, sx0:sx1]
        cur[region > 0] = region[region > 0]
    return lab


def labels_for(img: Image.Image) -> np.ndarray:
    """Per-pixel parser label shaped like `img` (0 outside every face crop)."""
    rgb = img.convert("RGB")
    key = hashlib.sha1(rgb.tobytes() + repr(rgb.size).encode()).hexdigest()[:16]
    cached = CACHE / f"{key}.npz"
    if cached.is_file():
        return np.load(cached)["l"]
    arr = np.asarray(rgb)
    lab = _parse(arr, faces(arr))
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(f".{os.getpid()}.tmp.npz")
    np.savez_compressed(tmp, l=lab)
    os.replace(tmp, cached)
    return lab
