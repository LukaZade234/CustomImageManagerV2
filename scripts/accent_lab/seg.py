"""Foreground masks from skytnt/anime-seg (`isnetis.onnx`), cached per image.

The model (176 MB, Apache-2.0) is not committed; `python -m
scripts.accent_lab.seg --download` fetches it into `.data/`. Inference follows
the model's reference code: fit the longest side to 1024, pad to a square,
float RGB in [0, 1], CHW; the output is a 0..1 foreground probability.
Roughly half a second per image on a laptop CPU.
"""

from __future__ import annotations

import hashlib
import os
import sys

import numpy as np
from PIL import Image

from .lab import DATA

MODEL = DATA / "isnetis.onnx"
MODEL_URL = "https://huggingface.co/skytnt/anime-seg/resolve/main/isnetis.onnx"
CACHE = DATA / "masks"
SIZE = 1024
_session = None


def _sess():
    global _session
    if _session is None:
        import onnxruntime as ort

        if not MODEL.is_file():
            sys.exit(f"segmentation model missing: run `python -m {__name__} --download`")
        opts = ort.SessionOptions()
        threads = int(os.environ.get("ACCENT_LAB_ORT_THREADS", "0"))
        if threads:
            opts.intra_op_num_threads = threads
        _session = ort.InferenceSession(str(MODEL), opts, providers=["CPUExecutionProvider"])
    return _session


def mask_for(img: Image.Image) -> np.ndarray:
    """Foreground probability shaped (H, W) like `img`, float32 in 0..1."""
    rgb = img.convert("RGB")
    key = hashlib.sha1(rgb.tobytes() + repr(rgb.size).encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.npy"
    if cached.is_file():
        m = np.load(cached)
        return m.astype(np.float32) / 255.0 if m.dtype == np.uint8 else m
    w, h = rgb.size
    scale = SIZE / max(w, h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    arr = np.asarray(rgb.resize((nw, nh), Image.BILINEAR), dtype=np.float32) / 255.0
    canvas = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    ph, pw = (SIZE - nh) // 2, (SIZE - nw) // 2
    canvas[ph : ph + nh, pw : pw + nw] = arr
    out = _sess().run(None, {"img": canvas.transpose(2, 0, 1)[None]})[0][0, 0]
    crop = (out[ph : ph + nh, pw : pw + nw] * 255).astype(np.uint8)
    mask8 = np.asarray(Image.fromarray(crop).resize((w, h), Image.BILINEAR), dtype=np.uint8)
    np.save(cached, mask8)  # 8-bit: a quarter of the float cache, same result after /255
    return mask8.astype(np.float32) / 255.0


if __name__ == "__main__":
    if "--download" in sys.argv:
        import requests

        DATA.mkdir(parents=True, exist_ok=True)
        with requests.get(MODEL_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(MODEL, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        print(f"saved {MODEL} ({MODEL.stat().st_size // 1_000_000} MB)")
