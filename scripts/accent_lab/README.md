# Accent lab

The experiment harness behind `docs/ACCENT.md` §14–43: every extractor variant
that was tried, the calibration panel they were scored on, and the tools that
produced the numbers and contact sheets in the doc. Nothing here is imported by
the app, and the shipped extractor is still `accent_extract.py`.

**Where it ended:** the candidate is V43 (`methods.candidate`), 84 of 96 review
checks. `docs/ACCENT.md` §29 describes its behaviour step by step, what is still
open, and the checklist for porting it into the app.

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

# The full check: every character with 4+ images, in parallel, then two review pages.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.fullcheck compute
uv run python -m scripts.accent_lab.fullcheck render
# ... or a new version beside an earlier run:
#   fullcheck --method v36 --out full_v36 compute
#   fullcheck --method v36 --out full_v36 --compare full --compare-label V33 render

# Score versions against every review verdict in lab.py, and explain a character.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.checks v37,v43
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.trace v43 "Reze|Kyouka Jirou"

# Characters whose accent visibly changed between two full runs (Oklab >= 0.08).
uv run python -m scripts.accent_lab.changes full_v40 full_v43

# Skin/body-part models (ACCENT.md §30): speed, memory, and a contact sheet of what
# each marks. Model download and ONNX conversion are in the module docstring.
uv run --no-project --with numpy --with onnxruntime --with pillow --with requests \
    python -m scripts.accent_lab.skinbench speed

# Only the characters that visibly changed between two runs, one page (--also adds
# named characters regardless):
#   fullcheck --method v43 --out full_v43 --compare full_v40 --compare-label V40 \
#       --min-change 0.08 --changed-only --also "Jotaro Kujo" render
# (V38 onward use face-parser labels from faceparse.py; models as in skinbench.py.)

# Why a character's distinct hair colour loses: what V43's rules do to the parsed hair.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.hairwhy "Shouko Nishimiya"

# Background colours: what the cut-out removes, and whether it is on the character.
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.bgprobe "Gon Freecss|Lynae"

# The WD tagger (§41-42): colour tags per gallery, then the tie-breaker simulation.
uv run --no-project --with numpy --with onnxruntime --with pillow \
    python scripts/accent_lab/tagprobe.py "Gon Freecss|Audrey Hall"
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.tagsim scan
uv run --with numpy --with onnxruntime python -m scripts.accent_lab.tagsim simulate

# Contact sheet from the last library run, to judge colours by eye.
uv run python -m scripts.accent_lab.sheet current,v24 --ids "live:Reze,live:Lynae"
```

Outputs, masks and fetched characters live in `.data/` (`ACCENT_LAB_DATA`
overrides it). Masks are cached by image content, so segmenting is only slow
the first time: about half a second per image on a laptop CPU.

## Files

- `lab.py` — paths, loading (local ids and `live:<Name>`), `describe`, the
  panel, and `method_current` (the shipped extractor).
- `methods.py` — every variant, `method_mcu` through `method_v43`, with a table
  at the top saying what each one tried and how it came out. `candidate` (= `v43`)
  is where the work stopped.
- `seg.py` — skytnt/anime-seg foreground masks.
- `faceparse.py` — anime face detector + face parser labels (hair, face, skin …)
  with the face each pixel belongs to, cached per image.
- `skinbench.py` — size, speed and memory of the skin/body-part models, and their
  ONNX conversion.
- `fetch_live.py`, `panel.py`, `library.py`, `explain.py`, `sheet.py`,
  `sample.py`, `showcase.py`, `profiles.py`, `fullcheck.py`, `checks.py`, `trace.py`,
  `changes.py`, `hairwhy.py`, `bgprobe.py`, `tagprobe.py`, `tagsim.py` — the tools
  above. See `docs/ACCENT.md` §29 for where things stand.

## Rules of thumb (from the doc)

- Judge colours on a contact sheet as well as on the panel; the panel mostly
  checks hue ranges and passed plenty of mud.
- Measure every image (`--all`). The 60-image sample hid Madoka's skin leak
  and makes Lynae's result depend on which images were picked.
- Run the whole library before believing a panel pass. Artoria (Alter) is the
  standing reminder that one tweak can turn a confident red pale.
