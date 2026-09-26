# Accent lab

The experiment harness behind `docs/ACCENT.md` §14–22: every extractor variant
that was tried, the calibration panel they were scored on, and the tools that
produced the numbers and contact sheets in the doc. Nothing here is imported by
the app, and the shipped extractor is still `accent_extract.py`.

## Setup

The lab needs three things the app does not: `numpy`, `onnxruntime` (for
segmentation), and optionally `materialyoucolor` (only for the MCU variant).
Pass them to `uv run --with` instead of adding them to the project.

```sh
# The segmentation model, 176 MB, into .data/ (gitignored)
uv run python -m scripts.accent_lab.seg --download

# Live characters, pulled read-only from the public API and image CDN
uv run python -m scripts.accent_lab.fetch_live "Lynae" "Reze"
```

Local panel characters come from the working library in `data/`
(`imgmanager.db`, `thumbs/`, `portrait_samples/`), the same assets
`tests/test_accent_extract.py` uses. That snapshot predates the cut-over, so
anything reported against today's library should be fetched live. It also
has main images for only the 13 panel characters, so a local character is
measured with no main image -- which disables the tie-breaker and the fallback.
Some live characters have no main image either (dead ImgChest links, §18.2);
`fetch_live` then saves no `portrait.*`, and `explain` reports "portrait NO".

## Tools

```sh
# The panel, side by side. --all measures every image, not the 60-image sample.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.panel current,v8,v12 --all

# Library-wide effect: medians, dark/grey counts, hue moves, new declines.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.library current,v8 --all

# The owner's review (lab.REVIEW) instead of the calibration panel.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.panel current,v24 --all --review

# Every fetched live character, no local ones -- main images included.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.library current,v24 --all --live-only

# Why one character lands where it does: families, peaks, margin, coverage, candidates.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.explain "live:Himeno"

# A random sample by image-count band (top 10%, 10-20, 20-30, 30-50, 50-70),
# only characters whose main image loads; then the page for the owner to judge.
uv run python -m scripts.accent_lab.sample
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.showcase

# Colour-profile scan: profile many characters, show who takes V30's
# monochrome and pale-pink paths (scan list in .data/scan.json).
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.profiles

# Contact sheet from the last library run, to judge colours by eye.
uv run python -m scripts.accent_lab.sheet current,v24 --ids "live:Reze,live:Lynae"
```

Outputs, masks and fetched characters live in `.data/` (`ACCENT_LAB_DATA`
overrides it). Masks are cached by image content, so segmenting is only slow
the first time: about half a second per image on a laptop CPU.

## Files

- `lab.py` — paths, loading (local ids and `live:<Name>`), `describe`, the
  panel, and `method_current` (the shipped extractor).
- `methods.py` — every variant, `method_mcu` through `method_v32`, with a table
  at the top saying what each one tried and how it came out. `method_v32` is
  the current candidate.
- `seg.py` — skytnt/anime-seg foreground masks.
- `fetch_live.py`, `panel.py`, `library.py`, `explain.py`, `sheet.py`,
  `sample.py`, `showcase.py`, `profiles.py` — the tools above.

## Rules of thumb (from the doc)

- Judge colours on a contact sheet as well as on the panel; the panel mostly
  checks hue ranges and passed plenty of mud.
- Measure every image (`--all`). The 60-image sample hid Madoka's skin leak
  and makes Lynae's result depend on which images were picked.
- Run the whole library before believing a panel pass. Artoria (Alter) is the
  standing reminder that one tweak can turn a confident red pale.
