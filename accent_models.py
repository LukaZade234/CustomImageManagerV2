"""The two models behind the V43 accent, and what they leave behind per image.

- **The cut-out** (skytnt/anime-seg, `isnetis.onnx`, 176 MB, Apache-2.0): a mask of
  the character, so backgrounds stop voting.
- **The face parser**: an anime face detector (deepghs `face_detect_v1.4_n`, 12 MB,
  MIT) finds faces, and a UNet (siyeong0/Anime-Face-Segmentation, MIT; converted to
  ONNX once and bundled at `models/face_parse.onnx`, 6 MB) labels hair, face, eyes and
  clothes on each face crop -- which is how the accent knows the character's hair.

Both run through onnxruntime on the CPU. They are the expensive part of the accent
(about 1.9 GB of memory and a second or more per image on the server), so each image
is processed once: `prepare` returns an `ImageData` -- the mask and labels at the
200px measurement size and each face's hair colour -- which is stored with the image
row and is everything `accent_v43.decide` needs besides the pixels themselves.

The code mirrors the lab's (`scripts/accent_lab/seg.py`, `faceparse.py`) step for
step, including its rounding, so the stored data is what the owner reviewed.
The upstream models are fetched at pinned revisions and checked against their
sha256 (`ensure_models`); nothing is downloaded at import.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

import logs

log = logs.get(__name__)

# The version of what `prepare` produces. Bump it when the models or the way their
# output is reduced change, and stored data from the old version is recomputed.
DATA_VERSION = "m1"

BUNDLED = Path(__file__).resolve().parent / "models"

# name -> (url, sha256, bytes)
DOWNLOADS = {
    "isnetis.onnx": (
        "https://huggingface.co/skytnt/anime-seg/resolve/"
        "493cb60893f47441b26ec4fb9a306bce9e342982/isnetis.onnx",
        "f15622d853e8260172812b657053460e20806f04b9e05147d49af7bed31a6e99",
        176069933,
    ),
    "face_detect.onnx": (
        "https://huggingface.co/deepghs/anime_face_detection/resolve/"
        "784dc4c0bb692351ddcdbe6131a050b17d3025d5/face_detect_v1.4_n/model.onnx",
        "fd860b650a4377046842c3cd80d01b0b408bdfbdb4acee5759630f82c6ef04a9",
        12102558,
    ),
}
FACE_PARSER = (
    "face_parse.onnx",
    "25720e1356295770bc53b5333fcedcb6b64f465684bc329f6b41c2578c60ce96",
)

CUTOUT_SIZE = 1024  # the cut-out model's input
MEASURE_SIDE = 200  # accent_extract.SAMPLE_MAX_SIDE: the measurement copy
FG_THRESHOLD = 0.5
DETECT_THRESHOLD = 0.278  # the face detector card's F1-optimal threshold
CROP_GROW = 2.2  # crop side = face box side x this, so hair and neck are in frame
HAIR = 1  # the parser's hair channel
MIN_HAIR_PX = 150  # a face needs this much hair to say what colour it is


def model_dir() -> Path:
    return Path(os.environ.get("ACCENT_MODEL_DIR", "data/models"))


def threads() -> int:
    return max(1, int(os.environ.get("ACCENT_THREADS", "2")))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_models() -> None:
    """Download any missing upstream model, verified; check the bundled parser."""
    import requests

    directory = model_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, digest, size) in DOWNLOADS.items():
        path = directory / name
        if path.is_file() and path.stat().st_size == size:
            continue
        part = path.with_suffix(".part")
        log.info("accent.model_download", model=name, bytes=size)
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if _sha256(part) != digest:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{name}: checksum mismatch, download discarded")
        os.replace(part, path)
    parser = BUNDLED / FACE_PARSER[0]
    if _sha256(parser) != FACE_PARSER[1]:
        raise RuntimeError(f"{parser}: checksum mismatch")


class Models:
    """Lazily loaded onnxruntime sessions; `unload()` gives the memory back."""

    def __init__(self) -> None:
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def _session(self, name: str):
        with self._lock:
            if name not in self._sessions:
                import onnxruntime as ort

                path = BUNDLED / name if name == FACE_PARSER[0] else model_dir() / name
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = threads()
                opts.inter_op_num_threads = 1
                self._sessions[name] = ort.InferenceSession(
                    str(path), opts, providers=["CPUExecutionProvider"]
                )
            return self._sessions[name]

    def unload(self) -> None:
        with self._lock:
            self._sessions.clear()

    @property
    def loaded(self) -> bool:
        return bool(self._sessions)

    # ---- the cut-out ----------------------------------------------------------------

    def cutout(self, full: Image.Image) -> np.ndarray:
        """Foreground probability as uint8 (h, w), the size of `full`."""
        rgb = full.convert("RGB")
        w, h = rgb.size
        scale = CUTOUT_SIZE / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        arr = np.asarray(rgb.resize((nw, nh), Image.BILINEAR), dtype=np.float32) / 255.0
        canvas = np.zeros((CUTOUT_SIZE, CUTOUT_SIZE, 3), dtype=np.float32)
        ph, pw = (CUTOUT_SIZE - nh) // 2, (CUTOUT_SIZE - nw) // 2
        canvas[ph : ph + nh, pw : pw + nw] = arr
        out = self._session("isnetis.onnx").run(None, {"img": canvas.transpose(2, 0, 1)[None]})
        crop = (out[0][0, 0][ph : ph + nh, pw : pw + nw] * 255).astype(np.uint8)
        return np.asarray(Image.fromarray(crop).resize((w, h), Image.BILINEAR), dtype=np.uint8)

    # ---- the face parser ------------------------------------------------------------

    def faces(self, arr: np.ndarray) -> list[tuple]:
        """Face boxes (x0, y0, x1, y1, conf) in pixel coordinates, best first."""
        c, s, py, px = _letterbox(arr, 640, 0.5)
        out = self._session("face_detect.onnx").run(None, {"images": c.transpose(2, 0, 1)[None]})
        out = out[0][0]
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

    def parse(self, full: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """(labels, face index) the size of `full`: 1-based faces, best first; 0 = none."""
        arr = np.asarray(full.convert("RGB"))
        h, w = arr.shape[:2]
        lab = np.zeros((h, w), np.uint8)
        fid = np.zeros((h, w), np.uint8)
        for k, (x0, y0, x1, y1, _) in enumerate(self.faces(arr), start=1):
            side = max(x1 - x0, y1 - y0) * CROP_GROW
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.1
            X0, Y0 = round(cx - side / 2), round(cy - side / 2)
            X1, Y1 = X0 + round(side), Y0 + round(side)
            crop = np.full((Y1 - Y0, X1 - X0, 3), 255, np.uint8)
            sx0, sy0, sx1, sy1 = max(0, X0), max(0, Y0), min(w, X1), min(h, Y1)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            crop[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0] = arr[sy0:sy1, sx0:sx1]
            inp = (
                np.asarray(Image.fromarray(crop).resize((512, 512), Image.BILINEAR), np.float32)
                / 255
            )
            p = self._session(FACE_PARSER[0]).run(None, {"x": inp.transpose(2, 0, 1)[None]})[0][0]
            p = np.asarray(
                Image.fromarray(p.argmax(0).astype(np.uint8)).resize(
                    crop.shape[1::-1], Image.NEAREST
                )
            )
            region = p[sy0 - Y0 : sy1 - Y0, sx0 - X0 : sx1 - X0]
            cur = lab[sy0:sy1, sx0:sx1]
            cur[region > 0] = region[region > 0]
            fid[sy0:sy1, sx0:sx1][region > 0] = k
        return lab, fid


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


# ---- per-image data ---------------------------------------------------------------


@dataclass
class ImageData:
    """What the models leave behind for one image, at the 200px measurement size."""

    mask: np.ndarray  # (h, w) bool: the character
    labels: np.ndarray  # (h, w) uint8: the face parser's label, 0 outside faces
    faces: np.ndarray  # (h, w) uint8: which face (1-based) each labelled pixel came from
    face_hair: dict[int, list[float]] = field(default_factory=dict)  # face -> hair Oklab
    n_faces: int = 0
    version: str = DATA_VERSION

    @property
    def size(self) -> tuple[int, int]:
        return self.mask.shape[1], self.mask.shape[0]

    def to_blob(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(
            buf,
            mask=np.packbits(self.mask),
            shape=np.array(self.mask.shape),
            labels=self.labels,
            faces=self.faces,
        )
        return buf.getvalue()

    def hair_json(self) -> str:
        return json.dumps({str(k): [float(x) for x in v] for k, v in self.face_hair.items()})

    @classmethod
    def from_row(cls, blob: bytes, hair_json: str, n_faces: int, version: str) -> ImageData:
        z = np.load(io.BytesIO(blob))
        shape = tuple(int(x) for x in z["shape"])
        mask = np.unpackbits(z["mask"])[: shape[0] * shape[1]].reshape(shape).astype(bool)
        hair = {int(k): v for k, v in json.loads(hair_json).items()}
        return cls(mask, z["labels"], z["faces"], hair, n_faces, version)

    def prepared(self, rgb: np.ndarray):
        """The accent_v43 input, given the measurement copy's pixels."""
        import accent_v43

        if rgb.shape[:2] != self.mask.shape:
            raise ValueError(
                f"measurement copy {rgb.shape[:2]} does not match data {self.mask.shape}"
            )
        return accent_v43.Prepared(
            rgb=rgb,
            mask=self.mask,
            labels=self.labels,
            faces=self.faces,
            face_hair={k: np.array(v) for k, v in sorted(self.face_hair.items())},
            n_faces=self.n_faces,
        )


def composite(img: Image.Image) -> Image.Image:
    """RGB with any transparency resolved against white, full size."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img)
    return img.convert("RGB")


def measurement_copy(full: Image.Image) -> Image.Image:
    """The 200px copy the colours are measured on (accent_extract._prepare)."""
    small = full.copy()
    small.thumbnail((MEASURE_SIDE, MEASURE_SIDE), Image.LANCZOS)
    return small


def reduce(full: Image.Image, mask: np.ndarray, labels: np.ndarray, faces: np.ndarray) -> ImageData:
    """Model output at full size -> the data kept, at measurement size.

    `mask` is the cut-out's uint8 output (or, from the lab's older cache, the same as
    float32 in 0..1). It is resized exactly as the lab resized it (through float32
    and back to uint8), so a character on the threshold lands on the same side.
    """
    size = measurement_copy(full).size
    full_m = mask if mask.dtype != np.uint8 else mask.astype(np.float32) / 255.0
    m = full_m
    if m.shape[::-1] != size:
        m = (
            np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(size, Image.BILINEAR))
            / 255.0
        )
    shape = (size[1], size[0])
    lab200, fid200 = labels, faces
    if labels.shape != shape:
        lab200 = np.asarray(Image.fromarray(labels).resize(size, Image.NEAREST))
        fid200 = np.asarray(Image.fromarray(faces).resize(size, Image.NEAREST))

    # Each face's hair colour, read at full size.
    import accent_v43

    keep = full_m >= FG_THRESHOLD
    rgb = np.asarray(full, dtype=np.float64) / 255.0
    hair: dict[int, list[float]] = {}
    for k in np.unique(faces[faces > 0]):
        sel = (labels == HAIR) & (faces == k) & keep
        if sel.sum() >= MIN_HAIR_PX:
            hair[int(k)] = [float(x) for x in np.median(accent_v43.oklab(rgb[sel]), axis=0)]
    return ImageData(
        mask=m >= FG_THRESHOLD,
        labels=np.ascontiguousarray(lab200, dtype=np.uint8),
        faces=np.ascontiguousarray(fid200, dtype=np.uint8),
        face_hair=hair,
        n_faces=int(faces.max()) if faces.size else 0,
    )


def prepare(models: Models, img: Image.Image) -> ImageData:
    """Run both models on one image (the 600px thumbnail, or the main image)."""
    full = composite(img)
    return reduce(full, models.cutout(full), *models.parse(full))
