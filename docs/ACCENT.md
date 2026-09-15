# The character accent colour

A retrospective of the accent-colour feature: every idea proposed, every version
of the logic tried, what worked, what did not, and why — so that revisiting it
does not repeat the same mistakes.

This is a working document, not a design spec. The design rationale that still
holds lives in `DECISIONS.md` and `DESIGN.md`; this one is the full history and
the open questions, including the dead ends.

---

## TL;DR

- **Shipped and merged-ready:**
  - Portrait weighting by gallery size (`accent_extract._portrait_share`).
  - A 10+-image gallery ignores the portrait entirely.
  - A staff-only **manual accent override** with a click-a-pixel picker.
- **Tried and deliberately reverted:** the "per-image prominent-colour vote" and
  the "median of per-image representatives". Both regressed the calibration panel
  or made colour worse. See §6.
- **The core unsolved problem:** the algorithm answers *"dominant chromatic
  colour"*; people want *"the character's signature colour"*. These diverge when
  a character is blonde/warm-lit but themed in another colour (Audrey Hall), or
  when a background out-areas the subject. No colour statistic fixes this — it is
  semantic. Manual override is the safety valve; foreground segmentation is the
  promising algorithmic route.
- **Audrey Hall cannot be fixed by statistics, and this was verified**: her art
  is gold-dominant by area (55% gold/orange vs 32% green), green wins only 9 of
  28 images. "Audrey is green" is lore, not pixels.

---

## 1. What the accent is

A character page replaces the site's teal accent with a colour derived from that
character's own art. The server measures one **seed** (a hex colour) per
character, stores it on the `characters` row, and the frontend turns it into the
eight contrast-fitted CSS tokens (`frontend/src/utils/accentFromImage.js`,
`useCharacterTheme`, `useApplyCharacterTheme`).

- Migration `007_character_accent.sql` added the accent columns:
  `accent_seed`, `accent_hue`, `accent_source`, and a fingerprint
  (`accent_gallery_count`, `accent_gallery_latest`, `accent_portrait_url`,
  `accent_partial`, `accent_updated_at`).
- `NULL` seed means "declined" — genuinely two-coloured or greyscale art keeps
  the system accent. The fingerprint is still written, so a decided "no" is not
  re-measured forever.
- The seed is recomputed when a fingerprint of its inputs (gallery size, newest
  add, portrait URL) changes, or on the first visit after the batch backfill.
- Migration `013_character_accent_override.sql` added the override (see §9).

Where it is computed: `accent_extract.py`. Where it is measured on demand:
`routes/customs.py` (`/api/custom-image/<name>` calls `ensure_accent`). Where it
is backfilled: `scripts/recompute_accents.py`.

---

## 2. How the current algorithm works (the baseline)

This is the shipped logic as of this document. Read it before touching the code.

**Per image (`measure_image`)** — every pixel of a downsampled 200px image is
classified into two hue histograms on a 72-bin wheel (5°/bin):

- Reject deep shadow (`val < 0.15`), blown-out white (`val ≥ 0.95 && sat ≤ 0.15`),
  greyscale (`d ≈ 0`), and skin (`hue 12–48`, `0.12 ≤ sat ≤ 0.55`, `val ≥ 0.6`).
- **Saturated** (`sat ≥ 0.22`): weight `sat^1.6 × _light_pref(val)`.
- **Pale** (`sat ≥ 0.05`, `val ≥ 0.5`): weight `sat × 0.5`.
- Each class is then **normalised to sum to 1 per image**, so resolution and crop
  cannot bias the vote.

**Pooling (`_pool_histogram`) — this is the "mass" method.** Each image's
normalised histogram is added, weighted by the image's weight. Then one peak is
found.

**The decision (`_decide_from`)**:
- Find the dominant hue in the saturated pool (`_dominant_hue`): smooth the
  histogram (Gaussian σ=1.6 bins, radius 5), take the max, require
  `confidence ≥ MIN_CONFIDENCE` (0.05), and require the peak to beat any rival
  >60° away by `MIN_MARGIN` (1.25×) — otherwise two-colour art declines.
- Do the same for the pale pool.
- Decide whether the pale class *is* the identity, under two narrow rules
  (`PALE_CONF_MULT`, `PALE_AGREEMENT`, `PALE_REP_MIN_SHARE`,
  `PALE_REP_MAX_SAT_CONF`). This is load-bearing for Lucy (pale blue-white hair
  beats scattered neon backgrounds).
- Halve the representative from the winning class's pooled band (±22.5°) using a
  0.6 saturation / 0.55 value percentile (`_grid_percentile`), require
  `chroma ≥ MIN_CHROMA`, and return the seed.

**Portrait vs gallery (`decide`)** — the newest addition:
- Compute the gallery result, the portrait result, and a combined result with the
  portrait weighted by `_portrait_share(len(gallery))`.
- Whichever side can decide alone owns the answer if the other declines.
- The portrait's weight falls with gallery size (§4.2).

**Constants worth remembering** (all in `accent_extract.py`):
`HUE_BINS=72`, `SAMPLE_MAX_SIDE=200`, `SKIN_HUE=(12,48)`,
`SATURATED_SAT_MIN=0.22`, `PALE_SAT_MIN=0.05`, `PALE_VAL_MIN=0.5`,
`PALE_VOTE_WEIGHT=0.5`, `MIN_CONFIDENCE=0.05`, `MIN_CHROMA=0.025`,
`RIVAL_SEPARATION=60`, `MIN_MARGIN=1.25`, `POOL_SAMPLE_CAP=60`,
`PALE_CONF_MULT=2.0`, `PALE_AGREEMENT=60`, `PALE_REP_MIN_SHARE=0.4`,
`PALE_REP_MAX_SAT_CONF=0.07`, `SAT_PERCENTILE=0.6`, `VAL_PERCENTILE=0.55`,
`BAND_SPAN=22.5`, `PORTRAIT_SHARE_POINTS=((0,1.0),(1,0.70),(2,0.70),(5,0.20),(10,0.0))`.

---

## 3. The calibration harness

`tests/test_accent_extract.py` has two halves:

- **Synthetic tests** (`TestMeasurement`, `TestDecision`, `TestPortraitWeighting`,
  `TestFingerprint`) that pin the rules on generated images.
- **The calibration panel** (`PANEL`), which runs the real extractor against the
  working library in `data/` and asserts known-good answers. It skips itself when
  those assets are absent (CI, fresh clone). Current expectations:

| id | character | expectation |
|---|---|---|
| 1001 | Audrey Hall | a seed exists, `source == "gallery"` |
| 445 | Tsumugi Kotobuki | a seed exists |
| 92 | Lucy (Cyberpunk) | hue 240–290, lightness ≥ 0.7, chroma ≤ 0.06 (pale blue) |
| 2 | Hatsune Miku | hue 170–240 (teal) |
| 592 | Reimu Hakurei | hue within 40° of 10 (red) |
| 13 | 2B | no seed, or chroma < 0.06 (greyscale) |
| 59 | Reze | hue 270–320 (violet) |
| 6 | Saber | hue 240–290, lightness < 0.6 (deep blue) |
| 156 | Madoka Kaname | hue within 30° of 350 (pink) |

**Any change to the extractor must be run against this panel.** It is the only
thing standing between a plausible idea and a shipped regression.

---

## 4. Timeline of the investigation

### 4.1 The trigger: Yuno Gasai was blue

Yuno Gasai showed a blue accent. Investigation:

- The gallery-wins rule meant a single custom image outvoted the portrait.
- Her one gallery image was a 500×245 ImgChest banner measuring
  `#59a2d2` (hue 239°), while her portrait measured `#9f6124` (hue 61°,
  orange-brown).
- The accent also flipped between visits: the first request (thumbnail not yet
  cached) returned the portrait seed; once `/thumbs/<id>.webp` was cached,
  `accent_partial` triggered a recompute and it settled on the gallery blue.

You proposed the fix that shipped: **the portrait's importance should scale with
gallery size**. Your numbers: 70% at 1–2 images, ~20% at 5, 0% at 10+.

### 4.2 Portrait weighting (shipped)

Interpolation through `PORTRAIT_SHARE_POINTS`. `portrait_weight = share/(1-share)
× n`, so the portrait's fraction of the vote is exactly the target share:

| gallery images (n) | portrait share | portrait weight | gallery weight |
|---|---|---|---|
| 0 | 100% | alone | 0 |
| 1 | 70% | 2.333 | 1 |
| 2 | 70% | 4.667 | 2 |
| 3 | 53.3% | 3.429 | 3 |
| 4 | 36.7% | 2.316 | 4 |
| 5 | 20% | 1.250 | 5 |
| 6 | 16% | 1.143 | 6 |
| 7 | 12% | 0.955 | 7 |
| 8 | 8% | 0.696 | 8 |
| 9 | 4% | 0.375 | 9 |
| ≥10 | 0% | — | n |

Two safety rules: if blending scatters the pool into a two-colour tie, fall back
to whichever side held more of the vote; and a side that can decide alone owns
the answer when the other declines.

Measured result (see §10): Yuno fixed to `#9f6124` (`source: portrait`).

### 4.3 The 10+ "agreement" blend and Artoria Pendragon (Alter)

The first cut let the portrait *join* a 10+ gallery when its hue agreed, on the
theory that agreement could only reinforce. Measurement disproved it: at 25
images **Artoria Pendragon (Alter)** went from `#6c0e1f` (dark red, L 0.35) to
`#c6a3a6` (pale pink, L 0.75) on a hue move of only 6°. The tiny weight flipped
the pale-vs-saturated branch — a different colour, not a firmer one.

**Fix shipped:** at 10+ the portrait does not join at all. `PORTRAIT_AGREE_DEGREES`
was removed. This was verified by a full pass over the live library (§10).

### 4.4 Audrey Hall: the harder problem

You reported Audrey should be green but was showing gold (`#9f8c44`, olive).

Investigation, with a low saturation floor (0.08) and broad hue families over her
28 cached thumbnails:

| family | chromatic-area share |
|---|---|
| gold/orange | 0.554 |
| green | 0.320 |
| blue | 0.076 |
| red | 0.040 |

- Green is significant, but gold is bigger, and green out-weighs gold in only
  **9 of 28** images.
- A coarse per-image vote tallied gold at ~0.78 vs green ~0.06 — gold by >10×.
- The greens are **not** invisible: green pixels have a median saturation of
  0.28. But two confounds understate green: (a) the greens span ~100° of hue
  (many shades), diluting a single peak; (b) a warm colour grade shifts green
  toward olive/yellow, which lands in the "gold" family.
- There **is** a real classifier gap: in one representative image (4166), 77% of
  the green pixels fall in the gap between the sat≥0.22 and (pale, val≥0.5)
  rules (green sat median 0.13, val median 0.27). Widening the gap was tested and
  did not flip the winner.

**Conclusion:** Audrey is genuinely gold-dominant in her art. "Green" is her
dress (lore), not the dominant colour. This is the semantic gap, not a bug.

### 4.5 The full rewrite (reverted)

You then proposed the deeper idea: **per-image, take the most prominent few
colours and compare them across images** — a colour that recurs across images is
probably the accent. I implemented this in three forms; all regressed or did not
help. Details in §6. Everything was reverted.

### 4.6 What each experiment measured

- Portrait weighting: 196 characters had a usable cached gallery; 161 changed,
  0 gained, 0 lost. 10+ images changed **0**; 1 image → 27, 2 → 11, 3–4 → 118,
  5–9 → 5. (This is the shipped change.)
- Median-of-per-image representatives: 135 of 150 local characters with a gallery
  changed shade; chroma **fell** on average by 0.008 and only 45/135 rose.
- The per-image vote: two-colour decline broke; Lucy and Reze failed the panel.

---

## 5. Every idea proposed

### 5.1 Yours

1. **Scale the portrait by gallery size** (70/20/0). — *Shipped, works.*
2. **At 10+, ignore the portrait unless its colour matches.** — *Implemented,
   then removed:* "matches" still let a tiny weight flip colour (Artoria). Now
   ignored entirely.
3. **Manual colour-pick as calibration targets** ("colourpick what I think the
   ideal accent is"). — *Partially shipped:* the manual override captures the
   picks and doubles as the label set; the automated threshold search on top is
   still open.
4. **Train an ML model** to predict the accent from your ideal choices. —
   *Assessed: not viable as an accent predictor* (too little data; would learn
   your hue preferences). *Viable as foreground segmentation* (see 5.2.1).
5. **The per-image prominent-colours vote.** — *Tried three ways, reverted* (§6).
6. **Background-beats-subject:** strip simple backgrounds? — *Your own skepticism
   is right:* complex backgrounds defeat heuristics; segmentation is the real
   route.

### 5.2 Mine

1. **Foreground/subject segmentation** (pretrained anime saliency) run before the
   colour logic — the robust fix for background-beats-subject; no labelling
   needed; acceptable as an offline batch. **Not built. Highest-value algorithmic
   direction.**
2. **Calibration protocol**: 40–80 characters spanning the failure modes
   (1–2 image galleries, 10+, pale identities, two-colour, complex backgrounds),
   each with a human-chosen target, and each tagged *dominant / subject / iconic*
   to say which mechanism is needed.
3. **A small model on engineered colour features** once a few hundred labels
   exist — marginal; benchmark against tuned rules, not a first choice.
4. **The manual override as a safety valve** — *shipped* (§9).
5. **Percentile lever for "washed out"** — raise `SAT_PERCENTILE` /
   `VAL_PERCENTILE` to pick the vivid end of the band rather than averaging
   across images. *Untested; cheap; likely the right lever for that symptom.*
6. **Distinguish dominant vs subject vs iconic** as a taxonomy, because the right
   mechanism differs by case.

---

## 6. Every version of the logic tried

### V0 — baseline (mass pooling)
Gallery wins outright; portrait is only a fallback. The state before this work.

### V1 — V0 + portrait weighting (shipped)
`_portrait_share` + combined pool. Fixes lone-image galleries (Yuno). Calibration
panel passes.

### V2 — V1 + 10+ exclusion (shipped)
At ≥10 images the portrait does not join. Fixes Artoria. Panel passes.

### V3 — full rewrite: fold classes + per-image vote + median representative (reverted)
What I built first:
- `measure_image` returns **one** normalised distribution (saturated and pale
  merged, one normalisation), retiring the class split.
- Each image votes for its **top-3 hues** (peaks separated by `RIVAL_SEPARATION`),
  rank-weighted 1.0/0.6/0.4 and scaled by each peak's share.
- The winner is the hue with the most votes; the shade is the **median** of each
  voting image's own representative.

**Failures:**
- **Lucy regressed** — her pale identity went to a mid slate (`#405379`,
  L 0.44). The pale class is load-bearing; folding lost it.
- **The vote changes the confidence scale**, which the pale/saturated thresholds
  (`PALE_REP_MAX_SAT_CONF` etc.) are calibrated to. Lucy's saturated confidence
  rose just over the 0.07 line and she flipped to saturated.
- **Audrey did not change** (gold is dominant in the data anyway).
- **Median representatives lowered chroma** on average across the library.

### V3a — drop-in vote only (reverted)
Kept the class split and the existing representatives; replaced only
`_pool_histogram` with per-image top-K rank-weighted votes.
- Broke `test_an_honest_two_colour_pool_declines`: rank weighting made one of two
  near-equal peaks win by a hair.
- Lucy and Reze still failed (confidence-scale mismatch).

### V3b — V3a + per-image two-colour abstention (reverted)
An image whose own top two peaks are within `MIN_MARGIN` abstains. Fixed the
synthetic two-colour decline, but Lucy and Reze still failed on the confidence
scale.

### V3c — vote for the hue, keep mass-based winner? (reverted)
Restored mass-based winner selection and kept only the **median-of-per-image
representative** for the shade. Panel passed.
- But across 150 local characters it changed 135 shades and **lowered** chroma by
  0.008 on average (45/135 higher). The pooled percentile is mass-weighted, so a
  dominant vivid image can pull it *up* — the median is not the crisper option it
  looked like.
- Reverted.

### V4 — manual override + click-to-sample picker (shipped, §9)
Because the semantic gap cannot be closed by statistics, a human sets the colour.

---

## 7. Why the colour logic is hard

1. **Dominant ≠ signature.** The algorithm measures the most chromatic area; the
   "identity" colour is a semantic judgement. Audrey is the archetype.
2. **Area accumulates.** Per-image normalisation caps one image, but summing mass
   across images lets a common secondary colour (a background, blonde hair under
   warm light) out-total a subject colour present in fewer images.
3. **The pale/saturated split is load-bearing.** It exists for soft identities
   (Lucy). Folding it regresses them.
4. **The confidence thresholds are scale-specific.** They were tuned on *mass*
   confidence. Any change to how the histogram is built (votes, weights) moves
   the scale and silently breaks the rules.
5. **Colour grading and shading spread a single identity across hues** (green →
   olive), and across saturations (a muted dark dress falls in the classifier
   gap).
6. **Backgrounds are complex.** No "strip the background" heuristic generalises;
   that needs segmentation.

---

## 8. Decisions and rationale

- **Keep gallery-wins, but weight the portrait by gallery size.** A gallery is a
  consensus; one or two images are not. Shipped.
- **At 10+, the portrait is ignored entirely.** Agreement-blending is not
  "reinforcement" — a tiny weight can flip the pale/saturated branch. Shipped.
- **Revert the vote and median rewrites.** They regressed the calibration panel
  or made shades worse; not shipped.
- **Do not retune thresholds blind.** The calibration panel is the contract.
- **Give humans the override.** The semantic gap is not closable by statistics,
  and every pick is a future calibration label. Shipped.
- **Manual override is staff-only and write-through** (§9).

---

## 9. The accent override / picker (shipped)

**Goal.** A moderator or the owner picks a pixel off the art and that colour
becomes the character's accent.

**Data (`migrations/013_character_accent_override.sql`):**
`accent_override` (hex, NULL = not overridden), `accent_override_by`,
`accent_override_at`.

**Precedence — write-through.** On set, both `accent_override` and `accent_seed`
are written (and `accent_source='manual'`), so every read path that already reads
`accent_seed` (the list `db.get_characters`, `db.find_character`, the saved list,
the gallery endpoint) shows it with **no query change**. `accent_extract.
ensure_accent` returns the override; `recompute_accent` returns early (so
`scripts/recompute_accents.py` never overwrites it). Clearing nulls both and the
next visit measures afresh.

**Endpoint:** `POST /api/accent-override` (`routes/characters.py`), staff-only
(403 otherwise), rate-limited with `edit_character`.
- `{name, seed}` → set from hex.
- `{name, clear: true}` → clear.
- `{name, image_id, u, v}` → sample the cached gallery thumbnail at the point.
- `{name, portrait: true, u, v}` → sample the character's portrait.

The client sends the **point, never a URL**; the server resolves the image by row
id / character name, so it can only ever sample an image already in the library.
Gallery sampling uses `thumbnails.cache_path(id)` (materialised via
`accent_extract._materialise_thumbnail` if never viewed). Portrait sampling uses
`accent_extract.fetch_portrait_bytes(main_image_url)`.

**Sampling:** `accent_extract.hex_at_point(image, u, v)` reads the pixel at
normalised coordinates (top-left origin); `open_image_bytes` loads at full
resolution (no 200px downsample) so the picked pixel is exact.

**Frontend:**
- `utils/imagePick.js` — `naturalPoint` / `pickPixel` map a click through the
  element's `object-fit` (the grid crops with `cover`, the portrait letterboxes
  with `contain`), so the sampled pixel is the one under the cursor.
- `components/AccentOverrideControl.jsx` — a quiet row (swatch,
  `Measured`/`Manual`, **Pick from image** / **Cancel pick**, **Reset to
  measured**), staff-only, pushed to the right of the header actions.
- On a click, `CharacterPage.handlePickAccent` calls the endpoint, toasts,
  invalidates the gallery + saved queries and reloads the character so the page
  re-themes. No separate confirm step.
- The gallery exposes `pick`/`onPick`; the header portrait becomes a picker
  button when `pick` is set.

**Tests:** `tests/test_accent_override.py` (set/clear, staff-only, validation,
pixel sampling, extractor respects the override, `hex_at_point`, no-downsample),
`frontend/src/utils/imagePick.test.js`,
`frontend/src/components/AccentOverrideControl.test.jsx`, and new cases in
`CharacterHeader.test.jsx` / `CustomImageGallery.test.jsx`.

**Also consider (not done):** the override is currently only reachable by staff
on a character page. There is no bulk view of overridden characters, and no way
to label a target *without* changing the display (the two are the same action).
If a calibration set is built, a separate "target" that does not override the
display may be wanted.

---

## 10. The evidence (numbers to keep)

**Portrait weighting, live library pass (196 characters with a cached gallery):**
161 changed, 0 gained, 0 lost. By gallery size: 1 → 27, 2 → 11, 3–4 → 118,
5–9 → 5, **10+ → 0**.

**Artoria Pendragon (Alter), 25 images:** `#6c0e1f` (L 0.35, C 0.126) →
`#c6a3a6` (L 0.75, C 0.041) with the agreement-blend; restored to `#6c0e1f` after
the 10+ exclusion.

**Yuno Gasai:** gallery `#59a2d2` (hue 239) vs portrait `#9f6124` (hue 61); with
portrait weighting she reads `#9f6124`, `source: portrait`. (Note: even so, her
portrait measures orange-brown, not the pink you wanted — her saturated pool is
won by the red bow and warm background; the pink hair is relatively
desaturated.)

**Audrey Hall:** gold/orange 0.554 vs green 0.320 by chromatic area; green wins
9/28 images; green pixel sat median 0.28; in image 4166, 77% of green pixels fall
in the classifier gap (sat<0.22, val<0.5; medians 0.13 / 0.27). Per-image vote:
gold ~0.78 vs green ~0.06.

**Median-of-representatives:** 135/150 local characters changed shade; mean
chroma change −0.008; higher in only 45/135.

---

## 11. Dead ends — do not repeat

- **Blending the portrait into a 10+ gallery when its hue "agrees".** It flips
  the pale/saturated branch. Verified with Artoria. (Kept as a comment in the
  code so it is not re-attempted.)
- **Folding the pale class into a single distribution.** Lucy regresses. The
  class split exists for a reason.
- **Replacing mass pooling with a per-image vote without retuning the
  thresholds.** The confidence scale changes; the pale/saturated rules silently
  break.
- **Median-of-per-image representatives as a "less washed out" fix.** It lowers
  chroma on average; the pooled percentile is mass-weighted and often more vivid.
- **Simple background stripping for complex art.** Does not generalise.
- **Training an accent-predictor ML model on a handful of picks.** Too little
  data; it learns your hue preferences, not the task.

---

## 12. Open problems and proposed next steps

Ordered by value, roughly:

1. **Apply the manual override to Audrey** (and others you care about) — the
   immediate fix. Each pick is a label.
2. **Percentile tuning for "washed out".** Raise `SAT_PERCENTILE` /
   `VAL_PERCENTILE` (or bias the representative toward the vivid end of the band)
   and run the calibration panel. Cheap; addresses the symptom directly.
3. **Build the calibration set** from overrides (and non-overridden targets),
   with the dominant/subject/iconic tag, then do a bounded parameter search
   against it. Keep the parameter count small; cross-validate.
4. **Prototype foreground segmentation** (pretrained anime saliency) as the real
   fix for background-beats-subject; score it against the calibration set. Offline
   batch is acceptable.
5. **Only then consider a small model** on engineered colour features, benchmarked
   against (2)–(4), not as a first move.
6. **If the vote is revisited**, retune `MIN_CONFIDENCE`, `MIN_MARGIN`,
   `PALE_*` against the panel on the *vote's* scale, and keep the two-colour
   decline and the pale class intact.

---

## 13. Current code state and branches

- **Shipped on `portrait-accent-weighting`:** `7076533` (portrait weighting),
  `84ca250` (10+ exclusion).
- **Shipped on `accent-override`:** `73a5049` (override + picker), branched from
  `portrait-accent-weighting`.
- **Reverted in full:** every change for the per-image vote / median rewrite.
  `accent_extract.py` currently contains V2 (mass pooling + class split + portrait
  weighting + 10+ exclusion).
- **Not built:** segmentation, calibration search, feature model.
- **Related earlier work:** the gallery/portrait pipeline (`d19e6dc`, `1e06ca6`,
  `85742b1`) and the traits editor (`9028ebd`) are separate but touch the same
  `accent_extract`/`characters` surface.

**Key files:**
`accent_extract.py` (measurement, decision, ensure/recompute),
`scripts/recompute_accents.py` (batch backfill),
`tests/test_accent_extract.py` (rules + calibration panel),
`routes/customs.py` (returns the seed + `accentManual`),
`routes/characters.py` (`/api/accent-override`),
`db.py` (`set_accent_override`, `clear_accent_override`, `get_accent_override`),
`migrations/007_character_accent.sql`, `migrations/013_character_accent_override.sql`,
`frontend/src/hooks/useCharacterTheme.js`,
`frontend/src/utils/accentFromImage.js`,
`frontend/src/utils/imagePick.js`,
`frontend/src/components/AccentOverrideControl.jsx`.
