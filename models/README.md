# Bundled model

`face_parse.onnx` (6.2 MB) is the face parser the V43 accent uses
(`accent_models.py`): a UNet on MobileNetV2 that labels an anime face crop as
background, hair, eye, mouth, face, skin or clothes.

- **Source:** [siyeong0/Anime-Face-Segmentation](https://github.com/siyeong0/Anime-Face-Segmentation),
  `model/UNet.pth`, MIT licence.
- **Converted** to ONNX (opset 17) with `python -m scripts.accent_lab.skinbench export`
  (needs torch; see that module's docstring). Bundled because there is no upstream
  ONNX to download, and the server has no torch to convert it.
- **sha256** `25720e1356295770bc53b5333fcedcb6b64f465684bc329f6b41c2578c60ce96`,
  checked by `accent_models.ensure_models()`.

The two larger models (the cut-out, 176 MB, and the face detector, 12 MB) are not
bundled: the worker downloads them at pinned revisions and checks their sha256
(`accent_models.DOWNLOADS`).
