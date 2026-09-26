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
- **2026-09-26, Lynae (§14):** a 96-image gallery of vivid cyan art produced a dark
  slate `#2c3946`. Three compounding faults: the confidence test measures one 5°
  bin, so a colour spread over cyan→blue "declines" at 0.048 against 0.05; a
  declined 10+ gallery silently hands the whole answer to the portrait; and the
  portrait's grey background scraped past the chroma floor. Investigating it
  showed the *shade* logic makes seeds dark and muted **library-wide** (median
  chroma 0.085, 17 of 68 seeds darker than L 0.45), that the pale class leaks
  pale skin as a dusty pink, and that Reze passes the panel only by the same
  portrait fallback that broke Lynae.
- **Recommended direction (§15):** decide *which hue* by prevalence and *which
  shade* by vividness, as two separate questions. A prototype (V8) keeps every
  hue but Reze's, lifts median chroma to 0.122 and cuts dark seeds from 17 to 4.
- **Same day, follow-up (§16):** foreground segmentation (skytnt/anime-seg) was
  prototyped and moves Lynae from sky blue to cyan `#34b0c1` — her sky-blue is
  the backgrounds, her teal/mint is on her. Measuring *every* image rather than a
  60-sample exposed the skin leak in Madoka too; a wider skin rule fixes it and
  Artoria. Reze is **not** fixed by using all 122 images: her art is a genuine
  tie between violet and Bomb Devil red, her hair is too muted to vote, and the
  violet the panel expected came from her portrait's *background*. The harness
  is committed as `scripts/accent_lab/`.
- **Owner's review (§17):** every character judged by eye. Two product rules
  came out of it — a tie between two colours goes to whichever the main image
  carries more of, and no character goes without an accent if its main image
  has a colour. The resulting pipeline (V18) passes 21 of the 23 reviewed
  characters (current: 17), leaves 2 of 80 accents near-grey (current: 24) and
  declines none. Open: Ceres Fauna's gradient hair and a few warm-window cases.
- **Second review (§18):** Ceres's yellow-green and Artoria's raspberry were
  approved; the gold drift (Will, Ishtar, Dazai, Poison Ivy) was traced to skin
  rewarded by presence pooling, warm whites and windows straddling two colours.
  V24 answers 25 of 26 checks (current: 20).

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

**Known weaknesses of the panel (found 2026-09-26, §14):** it checks hue ranges
almost exclusively, so a seed can pass while being dark and muted (Miku passes
as steel-blue `#3e7e93`, where her teal is nearer `#39c5bb`). Reze passes only
because her gallery declines and the portrait fallback supplies violet — the
exact path that produces Lynae's grey. And nothing asserts the pale-skin leak
does not happen. §15.4 proposes the additions.

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
- **Material Color Utilities' `Score` used as-is** (§14.4). Its chroma bonus
  outweighs prevalence, so tiny neon effects win: Lynae → magenta, Miku → red.
  The *ideas* in it (band proportion, a real cluster colour) are useful; the
  weights are tuned for wallpapers, not illustrations.
- **Choosing the winning hue by band share.** It favours whatever is spread
  widest; Reze's red/pink effects out-sum her violet peak. Use the band share
  for *confidence*, keep the smoothed peak for *location*.
- **One continuous OKLCH chroma weight replacing both classes.** Muted pixels
  get a vote (good for Reze in principle) but low-chroma noise then votes
  everywhere, Lynae's clear cyan drowns and she declines; Lucy's pale identity is
  lost. Same see-saw as the V3 fold.
- **Ranking the shade by HSV saturation.** High HSV saturation is mostly dark
  pixels, so it makes seeds darker, not more vivid. Rank by OKLCH chroma.
- **Dropping the "weak saturated" pale rule to stop segmentation flipping
  Artoria (Alter) pale** (§16.5). Lucy goes royal blue. Widen the skin rule
  instead.
- **Segmenting the 200px measurement copy.** The model misses the character in
  about half of all images at that size; segment the 600px thumbnail.
- **Blaming the sample for Reze.** All 122 images give the same answer as 60
  (§16.2).

---

## 12. Open problems and proposed next steps

> **Superseded in part by §15** (2026-09-26), which re-orders these in light of
> the Lynae investigation. Item 2 below — the "washed out" lever — turned out to
> be the biggest library-wide problem, and §15.2 is a tested version of it.

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

---

## 14. Lynae: a vivid gallery measured as dark slate (2026-09-26)

### 14.1 The report

Lynae (Wuthering Waves) showed a dark grey-blue accent, `#2c3946`. The grey is in
her Mudae portrait — it is the portrait's *background* — while her 96 gallery
images are bright and busy, full of cyan, teal and mint highlights; her hair is
blonde. The expected accent was a vivid teal, and at the very least "anything but
dark".

Stored state on the live row: seed `#2c3946`, `accent_source = portrait`,
`accent_gallery_count = 96`, `accent_partial = 0`, recomputed at
2026-09-26 17:08. So every sampled thumbnail *was* on disk and measured — this is
the algorithm's real answer, not a stale or partial one. Reproduced locally
bit-for-bit from the R2 thumbnails and the Mudae portrait.

### 14.2 Three faults, compounding

1. **The gallery declined on confidence, narrowly.** Her saturated pool peaks at
   HSV 197.5° with a 2.4× margin over the nearest rival (orange at 22°) — an
   unambiguous winner. But `_dominant_hue` measures confidence as the share of
   the *single tallest smoothed 5° bin*, and her colour is spread cyan→azure, so
   no one bin reaches 5%: it scores **0.048 against `MIN_CONFIDENCE = 0.05`**,
   while **39%** of all saturated mass sits within ±22.5° of the peak. The
   metric penalises exactly the characters whose colour is shaded across a range.
2. **A declined 10+ gallery hands the answer to the portrait.** The "portrait
   steps aside at ten" rule (§4.3) only applies when *both* sides decide. When the
   gallery declines, `decide()` returns the portrait's result outright — 96
   images of vivid art lose to one 225×350 portrait.
3. **The portrait's answer is a grey that passed the grey filter.** Its hue is
   right (blue, ~210° HSV) but the blue pixels are mostly dark clothing and the
   grey background; the 0.55 value percentile lands at V≈0.28. The seed is
   OKLCH L 0.34, **C 0.029** — just over `MIN_CHROMA = 0.025`. The frontend
   (`accentFromImage.js`) holds a seed's chroma and only walks lightness for
   contrast, so a C 0.03 seed is grey in both themes whatever it does.

**It is also unstable.** Which 60 of her 96 images `evenly_sample` picks decides
the outcome: a different sort order produced a proper blue (`#418dac`), and of
200 random 60-image samples of her gallery only **48** clear the confidence
floor. Adding or deleting one image can flip the colour.

Her hue histogram, per image rather than pooled: the 180–210° HSV family carries
≥10% of an image's saturated mass in **77%** of her images — the strongest
per-image consistency signal of any character examined.

### 14.3 What the investigation found beyond Lynae

- **Dark and muted is library-wide, not a Lynae quirk.** Across the 79 local
  characters with ≥6 cached thumbnails, current seeds have median chroma **0.085**
  and median lightness 0.52; **17 of 68** seeds are darker than L 0.45. Panel
  characters that "pass" are visibly muddy: Miku `#3e7e93` (steel blue),
  Tsumugi `#936e4d` (brown), Madoka `#ac5a69` (dusty rose), Kafka `#602d48`.
  Cause: the shade is a 0.6/0.55 percentile over *all* the band's mass, and the
  band's mass is dominated by shaded and shadowed pixels of the colour.
- **Reze passes the panel by accident.** Her gallery declines on the same 5%
  floor (0.046); her violet comes from the portrait fallback — fault 2 above.
  Her violet hair is in the classifier gap (muted, V < 0.5), the same gap as
  Audrey's green (§4.4), so it casts almost no vote. What does vote red/pink is
  blush, lips, lanterns and explosion effects (verified with a pixel mask). Fix
  fault 2 and she loses violet; her true identity needs segmentation or an
  override.
- **The pale class leaks pale skin.** 20 of 68 current seeds have chroma < 0.05,
  and many are the *same* dusty pink: Ruby Hoshino `#dfb8bd`, Alisa Kujou
  `#dfb8ba`, Illya `#dfb8bc`, Sesshomaru `#dfb8b9`, Patchouli `#c6a4a3`.
  Silver-, white- and purple-haired characters converging on one pink is the
  signature of skin highlights: `SKIN_HUE` is 12–48°, but pale anime skin sits at
  roughly 340–15° with saturation 0.1–0.3 and high value, straight into the pale
  class. *Strong hypothesis, not yet confirmed with a mask.* The identical hexes
  also come from the pale representative being read off a coarse 0.05 grid.
- **Two more characters had the Lynae pattern** (10+ gallery declined, portrait
  answered): The Sandman `#344653` and Vertin `#463c60` — both dark slate.

### 14.4 What was tried

All in a scratch harness against the calibration panel plus Lynae, then V8
against the whole local library. Nothing was committed.

| version | idea | result |
|---|---|---|
| MCU | Material Color Utilities: Celebi quantiser (128 colours/image, pooled with equal weight per image) + its `Score` | **Wrong across the board.** Lynae magenta `#f207f9`, Miku red, Reze red, Lucy royal blue. The chroma term `(C−48)×0.3` beats the proportion term, so small neon effects win. Dead end as-is. |
| V5 | band-share *winner* and confidence (±22.5°), vivid-core shade by OKLCH chroma, coverage gate | Vivid, Lynae seeded `#409ec7`. But Reze → pale pink (band winner picks the widest spread, red), Tsumugi declined (lost the pale→saturated fallback). |
| V6 | smoothed *peak* picks the hue, band share is only the confidence; vivid core ranked by HSV saturation; hue pinned ±10° of the peak | Reze still pink; **seeds got darker** — high HSV saturation is mostly dark pixels (Miku L 0.51, Lynae `#1f719d`). |
| V7 | replace both HSV classes with one continuous OKLCH weight `ramp(C, 0.02→0.10)`, sqrt "presence" pooling | Miku a real teal `#41a7b6`, Tsumugi clean gold. But **Lynae declined** (low-chroma noise spreads her histogram flat) and Lucy lost her pale identity. |
| **V8** | shipped classes and pale rules + peak location + **band-share confidence (≥0.20)** + coverage gate (≥3% of pixels) + **vivid-core shade** (top 35% of band mass by OKLCH chroma, mean L and C, hue pinned to the peak, gamut-fit by shedding chroma) + **a declined 10+ gallery stays declined** | 9/10 on the panel (fails Reze only — see above). Lynae `#3793c6`. Library: below. |
| V9 | V8 + classifier-gap pixels (S 0.10–0.22, V ≥ 0.25) vote at half weight | No change for Reze (her hair is darker/greyer still); Tsumugi declined. Not worth it. |

**V8 on the local library (79 characters):**

| | current | V8 |
|---|---|---|
| seeded | 68 | 71 |
| median chroma | 0.085 | **0.122** |
| median lightness | 0.52 | 0.56 |
| seeds darker than L 0.45 | 17 | **4** |
| seeds with C < 0.05 | 20 | 21 (the pale path is untouched) |
| hue moved > 30° | — | 1 (Reze) |

Seeded → declined under V8: 2B (correct), The Sandman, Vertin (both were the
portrait-fallback slate). Declined → seeded: Nico Robin (pale `#d2b4ae` —
**wrong**, she is the documented two-colour case and the pale path let her
through), Osamu Dazai, Rebecca (pale grey-blue — doubtful), Stocking Anarchy,
Ceres Fauna, Kaguya Houraisan (pale pink — probably the skin leak).

Panel side by side (current → V8): Miku `#3e7e93`→`#258ea5`, Saber
`#2d4079`→`#304598`, Reimu `#933530`→`#b7413c`, Madoka `#ac5a69`→`#b95168`,
Audrey `#9f8c44`→`#c3a643`, Tsumugi `#936e4d`→`#ac7746`, Lucy unchanged, 2B
declined.

**On "teal".** V8 gives Lynae a bright sky blue (OKLCH hue 237), not a teal
(~185). Her pooled peak is HSV 197.5°, between cyan and azure, and the mint/teal
highlights (HSV 160–185) are a secondary shoulder of it. Whether sky blue is
acceptable or teal is required is a judgement for the owner; if teal is
required, it is a *hue-location* question, not a shade question, and the
override is the immediate answer.

---

## 15. Recommended approach (2026-09-26)

The lesson of every experiment, old and new, is that the extractor has been
asked one question when there are two:

- **Which hue is this character?** — a *prevalence* question: the colour the art
  keeps returning to. The shipped machinery (per-image normalisation, smoothed
  peak, rival margin, the pale class for soft identities) answers it reasonably
  well, and every attempt to replace it wholesale regressed something.
- **Which shade of that hue represents it?** — a *vividness* question: the
  colour a person would point to, which is the clean, saturated core of the
  band, not its average. The shipped percentile answers it badly everywhere,
  and fixing it moves no hues.

Keep the first, replace the second, and fix the plumbing between them. In order:

### 15.1 Decision plumbing (fixes Lynae; low risk)
- **Confidence as band share.** `share of pooled mass within ±22.5° of the
  peak ≥ 0.20` instead of `single bin ≥ 0.05`. The peak *location* and the rival
  margin stay exactly as shipped. The pale-identity rules keep using the old
  single-bin confidence, because their thresholds are calibrated to that scale
  (§7.4).
- **A declined 10+ gallery stays declined.** Never fall back to the portrait
  once the portrait has no vote. The character gets the system accent — which is
  honest — and the override exists for the ones someone cares about.
- **A coverage gate.** Decline when the winning band covers < 3% of all pixels
  across the pool. This is what lets 2B decline *because she is greyscale*,
  rather than by a seed happening to fall under the chroma floor.
- **Keep the pale→saturated fallback** when a pale seed is too grey.

### 15.2 Shade: the vivid core (fixes "dark and muted" library-wide)
Within the winning band, pooled per image: take the most chromatic 35% of the
mass (by OKLCH chroma, not HSV saturation), average its L and C, pin the hue to a
mass-weighted mean within ±10° of the peak (so the shade cannot drift toward the
more gamut-rich neighbour — blue beside cyan), and bring it into sRGB by
shedding chroma, never by moving hue. Measured effect: §14.4.

### 15.3 The pale path (next, not yet prototyped)
- Extend skin rejection to pale pinks (roughly hue 340–15°, S 0.08–0.35,
  V ≥ 0.7) *for the pale class*, then confirm with masks on Alisa, Ruby,
  Sesshomaru. Madoka's pink hair is more saturated and should be unaffected —
  check.
- Give the pale path the same margin test the saturated path has, so a
  two-colour character (Nico Robin) cannot enter through it.
- Audit all C < 0.05 seeds: a pale identity is legitimate (Lucy, Frieren, Gojo)
  but it should be the exception, not 30% of seeds.

### 15.4 The panel as a real contract
- Add **Lynae**: hue 170–240, C ≥ 0.09, L ≥ 0.55.
- Add a **vividness floor** to every non-pale entry (C ≥ 0.08, 0.42 ≤ L ≤ 0.8),
  with Saber's "deep" and Lucy's "pale" as explicit exceptions.
- Mark **Reze** as a known semantic failure (or give her an override and assert
  the override wins), rather than letting her pass by the fallback.
- Add a **skin-leak regression**: Alisa Kujou / Ruby Hoshino must not seed
  pale pink.
- Add **Nico Robin**: must decline.

### 15.5 Measure every image once, and use all of them
The 60-image `evenly_sample` makes the answer depend on which images happen to
be picked (Lynae: 48/200). Per-image measurement is small (a few hundred grid
cells), so compute it once when the thumbnail is rendered and store it with the
image row; the character's pool is then a sum over *all* active images, is
stable as images come and go, and a recompute costs no image decoding at all.

### 15.6 Still the route for the semantic cases
Reze (muted violet hair losing to blush and explosions) and Audrey (green dress
under gold hair) are unchanged by all of the above. Foreground/hair
segmentation (§5.2.1) remains the algorithmic answer, and the override the
practical one.

### Reproducing the experiments
Everything in §14–18 runs from `scripts/accent_lab/` — see its README. Each
variant in the tables is a `method_<name>` in `scripts/accent_lab/methods.py`.

---

## 16. Follow-up: all images, segmentation, and Reze (2026-09-26)

### 16.1 The owner's calls
- **Lynae must be teal or mint, not sky blue.** Added to the lab panel as OKLCH
  hue 150–205, C ≥ 0.09, L ≥ 0.55.
- **Measure all of a character's images, not a sample** — prompted by Reze's
  contact sheet, where the images shown happened to carry little purple.

### 16.2 Reze with all 122 images: not fixed
Shipped extractor, V8 and every later variant give the same answer on all 122
live images as on the 60-image sample. The sample was not the problem:

- Across all 122, saturated violet-family pixels cover **11.0%** of the frame and
  saturated red-family **11.1%**; each family wins in exactly **61** images. Her
  art is an honest tie.
- The red is not noise. Masking the red-voting pixels shows explosions, fire and
  blood — the Bomb Devil — and in 71 of 122 images it outweighs violet *within the
  segmented character*, because the effects wrap around her.
- Her hair is dark greyish purple: it falls in the classifier gap (§4.4) and
  barely votes at all.
- **The violet `#6a549f` the panel expects came from her Mudae portrait's violet
  background.** With the background masked, the portrait's strongest colour is
  the navy ribbon and choker.

So "Reze is violet" means "Reze's *hair* is violet" — a semantic judgement, not a
pixel statistic. Options are in §16.6.

### 16.3 Measuring every image changes results
The 60-image `evenly_sample` was hiding a failure. With all 70 of her images
the **shipped** extractor gives Madoka `#dfb8bf` — the pale-skin pink of §14.3 —
where the sample gave `#ac5a69`. Sample-dependence cuts both ways: Lynae's
result depended on it too (§14.2). Measuring everything is the only stable
baseline, and every number in this section uses `--all`.

### 16.4 Foreground segmentation, prototyped
[skytnt/anime-seg](https://huggingface.co/skytnt/anime-seg) (`isnetis.onnx`,
176 MB, Apache-2.0, ~0.5 s per image on a laptop CPU through onnxruntime)
produces a character mask; background pixels are painted white, which the
classifier already ignores.

- **The mask must be computed on the 600px thumbnail.** On the 200px measurement
  copy the model found under 3% foreground in 46 of Lynae's 96 images. At full
  thumbnail size: median foreground 57%, no misses.
- **Wide scenes the model cannot separate** (it calls >85% of the frame
  "character") are dropped rather than measured whole.
- **Lynae:** in the full frame, sky blue (HSV 200–225°) is 25% of her saturated
  mass and teal/mint (150–180°) 18%; inside the mask, 20% and 21%. Masks of
  which pixels vote which way show why: sky blue is skies, water and city
  lights; teal/mint is her jacket trim, hair streaks and effects. Her pooled
  peak moves to HSV 187.5°, and the segmented Mudae portrait peaks at the same
  place.

### 16.5 The variants, and what they did

| version | change over the previous | Lynae | Reze (live) | note |
|---|---|---|---|---|
| V8 | §14.4 | `#3795c7` sky | `#c6a6a3` skin pink | |
| V8s | V8 + pale skin rejected (hue 335–20°, S ≤ 0.35, V ≥ 0.45) | `#aec6d2` pale | `#b34132` red | fixes Madoka's leak |
| V10 | V8 on the segmented foreground | `#38aac5` | `#c6a6a3` | skin is foreground, so the leak remains |
| V11d | V10 + skin rule + drop unseparable scenes | **`#34b0c1`** | declined | |
| V12 | V11d + **portrait as tie-breaker** | **`#34b0c1`** | `#4c649e` navy | see below |

**V12's tie-breaker.** The gallery proposes candidate hues (smoothed peaks at
least 60% of the top one, 60° apart, each holding ≥15% of the pool); the
segmented portrait chooses among them by which band it carries most of. The
portrait never introduces a hue and never blends into the pool, so the
Artoria trap (§4.3) cannot recur through it. It only acts at 10+ images when
there are two or more candidates.

**Two traps found on the way.**
- *Segmentation re-triggers the pale rule.* Removing Artoria (Alter)'s red
  backgrounds dropped her saturated confidence under `PALE_REP_MAX_SAT_CONF`,
  and the "weak saturated" pale rule gave her grey-mauve `#93797d`. Removing
  that rule fixes her but sends Lucy to royal blue — the same see-saw as V3.
  The actual culprit was shaded skin at V 0.45–0.6, just under the first skin
  rule's V ≥ 0.6; lowering it to 0.45 restores Artoria's crimson and changes no
  other panel character.
- *Lynae is cyan, not teal, and the pixels do not say otherwise.* Inside the
  mask her colour is flat across mint (21%), cyan (21%) and blue (20%); the
  centre of that is cyan, HSV 187.5° = OKLCH ~208°, just outside the 150–205
  teal range. Nothing in the pixels prefers teal over cyan — the jacket trim is
  what makes her read as teal. Tuning a threshold until she lands on teal would
  be fitting one character's preference (§11). V12's `#34b0c1` is turquoise;
  whether that is "teal enough" is the owner's call, and the override gives
  exact teal today.

**Across the library** (80 characters, every image, `library.py`):

| | current | V8 | V11d | V12 |
|---|---|---|---|---|
| seeded | 70 | 72 | 70 | 72 |
| median chroma | 0.083 | 0.116 | 0.127 | **0.127** |
| median lightness | 0.52 | 0.56 | 0.55 | 0.54 |
| darker than L 0.45 | 18 | 4 | 7 | 7 |
| near-grey (C < 0.05) | 21 | 23 | 10 | **9** |

Judged by eye on a contact sheet of every character V12 changes:
- **Better:** Madoka (skin pink → her pink `#c55465`), Patchouli (skin pink →
  muted purple `#8c7993`), Lynae, Artoria (crimson kept), Stocking Anarchy
  (declined → blue), Alisa Kujou (skin pink → declined, honest), The Sandman
  (dark slate → declined), Panty Anarchy (pink → cream, nearer her blonde).
- **Doubtful or worse:** Nico Robin now seeds red-orange `#bf5444` — the
  tie-breaker overrides the two-colour decline §2 insists on, by design; Hiyuki
  slate → red; Columbina pale lavender → magenta; Vertin dark purple → pale
  grey-blue; Ceres Fauna blue while her hair is green; Yuta Okkotsu and Will
  Auceptin → declined; Touka Kirishima → pale blue.

### 16.6 Where this leaves the recommendation

§15 stands, with these amendments:

1. **Measure every image** (§15.5 moves up — it is a correctness fix, not a
   performance one).
2. **Widen the skin rule** to pale pinks with V ≥ 0.45 (§15.3's first item,
   now measured). It is the single biggest fix for grey accents: near-grey seeds
   21 → 9.
3. **Segmentation is worth adopting**, computed once per image when its
   thumbnail is rendered and stored with the per-image measurement (§15.5), on
   the 600px thumbnail. It is what moves Lynae off sky blue. The cost is a
   176 MB model and onnxruntime on the origin box (ARM builds exist); it must be
   checked for memory on the Oracle instance before committing to it.
4. **The tie-breaker is a product decision, not a tuning one.** It gives Reze
   navy instead of pink or nothing, but it also gives two-colour characters like
   Nico Robin a colour where the current rule deliberately declines them. Decide
   which is preferred: "the portrait's pick of the two" or "the system accent".
5. **Reze needs one of:** (a) hair segmentation — an anime face-parsing model
   that labels hair specifically, so the identity colour can be read from the
   hair alone; (b) the override, which is available today; or (c) accepting a
   non-violet answer. (a) would also be the principled fix for Lynae's teal and
   Audrey's green, and is the next thing worth prototyping.
6. **Fix the panel.** Reze's violet expectation tests a portrait background;
   change it to reflect the owner's intent explicitly (an override, or a
   hair-based check once one exists), and add Lynae, Madoka-with-all-images,
   Artoria (Alter) and Nico Robin.

---

## 17. The owner's review of V12, and V13–V18 (2026-09-26)

### 17.1 The verdicts

The owner went through the V12 contact sheet character by character:

| character | verdict | what it means for the extractor |
|---|---|---|
| Lynae | cyan is good | accepted; turquoise-cyan is fine |
| Columbina | V12's dark pink is fine (light blue or pink both are) | two-colour characters may take either |
| Hiyuki | red or blue both fine | ditto |
| Vertin | grey-blue or purple both fine | ditto |
| Himeno | not brown — grey, leaning blue-grey or navy | |
| Rebecca | her light teal/cyan/green **hair**, in every image | light colours must be able to win |
| Ceres Fauna | overwhelmingly light mint green; blue is baffling | ditto |
| Panty Anarchy | a stronger, clearer yellow | pale identities must still read as colour |
| Reze | violet: compare the two main colours with the main image | **the main image breaks ties** |
| Nico Robin | the main image should pick the main colourway | ditto |
| Yuta, Alisa, Will Auceptin, The Sandman | should not decline | **fall back to the main image alone** rather than show no colour |

Two of these are product rules, not tuning targets, and are now decided:
**a tie between two colours goes to whichever the main image carries more of**
(this settles §16.6 item 4), and **a character never goes without an accent
when its main image has a colour**.

### 17.2 A flaw in the earlier lab numbers

The local working library has main images (`data/portrait_samples/`) for only
the 13 panel characters. Every other character in §14–16 — Himeno, Yuta,
Rebecca, Alisa, Will, The Sandman, Ceres, Panty — was measured **with no main
image at all**, so neither a tie-breaker nor a fallback could act for them.
Everything in this section uses characters fetched live (`fetch_live`), main
images included: the 23 in the owner's review plus all 80 library characters.

Two data problems surfaced on the way. The Sandman's main image was a dead
ImgChest link with no R2 mirror (the owner has since replaced it). Vertin's main
image is intact on the live site — both the Mudae original and the R2 copy.

### 17.3 Why each was wrong

`explain.py` traces one character through the pipeline; these are its findings.

- **Yuta** declined on coverage: his red covers 1.2% of pixels against a 3% floor;
  his art is mostly black and white. His main image is 82% blue.
- **Himeno**'s gallery is an orange/red vs blue tie that fails the two-colour
  margin (1.17 against 1.25). With her main image the tie goes to blue — the
  brown came purely from the missing main image.
- **Reze**: the gallery *has* a violet peak at 262° next to blue at 222°, but
  V12's candidates had to be 60° apart, so violet was merged into blue and never
  faced the main image. Her main image, whole, is 85% violet — the purple
  background the owner is looking at.
- **Rebecca and Ceres Fauna**: their identity is **light hair**. Light colours
  only live in the pale class, which never voted on the hue — it could only take
  over through the narrow pale-identity rule. Rebecca's pale teal/cyan appears
  in about half her images, more than any saturated blue; Ceres's pale
  yellow-green in 71%.
- **Panty**: blonde hair sits at HSV 40–55°; the *shipped* skin rule removes
  hue 12–48°. Her yellow barely registered.
- **Very pale skin** (S < 0.12, peach) slipped under both skin rules into the
  pale class, where it flooded the hue vote as beige (Himeno, Vertin, Yuta).
- **Ceres Fauna's hair is a gradient** — yellow-green where lit, green through
  the middle, teal at the tips (confirmed by masking which pixels are which).
  "Mint" is the whole gradient; any one window catches only one end of it.

### 17.4 The variants

| version | change | result on the review (23) |
|---|---|---|
| V13 | pale votes on the hue; candidates 30° apart; the **whole** main image breaks ties; main-image fallback | Rebecca and fallbacks fixed; pale skin floods the vote (Reze, Madoka pink; Himeno beige) |
| V14 | clusters between valleys; skin rule through orange | Reze violet, Alisa pink; clusters came out 170° wide |
| V15 | skin stops at 38° (blonde survives); pale vs saturated compared directly for the shade; tie aim where gallery and main image agree | Panty clear yellow; Lucy lost pale |
| V16 | fixed ±30° colour windows, shipped pale rule restored alongside | 19/23 |
| V17 | V16 tuned: pale weight 0.5, presence pooling (√ per image), gallery-weighted aim; tinted pale identities lifted to C ≥ 0.09, grey ones left alone | 21/23 |
| **V18** | V17 + the aim stays within ±15° of the winning colour; a tie with no main image takes the stronger side | **21/23**, and fixes the pale-gold drift below |
| V19 | V18 + shaded skin (V 0.45–0.6) removed from the saturated class | no gain; Ishtar worse. Dead end. |

**V17's pale-gold drift.** On the whole library V17 turned Ereshkigal, Ishtar and
Will Auceptin pale gold. Their winning colour was correctly red, but the final
hue was aimed anywhere in the ±30° window, whose edge (≈42°) is where pale
blonde and skin pile up. V18 keeps the aim within ±15° of the window's centre:
Ereshkigal returns to red.

### 17.5 Results

**The owner's review** (23 characters, all live, every image):

| | current | V12 | V18 |
|---|---|---|---|
| passes | 17 | 14 | **21** |

**All 80 library characters, live:**

| | current | V12 | V18 |
|---|---|---|---|
| seeded | 79 | 75 | **79** |
| median chroma | 0.081 | 0.123 | 0.119 |
| median lightness | 0.50 | 0.54 | 0.55 |
| darker than L 0.45 | 25 | 6 | 11 |
| near-grey (C < 0.05) | 24 | 9 | **2** |

V18 per review character: Lynae `#33b0c1`, Reze `#5c4293` (violet), Rebecca
`#2ea6ac` (teal), Himeno `#336b7b` (dark blue-teal), Panty `#fee4a0` (yellow),
Nico Robin `#445aa6` (her main image's blue), Yuta `#78222b` (red — his gallery
now clears the coverage bar on its own), Alisa `#b25185`, Will Auceptin
`#dcb65d`, The Sandman `#374454`, Columbina `#a3b2f0`, Hiyuki `#c6433c`, Vertin
`#78a5d8`, Miku `#2e8aac`, Madoka `#c4536b`, Lucy `#9cace9`, Saber `#2f4b95`,
Reimu `#bc4131`, 2B `#c9bea7` (grey-beige), Audrey `#c4a748`, Tsumugi `#bc9c58`.
Elsewhere: Komi Shouko now dark purple (her hair), Illya pink, Eirin a purple
where she used to decline.

### 17.6 Still open

- **Ceres Fauna** (`#ddefab`, pale yellow-green): the gradient case. Merging two
  tied colours when there is "no real valley" between them was tested and
  does not discriminate — her valley ratio (0.77) sits between genuinely
  separate pairs (Hiyuki's red/blue 0.56, Reze's red→blue path 0.89). Hair
  segmentation would read the whole gradient; the override is the answer today.
- **Artoria (Alter)** comes out deep raspberry `#8b1c55` rather than crimson: her
  red window leans magenta. Borderline.
- **Warm windows**: Ishtar (brown `#966d43`), Osamu Dazai (pale gold), Will
  Auceptin (gold) and Poison Ivy (gold) have an orange/gold window winning
  outright — blonde (Ereshkigal in shared art), sepia and warm shading outweigh
  their red. Extending the skin rule (V19) did not help.

### 17.7 Where this leaves the recommendation

§15 and §16.6 stand, with the pipeline now being V18's:

1. Measure every image, segmented on the 600px thumbnail (unchanged).
2. Skin: the shipped rule stops at 38° instead of 48° so blonde survives, and
   pale pink-to-peach skin (hue 335–38°, S ≤ 0.35, V ≥ 0.45) is removed from both
   classes.
3. **Hue evidence** is saturated + ½ × pale, each image normalised, pooled by
   square root (presence over mass). Colours are ±30° windows.
4. **Ties** (within the shipped 1.25 margin) go to the main image, whole —
   background included — and the final hue is aimed where gallery and main image
   agree, within ±15° of the chosen colour.
5. **Shade**: the vivid core of whichever class the band belongs to (pale when it
   outweighs saturated 1.5×, or when the shipped pale rule says so); tinted pale
   identities lifted to C ≥ 0.09.
6. **Never empty-handed**: a tie with no main image takes the stronger side; a
   gallery that cannot decide falls back to the main image alone.

`method_v18` in `scripts/accent_lab/methods.py` is the reference
implementation, and `REVIEW` in `lab.py` is the owner's review as checks.

---

## 18. Second review: the gold drift, and dead main images (2026-09-26)

### 18.1 The verdicts

- **Ceres Fauna's pale yellow-green (`#ddefab`) is right.** The earlier "mint"
  was loose; §17.6's open item is closed.
- **Artoria (Alter)'s raspberry (`#8b1c55`) is fine.**
- **Gold is wrong for Will Auceptin, Ishtar, Osamu Dazai and Poison Ivy.**
  - Will has some gold accents, one yellow background and blonde hair in a few
    images, but it is a minority; red should win.
  - Ishtar's gold is Ereshkigal's hair in shared images plus her golden
    accessories; with little red and many dark tones, a dark grey or navy would
    be expected before gold.
  - Dazai is brown, grey and red with a few dark navies; yellow is in very few
    images.
  - Poison Ivy should be green (everywhere in her art), or red (her hair);
    gold only appears as another character's blonde in two images and as her
    saturated, dark skin.

### 18.2 Correction: not every character had a main image

§17.2 said the review was run "main images included". That was wrong for five
of the 80 live characters: **Eirin Yagokoro, Eternity (R1999), Moghedien,
Shiroko\*Terror and Tsukatsuki Rio** have no usable main image, and
`fetch_live` silently saved none. Eirin's V18 purple came from "a tie with no
main image takes the stronger side", not from her main image. The lab now says
so (`explain` prints "portrait NO").

Checking why: of the 764 library characters, the 107 whose main image still
points at ImgChest all return 404 (none has an R2 copy), and three more have no
main image at all. **This is expected, not damage.** Main images are now direct
Mudae links mirrored to R2 and no longer go through ImgChest, so the old ImgChest
files going away (in the cut-over cleanup) is fine and partly intended; the
characters without one simply have not been captured from Mudae yet and fill in
gradually as people use the site (owner, 2026-09-26). Until then the extractor
treats them as having no main image: no tie-breaker and no fallback.

### 18.3 Why gold, and the fixes (V20–V24)

`explain` and per-image breakdowns found three mechanisms feeding the gold.

- **Presence pooling rewards skin.** V17's square-root pooling favours a colour
  present in most images — and in anime art that is skin and warm shading. All
  four won an *orange* window (22–32°), not a gold one; the aim and the vivid
  shade then turned brown and peach into gold.
- **Warm whites.** Faint pale pixels at 35–70° (S < 0.15: cream paper, ivory,
  warm-lit highlights) were a large share for Will (0.31 of his pale class) and
  real for Dazai and Poison Ivy.
- **Two colours in one window.** A ±30° window centred at 22–28° sums red
  (0–20°) and gold (40–60°), two colours 35° apart, into one that beats either.

| version | change | review (26) |
|---|---|---|
| V20 | the skin-tone zone (hue 10–45°, S ≤ 0.65, or any S when V < 0.55 — brown) votes at ¼ weight instead of being dropped or trusted | Ishtar red; Will, Dazai, Poison Ivy still gold |
| V21 | V20 + windows centred only on peaks + warm whites dropped | the two parts disagree — tested apart: |
| — whites only | | 25/26 (Dazai brown-red, Poison Ivy red) but Lynae pale |
| — peaks only | | 22/26 (broke Panty, Rebecca, Tsumugi) — dead end |
| V22 | V20 + warm whites dropped + aim across the whole window | 25/26; Lynae pale `#7fdce9`, Kotoko Ijichi near-white |
| V23 | whites muted instead of dropped; aim by sub-colour mass | 22/26 — worse; dead end |
| **V24** | V22's measurement decides the **hue**; V20's (whites kept) decides the **shade** | **25/26** |

**Why V24 splits the two measurements.** Dropping warm whites removes pixels
from the pale class, and because each class is normalised per image, what
remains grows — Lynae's pale cyan then out-weighed her saturated cyan and her
shade flipped to pale. Whites now vote on *which hue* but not on *which shade*.

**Will Auceptin stays gold.** Red dominates 5–6 of his 11 images and gold 3,
but those three are almost entirely gold, and every attempt to tip the balance
(pale weight, pooling, aim span, mass-based aim) either left him gold or broke
others. Two asymmetries are behind it: gold gets a pale-class vote that red
cannot (pale red is pink, and pink is removed as skin), and his red spreads over
40° while the gold is packed into 15°. Open.

### 18.4 Results

**The owner's review** (26 checks after this round, all live, every image):

| | current | V18 | **V24** |
|---|---|---|---|
| passes | 20 | 22 | **25** |

V24: Lynae `#34b0c0` (the approved cyan), Reze `#5c4292`, Ceres `#ddefab`,
Rebecca `#34ada6`, Himeno `#336a7a`, Panty `#e1a929` (stronger than V18's
pale yellow), Ishtar `#be3041`, Dazai `#934341`, Poison Ivy `#b13b2c`, Will
`#e1bf5c` (still gold); the rest as §17.5.

**All 79 live library characters** (V22, whose hue choices V24 shares):
median chroma 0.124 (current 0.081), 10 darker than L 0.45 (current 25),
2 near-grey (current 24), none declined.

### 18.5 Still open

- **Will Auceptin** — gold over red (§18.3).
- **Kotoko Ijichi's** near-white yellow was accepted as good enough.
- Characters not yet captured from Mudae (§18.2) get no tie-breaker or fallback
  until they are.

`method_v24` in `scripts/accent_lab/methods.py` is now the reference
implementation, and `lab.REVIEW` holds both rounds of the owner's review.

### 18.6 A random check across the library

To see V24 away from the characters it was tuned on, 25 characters were drawn at
random (seed 20260926) — five from each band of the library ranked by image
count (top 10%, 10–20%, 20–30%, 30–50%, 50–70%), only characters whose main
image loads — and shown with their main image, four gallery images and the
chosen accent alongside the review characters (`sample.py`, `showcase.py`).
One pattern to watch: 8 of the 25 landed on a red. Some are right; blush and
lips sit in the same hue range (0–10°) and the skin-zone damping does not reach
them.

---

## 19. The random sample's reds (2026-09-26)

### 19.1 The verdicts

On the random sample (§18.6): the top 10% all good. Too red, where the owner
expected something else — Mitsuri Kanroji (pale yellow, should be pink "no
contest"), Sakurako Kawawa (should be creamy with hints of pink), Tohru (nearer
orange), Mirio Togata (yellow/orange), Nadeko Sengoku (reddish pink, leaning
pink), Tewi Inaba (pink, clearly wrong as red), Nagatoro-san (darker skin, not
red). All of today's earlier characters good apart from Will Auceptin. Overall:
**too many accents land on a murky brick red or terracotta.** These are now
`SAMPLE_REVIEW` in `lab.py`; approved characters must stay near the colour the
owner saw.

### 19.2 Why

- **Skin shadow, blush and lips** sit at HSV 355–10°, below the damped skin zone
  (10–45°). For Tohru, Nadeko, Tewi, Mitsuri and Nagatoro the winning window was
  centred at 18–28° — skin — and the aim settled at 2–8°.
- **The vivid-core shade picks a band's deepest shading**, which in a pink band
  is red: every shade rule built from saturated pixels alone gave Tewi, Nadeko
  and Sakurako a salmon or red (rendered side by side).
- **Pale pink clothes and hair are removed as skin.** The pale-skin rule (hue
  335–38°) deletes Tewi's dress, Sakurako's cream-pink and Mitsuri's hair —
  but freeing that range (V26) brought back skin highlights and pink
  backgrounds: Panty turned pink, Nephis mauve, Shiki Ryougi red.

### 19.3 Variants

Scored on both review sets together (49 checks).

| version | change | score |
|---|---|---|
| V24 | — | 42 |
| V25 | skin zone wraps down to 350° with the dark rule | broke Superman, Poison Ivy, Dazai — dead end |
| V26 | pale-skin rule starts at 352° (pale pink is not skin) | 38 |
| V27 | V26 + skin shadow 355–10° damped (skin saturation, no dark rule) + shade blended with the bright half of both classes | 39–41 |
| V28 | V24's classes + V27's blend (0.35) + skin-shadow damping | 43: Tohru orange, Mirio yellow-orange, Nagatoro blue-grey |
| **V29** | V28 + pale pink at 335–352° counts once S > 0.25 (skin highlights are fainter) | **43**: adds Mitsuri pink; Narumi's light pink deepens |

A pale/saturated ratio switch ("shade pinks from the bright half, reds from
the vivid core") was measured first and does not separate them: pinks 0.39–0.66,
approved reds 0.32–0.67.

### 19.4 Where it stands

V29 fixes Tohru, Mirio, Nagatoro and Mitsuri. **Still wrong: Tewi Inaba, Nadeko
Sengoku and Sakurako Kawawa (salmon-red), Will Auceptin (gold), and Nephis
(turns brown with the skin-shadow damping).** The limit is the same each time:
at the pixel level, pale pink clothes and hair look like pale pink skin — same
hue, overlapping saturation — so every rule that frees one character's pink lets
skin through for another. A skin- or face-part model that labels skin, hair and
clothes separately is the principled next step; the override covers the rest.

The sample page now shows V29 with V24 and the live site's colour as chips
(`showcase.py --method v29 --compare v24`).

---

## 20. Cost, and colour-profile paths (2026-09-26)

The owner accepted V29 as "pretty decent": the remaining pink/red misses were
the barely-passable ones, and Will Auceptin is bearable.

### 20.1 What it costs

Measured on the owner's desktop (Ryzen 9 7900X, 24 threads), lab code:

| step | cost | notes |
|---|---|---|
| cut-out model (skytnt/anime-seg) | **176 MB** file, **~1.7 GB** peak RAM, **~0.4 s per image** | 1024×1024 input on the 600px thumbnail; once per image, ever, if stored |
| colour measurement | ~65 ms per image | pure-Python pixel loops in the lab; vectorised (numpy) it is a few ms |
| one character, masks cached | Reze (122 images): ~14 s | all measurement; with per-image results stored, a recompute is a sum of stored histograms — milliseconds |
| whole library, from scratch | 9,440 images: **~65 min** for masks + ~10 min measuring | one-off |

The origin is an Oracle Ampere A1 (ARM, 1–4 cores, 6–24 GB). Not measured
there; per-image segmentation will be several times slower than on the desktop
and the 1.7 GB peak is significant on a 6 GB box running the app. The shape that
fits: run the one-off backfill on the desktop, store each image's measurement
with its row, and on the server segment only new uploads, once each, off the
request path.

A body-part model: [siyeong0/Anime-Face-Segmentation](https://github.com/siyeong0/Anime-Face-Segmentation)
(MIT; UNet on MobileNetV2, 512×512; classes background, hair, eye, mouth, face,
skin, clothes) is the closest fit, but it is trained on **faces** — full-body
images would need a face crop first, or accept lower accuracy. Its weights are
undocumented in size; the architecture suggests tens of MB and a fraction of the
cut-out model's time. Unmeasured.

### 20.2 The owner's idea: different paths for different colour profiles

Measured on the segmented character (median across each character's images):

- **Monochrome** — share of pixels with real colour (S ≥ 0.15): 2B 0.28, A2 0.27,
  The Sandman 0.22; everyone colourful 0.46–0.96. Borderline: Nephis 0.33 (cream,
  approved), Alisa 0.31 (silver hair). A monochrome path is clearly detectable; it
  would choose a neutral (black, white or a grey) with at most a slight tint,
  instead of whichever small colourful part of a few images wins today.
- **Pink-dominant** — share of colour evidence at hue 320–12° (pale pink kept) *and*
  the pale share within it:

  | | pink/red share | pale within it |
  |---|---|---|
  | Tewi, Nadeko, Sakurako, Mitsuri (want pink) | 0.77–0.94 | **0.11–0.30** |
  | Zero Two, Kasane Teto, Reimu, Hornet, Daki (approved red) | 0.83–0.99 | **0.02–0.05** |
  | Madoka, Mystia (fine already) | 0.68–0.69 | 0.09 |
  | Panty, Shiki Ryougi (broke when pale pink was freed globally) | 0.36, 0.63 | 0.11, 0.07 |

  Pink/red dominance alone does not separate pinks from reds; **pale share within
  the pink/red does**, and together they exclude Panty and Shiki. That is the
  point of a profile path: pale pink can count as identity *only* where the whole
  gallery is pink, which is exactly what the global rule could not do. Caveat:
  the thresholds come from four characters, and the gap to the reds (0.05 vs
  0.11) is narrow — it needs the full library and the review checks before it
  is trusted.

---

## 21. Colour-profile paths (V30), prototyped (2026-09-26)

The owner's idea from §20.2, built: V30 profiles each character on its cut-out
images and sends two profiles down their own path; everyone else keeps V29.

- **Monochrome** (under 30% of pixels carry real colour): the dominant tone of the
  non-skin pixels, with a faint tint (chroma 0.03–0.045 — the frontend refuses
  seeds under 0.025). The tint comes from cool neutrals only; warm ones are mostly
  skin, and without a cool tint it falls back to a hint of blue. 2B `#4b4d5f`,
  A2 `#6c6c80`, The Sandman `#1e313a`.
- **Pale pink** (at least 70% of the colour pink/red, and at least 10% of that
  pale): pale pink counts as identity instead of skin; the hue is aimed where the
  *pale* pinks sit (HSV 315–358°) — the saturated evidence at 0–20° there is
  skin shadow and red details — and the shade leans 75% to the band's brighter
  pixels. Tewi `#ca8397`, Nadeko `#d18094`, Sakurako `#cb8498`, Mitsuri `#d790a3`.

**On the review checks: 46 of 49** (V29: 43). Tewi, Nadeko and Sakurako now pass;
nothing approved broke. Will Auceptin takes the monochrome path and becomes a light
grey-blue (`#a2b8c4`) instead of red: his colour is 37% red, 2B's 35%, and A2's red
leads in more of her images than his, so no statistic here separates him from them.

**Scan.** 224 characters profiled — every one of the first 196 in the 10–30 band
(the band where pale-pink characters cluster; stopped early at the owner's
request) plus 28 from the other bands and earlier examples. 25 took a path
(13 pale pink, 12 monochrome), 17 of them in the 10–30 band. New ones that look
right: Mori Calliope, Sylveon, Lily White, Yuji Itadori (pink), Sora Kasugano,
Mei Mei, Osaragi, Ken Kaneki (monochrome). Likely false positives to judge:
Annie Leonhart and Himiko Toga (pink), Semiramis (lavender → dark wine). The page
(`profiles.py`) shows every path character, the near misses on each threshold and
an unchanged sample.

---

## 22. The owner's review of V30, and V31–V32 (2026-09-27)

### 22.1 The verdicts

- **Monochrome.** Will Auceptin's move to the monochrome path made him *more*
  accurate — white is his most common colour, red his highlight — but he should
  be closer to pure white, without the blue tint. Ken Kaneki is black and white,
  sometimes with red highlights: show the highlight when there is a prominent
  one, but not softer background blues, browns or greens. 2B and A2 should pick
  a side — pure white or very light grey (their white hair) or pure black or
  very dark grey (their clothes) — not a bluish mid grey: the forced tint is
  unwanted.
- **Pale pink.** Semiramis (black clothes, dark red; pale skin under warm light —
  a warm grey would fit), Annie Leonhart (blonde; brown second), Himiko Toga
  (cream) and Evernight Goddess (red, shifted to pink) were false positives. The
  other pinks looked good, but suspiciously alike — pale skin with hints of pink
  seemed to get the same colour as genuinely pink characters. Very pale
  skin-tone pinks could perhaps be ignored or weighted down.
- Sakurako Kawawa and Kasumi Yamabuki share one gallery (the same 19 images):
  matching colours are correct.

### 22.2 What the measurements showed

- **Side.** Near-white (S < 0.15, V > 0.8) against near-black (V < 0.3) on the
  cut-out: Will 0.35 vs 0.10, Sora Kasugano 0.39 vs 0.01 — white; 2B 0.10 vs 0.43,
  A2 0.14 vs 0.27, Mei Mei, Osaragi, The Sandman — black.
- **Tint.** Every monochrome character's grey tint is tiny (0.002–0.009), so tint
  *strength* separates nothing. What separates The Sandman is *consistency*: 94%
  of his greys lean cool; 2B, A2, Mei Mei, Kaneki and Himeno sit at 54–60% —
  no lean.
- **Highlight.** A saturated hue family's mean coverage of the character: Kaneki's
  red 4.4%; 2B 0.1%, A2 0.6%, Will 0.4%.
- **Pale pink present or not.** Pixels at hue 315–355, S 0.15–0.45, V ≥ 0.7:
  0.0% for Semiramis, Annie and Himiko Toga, 0.5% for Evernight Goddess; 1–13%
  for every genuine pink. Their "pink" was warm-lit skin.
- **Why the pinks looked alike.** Most had their chroma lifted to exactly the
  0.09 floor, which erased the real differences; the hue was also shared.

### 22.3 V31 and V32

- **Monochrome** picks the side that covers more (seed L 0.93 or 0.22); tints by
  how consistently the greys lean cool (none at ≤ 55%, full 0.045 at 95%); and
  when one saturated hue family covers ≥ 2% of the character on average and shows
  in ≥ 15% of images, that highlight becomes the accent instead.
- **Pale pink** additionally needs real pale pink: ≥ 0.8% coverage (median) or
  present in ≥ 15% of images.
- **V32** shades each pale pink from the character's own pink pixels only (hue
  320–355°, so red and skin cannot mix in): the brighter half, then its most
  chromatic 35%, with no floor.

| character | V29 | V30 | **V32** |
|---|---|---|---|
| 2B, A2 | brown | bluish grey | black `#1b1b1b` |
| Will Auceptin | gold | bluish grey | white `#e8e8e8` |
| Ken Kaneki | red | bluish grey | red `#c72e29` |
| The Sandman | slate | slate | deep blue-teal `#001e2b` |
| Sora Kasugano | olive | blue-grey | white |
| Semiramis | lavender | wine (pink path) | lavender (standard) |
| Annie Leonhart | gold | dusty pink | gold `#c1a358` |
| Evernight Goddess | red | pink | red `#d5404c` |
| Sylveon / Mori Calliope | — | `#dc8ea3` / `#ce7994` | `#ee99ae` / `#df88a4` |
| Sakurako / Tewi | red | `#cb8498` / `#ca8397` | `#dba0ae` / `#dc9dac` |

**Checks: 47 of 49** (with Will's check updated to accept near-white).

**Frontend.** Seeds under chroma 0.025 are refused by `accentFromImage.js`
(`MIN_CHROMA`), and the page falls back to the site accent. The monochrome path's
near-white and near-black seeds need `themeFromSeed` to build a neutral theme
instead of returning null before they can show on the site.

### 22.4 Still open

- **Himeno** is now on the monochrome path and becomes near-black; the earlier
  approved colour was a blue-grey/navy. Her greys lean cool 60% of the time —
  the same as 2B — so the tint rule cannot keep hers without giving 2B one.
- **Himiko Toga** falls back to the standard path's brick red (cream wanted);
  **Semiramis** to lavender (warm grey wanted). Both are warm-lit skin cases.
- **Nephis** (brown since V28's skin-shadow damping) and **Narumi Momose** (a
  deeper pink since V29).
- **Gu Yue Fang Yuan** took the highlight rule (red `#922426`) — unreviewed.
