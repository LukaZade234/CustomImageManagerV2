# The character accent colour

A retrospective of the accent-colour feature: every idea proposed, every version
of the logic tried, what worked, what did not, and why — so that revisiting it
does not repeat the same mistakes.

This is a working document, not a design spec. The design rationale that still
holds lives in `DECISIONS.md` and `DESIGN.md`; this one is the full history and
the open questions, including the dead ends.

---

## TL;DR

> **Where it ended (2026-09-27):** the lab work stopped at **V43** by the owner's
> decision (§43) — 84 of 96 review checks, against 59 of 80 when the review sets
> began. It is not in the app yet: §29 has its behaviour step by step, the list of
> characters still open (for the manual override), and the checklist for porting it.

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
- **Random sample and profile paths (§19–23):** a random sample exposed murky
  brick reds (skin shadow, and pale pink removed as skin). The owner's idea of
  **colour-profile paths** was built: *monochrome* characters take a neutral
  (near-white or a faintly tinted mid tone) or a recurring highlight colour; *pale
  pink* characters (almost all pink/red, with real pale pink present) treat pale
  pink as identity. V33.
- **Full check and V34–V37 (§23.4–28):** V33 run over all 599 characters with 4+
  images; the owner's review found greens split by HSV geometry, main-image
  backgrounds deciding ties, near-monochrome misses and empty accents. **V37 is the
  current candidate: 73 of 87 review checks.** Open items, the full list of flagged
  characters that never changed, and the suggestions are in §28; how to resume is
  §29.
- **Skin models measured (§30):** an anime face detector plus a face parser
  (18 MB, ~270 MB RAM, ~0.12 s per image — a sixth of the cut-out) reliably
  labels face skin and hair, but only around the head; no small full-body anime
  parser exists, and photo-trained models fail on anime. Whether it moves the
  flagged characters is untested.
- **Skin trial (§31):** removing face skin does *not* help (the skin group's warm
  window is not face skin) and costs approved colours; counting hair twice does.
  **V38e** (V37 + hair counted twice in the colour vote) scores **75 of 87** (V37:
  73) and visibly changes 34 of 599 characters — review page linked in §31.
- **V39 (§32–33):** the owner reviewed V38e (mostly positive). V39 reads the shade
  without the extra hair and counts only the character's own hair in multi-character
  images (shared "package deal" galleries count every face): **83 of 96** checks
  (V37 79).
- **V40–V43 (§34–40):** a pale-pink gate (Centurion), two rejected global rules
  (hair exempt from skin rules, V41; failed cut-outs kept, V42) and a recurring
  monochrome tint (Gon pale green). **V43 is the candidate** (83 of 96).
- **Final research (§41):** the one untried method with evidence is semantic —
  Danbooru's colour tags, locally via the WD tagger (378 MB, ~0.35 s per image),
  which names the wanted colour for most of the greens, hair identities and Audrey.
  Otherwise ship V43 with overrides.

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

---

## 23. The owner's review of V32, and V33 (2026-09-27)

### 23.1 The verdicts

- **Monochrome tone.** Himeno and Mei Mei were clear downgrades at near-black;
  V30's tinted greys suited them best. Akira Asai too dark. Osaragi fine either
  way, perhaps with the slightest tint. 2B and A2 suit white more than black, and
  are correctly given no tint.
- **Semiramis**'s lavender comes only from her main image's background; none of
  her gallery images has any.
- **Himiko Toga** should be nearer cream — browns likely push her toward a
  saturated brick red.
- **Gu Yue Fang Yuan** should not take the red: two images hold a lot of it,
  the rest none or next to none.
- **Nephis** and **Narumi Momose** are fine as they are.

### 23.2 V33

- **Tone.** Light-side characters (Will Auceptin, Sora Kasugano) stay near-white
  and neutral. Dark-side characters go back to V30's tinted mid tone: Himeno
  `#465664`, Mei Mei `#6f768d`, Akira Asai `#6e7890`, Osaragi `#23333f`, The Sandman
  `#1e313a`. **2B and A2 measure the same as Mei Mei and Himeno** — dark-dominant,
  57% cool lean, similar light share — so no rule gives them white without taking
  Mei Mei's tint away. White for them is an override.
- **Highlight must recur.** Ken Kaneki's red and Gu Yue's both come mostly from two
  images (93% and 98% of the total). The difference is the tail: Kaneki's red
  clears 1% coverage in 4 images, Gu Yue's in 2. The highlight now needs at least
  three. Gu Yue → blue-grey `#3e4c5b`; Kaneki keeps his red. Thin margin — one
  example each side.
- **Tie candidates must be real colours of the gallery** (saturated coverage ≥ 1%).
  Semiramis's lavender tie is gone; she becomes a warm grey-beige `#906f53`. No
  other tie changed (Reze, Nico Robin, Hiyuki, Sandrone, Artoria).

**Checks: 56 of 59** across all four review rounds (`PROFILE_REVIEW` added).
The three misses are known: 2B and A2 (override to white) and Himiko Toga.

### 23.3 Still open

- **Himiko Toga.** Her winning colour is the red-orange window (0.55) — skin and
  blood — and her cream is not even the runner-up (her uniform's blue, 0.22):
  cream is the pale warm yellow that §18.3 removed from the hue vote as "warm
  whites" to stop Will, Dazai and Poison Ivy going gold. Her cream and their gold
  are the same pixels.
- **2B and A2** — white via the override.
- **Frontend** — near-white, near-black and faintly tinted seeds under chroma
  0.025 need `themeFromSeed` to build a neutral theme (§22.3).

### 23.4 The full check

V33 on every library character with 4 or more gallery images — 599 characters,
9,113 images — in two review pages (4–9 images: 287; 10+: 312), each card showing
the main image, four gallery images, the accent and the colour on the site today
(`fullcheck.py`). About 16 minutes of computing on the owner's desktop (6 worker
processes × 4 onnxruntime threads), plus the downloads. Masks are now cached as
8-bit, a quarter of the earlier float cache.

Paths: 537 standard, 41 monochrome, 21 pale pink. 2 characters got no accent; 72
have no main image yet. 12 accents are near-neutral and need the frontend change
(§22.3) to show.

The owner accepted Eto's move from green to red: a red highlight against her
green theme still fits.

---

## 24. The owner's review of the full check (2026-09-27)

About 55 characters flagged across both pages (10+ and 4–9 images), traced with the
recorded reason for each (`.data/full/<name>.json`). The overall trend the owner
named: **green characters are commonly not represented correctly.** Themes, by how
many characters they explain:

### 24.1 The skin/orange window still wins (≈17)
The winning colour is a window centred at 18–38° HSV — skin, blush and brown
shading — which then aims or shades into brick red, orange or pale gold: Sharron,
Himiko Toga, Kim Soleum, Sukuna (an in-between "average"), Chizuru Ichinose,
Tetsurou Kuroo (dark red wanted), Aoi Todo (0.71 for that window; dark red wanted,
got pale gold), Izumi Miyamura, Han Sooyoung, Jiu Niangzi, Anya Forger (pink wanted,
got cream), Tooth Fairy, Loki, Makoto Kino, Maki Zenin, Roronoa Zoro, Tsubasa
Hanekawa. Damping the zone to ¼ (V20) was not enough, and presence pooling favours
it because skin is in every image.

### 24.2 Greens split by HSV geometry (≈11)
HSV spreads green over ~100° of hue and squeezes yellow and orange. Of the pixels
that are green perceptually (OKLCH hue 115–185°), HSV puts a large share under 100° —
the yellow-green band that borders blonde and skin: Maki 74%, Daiyousei 65%, N 57%,
Noriaki 53%, Daiyousei, Zoro 37%. Green therefore loses as thin slices, or wins a
window at 68–78° whose aim drifts to 48–52° (gold) and whose shade comes from pale
pixels: Nefer (very light green; darker wanted), Maomao, N, Noriaki, Green Lantern
(68% of his green is dark and votes at half weight → too light), Daiyousei, Sanae
Kochiya, Zoro, Jiu Niangzi, Maki, Gon. Green is not missing — it is 16–27% of the
character for most of them. Maki and Gon have only ~3% green on the cut-out.
Dark greens otherwise vote at about the same weight as mid greens, so "dark colours
are under-counted" explains Green Lantern but not the rest.

### 24.3 The main image's background decides (≈11)
The tie-breaker and the fallback read the **whole** main image, background
included (the owner's rule from §17, set for Reze), and now pick backgrounds or
colours the gallery barely has: Kyouka Jirou, Arceus (sky), Ellen Joe (turquoise
background via the fallback), Rio Futaba (pink only in the main image, via the
fallback), Noriaki Kakyoin, Suika Ibuki and Usagi Tsukino (purple barely in the
gallery), Alpha (pink that is not in the main image either), Sanae Kochiya,
Daiyousei, Shizuku Murasaki, Mai Sakurajima.

### 24.4 Nearly monochrome, but not below the line (≈9)
Characters mostly black and white with some colour stay on the standard path and
take a minor colour: Kim Dokja, Mai Sakurajima (red in 2 images), Han Sooyoung,
Sharron; Tsukatsuki Rio and Alucard take the monochrome path but miss their red
highlights; Gon Freecss goes monochrome white where green is wanted; Mahoraga could
be whiter. **Griffith and Cheongmyeong got no colour at all** — the coverage gate
declined and the fallback declined too, which breaks the owner's "never empty" rule.

### 24.5 The pale-pink gates (≈6)
False positives: Umbreon (black with yellow), Centurion — both small galleries where
"pale pink in ≥15% of images" is one image. False negatives: Anya Forger (pink hair
→ cream), Aemeath (pink → blue), and softer ones (Yae Miko pinker, Tsubasa Hanekawa,
Yuyuko Saigyouji).

### 24.6 Shade quality (≈6)
Airani Iofifteen too dark, Makoto Kino too light, Sukuna an average of red and
orange, Kim Soleum too orange, Gloria Martinez a pale yellow where a strong one is
wanted, Vertin blue (previously purple or muted teal).

Main images added since the run: Arthur Leywin, Centurion, Arisa, Tooth Fairy,
Green Lantern (refetched).

---

## 25. V34–V36: greens, the main image, highlights, never empty (2026-09-27)

The owner chose themes 2, 3 and 4 of §24.

**V34** did all three at once: every pixel binned by OKLCH hue (perceptually
even), a later dark fade, ties and the fallback read on the main image's cut-out
(whole image at ¼ weight), tie candidates present in ≥ 30% of gallery images, a
highlight that recurs (clear in ≥ 3 images, or 2 that are half the gallery — no
average-coverage test), and a never-empty safety net. It fixed eleven flagged
characters and broke ten approved ones: 59/80, no better than V33. The per-pixel
work was vectorised (numpy) along the way; a python/numpy comparison differs by
at most 0.5% of any cell (pixels rounding across a bin edge).

**Ablation** (turning each V34 change off in turn): the OKLCH switch was what
fixed the greens and several ties — and what broke the warm characters (Tohru,
Mirio, Panty, Poison Ivy, Miku, Artoria), whose tuning is all in HSV. The later
dark fade hurt Miku and Artoria and helped little. The cut-out main image helped
(Kyouka, Lynae). Presence changed nothing.

**V35** returned to HSV and targeted green directly: windows centred in HSV's
green family (75–170°) are ±45° wide instead of ±30°, and the aim inside one
cannot drift below 75° into blonde and gold. Greens and warm colours both held —
but the tie fixes OKLCH had supplied were lost, and Reze went magenta: with the
background removed, the main image's cut-out includes skin, and pale skin and
blush vote pink.

**V36**: when the main image breaks a tie or decides alone, the *choice* between
colours uses only its saturated colour (skin is mostly pale; hair and clothes are
not), while the *aim* inside the chosen colour reads the whole main image at full
weight (Reze's violet is her background). Presence counts pale colour too (Luka's
mint hair is pale; saturated-only presence had filtered it out).

**Checks: 69 of 80** (V33: 59). Fixed: Zoro, N, Noriaki, Sanae, Daiyousei (green),
Suika, Alpha, Usagi (her bow's red), Tsukatsuki Rio and Alucard (red highlight),
Griffith (a colour again). **The full 4+ run took under two minutes** — cut-outs
cached, measurement vectorised.

**Still open:** Maki Zenin (now a very dark teal, `#163948`), Nefer (a teal-green,
darker as asked but bluer), Maomao (still pale), Kyouka Jirou (her main image's
saturated colour is also pink), Shizuku Murasaki, Ellen Joe and Rio Futaba (the
main-image fallback still picks a background-like colour), Himiko Toga, 2B and A2
(override), and Nephis, who moved from the approved brown to a dark mauve.

---

## 26. The owner's review of V36 (2026-09-27)

Now fine: Maki Zenin (the dark teal is good), Aqua Hoshino (either colour),
Nefer (bluer than wanted, but a step in the right direction). Everything not
listed below was accepted.

| character | V33 → V36 | cause |
|---|---|---|
| Yotsuba Nakano | orange → yellow-green | the ±45° green window centred at 78° reaches back to 33° and swallows orange and blonde, then shades them chartreuse |
| David Martinez | yellow → yellow-green | same |
| Yuuki (SYMK) | white → wine red | the relaxed highlight rule: wine red clears 1% in 4 of 27 images |
| Kaine | white → blue | same: 4 of 34 images |
| Ruka Urushibara | teal → red | the tie presence rule: her teal is 75% of one image and absent from the other three |
| Xurkitree | blue → olive | the fallback now reads the main image's cut-out on saturated colour only |
| Nephis | brown → dark mauve | same |
| Jotaro Kujo | navy → cream | tie between his navy and the gallery's skin window; the main image's saturated colour is his gold chain and hat pin plus tan skin |
| Kyouka Jirou | pink (unchanged) | her main image's cut-out is correct; her hair (purple, the largest area) is dark and votes little, while the small bright red tie and pink headphones vote strongly |

Measurements behind the suggestions:
- **Highlight.** Mean coverage across *all* images: Tsukatsuki Rio 0.015, Kaneki
  0.044, Alucard 0.100 against Yuuki and Kaine 0.003 (both clear in 12–15% of
  images, Rio 21%, Kaneki 18%).
- **Ruka's tie.** Per-image share of colour near 192° (teal): 0.00, 0.00, 0.00,
  0.75; near 352° (red): 0.52, 0.40, 0.51, 0.23.
- **Main-image cut-outs** worked for both Kyouka (65% foreground) and Jotaro (32%).

Suggestions (§27 if taken): keep green's extra width on the cool side only; the
highlight must also average ≥ 1% across all images; the fallback goes back to
V33's whole-main-image read; tie votes from the main image weigh colours by area,
not saturation; and, as a judgement call, presence counts a colour that fills one
image of a very small gallery.

---

## 27. V37 (2026-09-27)

From §26's suggestions:

- **Green windows no longer reach into orange and yellow.** They count from 50°
  (yellow-green; blonde and orange sit below) instead of reaching back to ~33°,
  but the aim inside one still lands at 75° or above. A first cut floored the
  window at 75°/58° and lost Zoro, Sanae, Daiyousei and N again: **part of V36's
  green wins had come from the warm pixels its wide window swallowed**, and a
  character's green hair sits in HSV's yellow-green (60–100°). Sweeping the floor
  over the greens and the yellow/orange characters: 40° → 10/18, 45° → 13, 50° →
  14, 55° → 12; 45° recovers N but gives Yotsuba and David their green tint back.
- **A monochrome highlight must also average ≥ 1%** across all images: Yuuki and
  Kaine are white again; Rio, Kaneki and Alucard keep red.
- **The fallback reads the whole main image again** (Xurkitree, Nephis).
- **Tried and dropped: an area-weighted tie vote.** It turned Sanae and Daiyousei
  blue and Maki red, and did not help Jotaro (his main image's cut-out barely
  includes his coat, so gold wins by area too) or Kyouka (0.47 against 0.40).
- **Tried and dropped: one strong image counts in small galleries.** It brings
  Ruka's teal back but changes 13 of the 106 characters with ≤ 5 images, among
  them Gloria Martinez back to the pale yellow the owner rejected, and complete
  hue changes for Spider-Ham, Bambietta and Kaoruko.

**Checks: 73 of 87** (V36: 70), with this round's verdicts added (`V36_REVIEW`).
Fixed: Yotsuba (orange), David Martinez (yellow), Yuuki and Kaine (white), Nephis
(approved brown). 26 of 599 characters changed from V36; none is empty.

**Lost:** Maki Zenin and N. Maki's accepted dark teal in V36 came from the safety
net (her gallery was too sparse to decide); in V37 her gallery decides a near-coin
flip, red 0.15 against green 0.14. N's green window now centres at 68°, below the
green family, so its aim drifts to gold. Xurkitree came out teal-cyan in the full
run rather than the earlier blue.

**Still open:** Maki, N, Xurkitree, Ruka, Jotaro, Kyouka, Nefer (bluer, but
accepted as a step), Maomao, Shizuku, Ellen Joe, Rio Futaba, Himiko Toga, and 2B
and A2 (override).

---

## 28. Where the accent picker stands (2026-09-27)

The owner's review of V37: Xurkitree's teal-cyan is not right either, but not
important; N, Maki Zenin, Suwako Moriya and Audrey Hall regressed. **The green
trade-off:** V36's wide green window swallowed warm pixels, which turned N, Maki,
Suwako and Audrey greener — and Yotsuba and David Martinez green too. V37 stops the
swallowing; the first four go back, the last two are fixed. No floor tried gets all
six (§27).

**Jiu Niangzi**, rechecked with her newly added main image: still burnt orange
`#b14918` — the tie is orange (38°) against green (112°), and her main image's
saturated colour is 73% in the orange window.

**Flagged in the full-check review (§24) and never changed by V34–V37 — 37 of 53:**

- *Skin and warm tones outvote the real colour* — Sharron, Himiko Toga, Kim
  Soleum, Sukuna, Aoi Todo, Izumi Miyamura, Chizuru Ichinose, Tetsurou Kuroo, Jiu
  Niangzi, Anya Forger, Loki, Makoto Kino, Eiki Shiki, Tooth Fairy.
- *Pink identities* — Anya Forger, Aemeath, Tsubasa Hanekawa, Yae Miko, Yuyuko
  Saigyouji (missed or too red); Centurion and Umbreon (false pale-pink path — in a
  6–7 image gallery one image already passes the 15% presence test).
- *Nearly monochrome* — Kim Dokja, Mai Sakurajima, Han Sooyoung, Sharron, Gon
  Freecss (monochrome white where green is wanted), Mahoraga (could be whiter).
- *The main image's background decides* — Rio Futaba, Ellen Joe, Kyouka Jirou,
  Shizuku Murasaki.
- *Greens* — Maki Zenin, N, Maomao.
- *Shade and other* — Airani Iofifteen (too dark), Zeus (gold wanted), Vertin (blue;
  purple or muted teal wanted), Arthur Leywin (blue), Shouko Nishimiya (blue; her
  pinkish light-brown hair wanted).

Changed (16): Tsukatsuki Rio, Alucard (red highlights), Daiyousei, Zoro, Sanae,
Noriaki, Green Lantern, Nefer (greens), Alpha, Suika, Usagi (ties), Arceus (now
gold, as preferred), Gloria Martinez (now wine red, the owner's second choice),
Arisa, Griffith and Cheongmyeong (colours again).

### Suggestions

1. **A skin/body-part model** is the largest remaining lever: the first group (14)
   and parts of the pink and main-image groups are skin winning. Candidate:
   siyeong0/Anime-Face-Segmentation (hair / skin / clothes classes; faces only, so
   it needs a face crop from the cut-out). Prototype it offline against the review
   checks before anything ships.
2. **Pale-pink gate for small galleries**: require the pale pink in at least two
   images (Centurion, Umbreon). Cheap; test against the 106 small galleries first,
   as §27's small-gallery rule showed how easily they move.
3. **Use the manual override** for the stubborn remainder: 2B and A2 (white), Maki,
   N, Kyouka, Rio Futaba, Ellen Joe, Himiko Toga, Jotaro Kujo, Ruka Urushibara — about
   ten characters of 599. The override already exists and each pick is a label for
   future tuning.
4. **Before shipping**: port V37 into `accent_extract.py` (vectorised), store a small
   per-image colour summary and discard masks; run the one-off backfill on the
   desktop; segment new uploads once, in the background, on the server (1.7 GB peak
   RAM — check the instance); and let `themeFromSeed` accept near-neutral seeds so
   monochrome accents display.


---

## 29. Resume here — the final state (updated 2026-09-27, after §43)

**The work stopped at V43 by the owner's decision (§43).** Nothing has shipped: all
of this is lab work on the `accent-lab` branch (not pushed), and the live site still
runs the original `accent_extract.py`. Porting V43 into the app is the next step and
has not been started; its checklist is below.

**The candidate** is `v43(portrait, gallery, trace)` in
`scripts/accent_lab/methods.py`, also reachable as `candidate` / `method_candidate`.
It is a chain of switches on earlier versions (v43 → v40 → v39 → v38e → v37 → v36 →
… → v16), so a production port should be a clean rewrite of the *behaviour* below,
not a copy of the chain.

**What V43 does, in order:**
1. **Cut-out.** skytnt/anime-seg on each 600px thumbnail; the background is painted
   white. An image whose cut-out covers under 3% (the character was missed) or over
   85% (a scene it cannot separate) is dropped from the colour work.
2. **Face parsing.** An anime face detector (deepghs `face_detect_v1.4_n`) finds
   faces; a face parser (siyeong0 UNet) labels hair, face, skin, eyes, mouth and
   clothes on each face crop. **Own hair:** the character's hair colour is the median
   (Oklab) of their hair in images with exactly one face; in an image with several
   faces, only the face whose hair is nearest counts. **Package deal:** with fewer
   than 2 solo images, or solo images under 25% of the images with a face, every face
   counts (Popola/Devola, Sakurako/Kasumi). The own hair is counted **twice** in the
   colour vote.
3. **Profile** (read on the plain cut-out, without the extra hair): share of pixels
   with real colour, share of colour that is pink/red, share of that which is pale.
   - **Monochrome** (< 30% real colour) → a recurring saturated highlight if one
     clears 1% in ≥ 3 images (or 2 that are half the gallery) and averages ≥ 1%;
     otherwise, if one hue family other than skin/brown/orange appears in ≥ 85% of
     images (scenes read whole) and on the figure itself, it tints the tone (up to
     chroma 0.06; Gon's pale green); otherwise near-white or near-black with at most
     the greys' own slight lean.
   - **Pale pink** (≥ 70% pink/red, ≥ 10% of it pale, and real pale pink present:
     median coverage ≥ 0.8%, or in ≥ 15% of images *and* at least two) → the
     character's own lighter pinks (hue 320–355), most chromatic 35%.
4. **Standard path.** Pixels classified in HSV: skin 12–38 removed; pale skin 335–38
   removed (335–352 only up to S 0.25); warm zone 10–45 and skin shadow 355–10 damped
   to ¼; faint warm whites out of the hue vote. Hue evidence per image = saturated +
   ½ pale, normalised, square-root pooled. Colour windows ±30° (the green family
   75–170 counts from 50° with its aim ≥ 75°). Two colours within a 1.25 margin tie;
   the main image's cut-out *saturated* colour (whole image at ¼) breaks it and the
   whole main image aims it; tie candidates must hold ≥ 10% of the colour in ≥ 30% of
   images. The extra hair votes on the choice and the aim; **the shade reads the
   cut-out without it**: the vivid core blended 35% toward the brighter half; pale
   identities lifted to chroma 0.09.
5. **Fallbacks:** gallery too sparse → the whole main image → its dominant colour
   with no minimum → the gallery's monochrome tone. Never empty.

**Review verdicts** are executable checks in `scripts/accent_lab/lab.py`: `REVIEW`,
`SAMPLE_REVIEW`, `PROFILE_REVIEW`, `FULL_REVIEW`, `V36_REVIEW`, `V38_REVIEW` (and the
original `PANEL`). Score versions with `python -m scripts.accent_lab.checks v37,v43`;
explain a character with `python -m scripts.accent_lab.trace v43 "Name"`. Scores:
V33 59/80 → V37 73/87 → V39 83/96 → **V43 84/96** (83 before Jotaro's check took the
gold the owner accepted). The 12 failures are all on the open list below.

**Still open under V43** (grouped, with causes, in §34 and on the open-cases page):
the skin/warm group (Sharron, Himiko Toga, Kim Soleum, Sukuna, Aoi Todo, Chizuru,
Tetsurou Kuroo, Jiu Niangzi, Loki, Eiki Shiki, Tooth Fairy, Centurion); pinks
(Tsubasa, Yae Miko, Yuyuko, Umbreon); nearly monochrome (Kim Dokja, Mai Sakurajima,
Han Sooyoung, Mahoraga, 2B and A2 — white wanted); ties (Rio Futaba, Shizuku, Ruka);
greens (Maki Zenin, N, Maomao, Nefer); one-offs (Airani, Zeus, Vertin, Shouko
Nishimiya, Xurkitree, Omaru); Audrey Hall (lore). Why distinct hair loses: §36.
These are for the manual override.

**Tried and rejected after V37** (do not repeat without a new idea): removing face
skin (§31); letting parsed hair skip the skin rules (V41/V41b, §38); keeping failed
cut-outs at reduced weight (V42, §39); counting backgrounds (§37); the aim read
without the extra hair (V39p, loses Anya); the WD tagger as a tie-breaker (§41–42:
~4 fixes against 3–4 backfires, for a third model).

**Review pages** (private artifacts):
- Open cases under V40/V43, grouped by issue: https://claude.ai/artifact/JU9XM5YNbvCSQ39mZt6zsK
- V43 recurring tint (Gon, Neferpitou): https://claude.ai/artifact/NX5Mw9oVg2LE63MN57hr7Z
- V40 pale-pink gate (+ Jotaro): https://claude.ai/artifact/SS55GbUYFySLed16KhVwp9
- V39 own hair (beside V38e): https://claude.ai/artifact/1GY72otrTP7BDpRKczpqy3
- V38e hair trial (beside V37): https://claude.ai/artifact/1mRbXVm2iuf32oiKba1tYH
- Full check 10+ and 4–9 (V37 beside V36; older): https://claude.ai/artifact/4aDYwNwRtsQVFBeemppsUE,
  https://claude.ai/artifact/1eqMqdy4UtNYjpgJ9aSFZP
- Colour Profile Paths (V29/V32/V33): https://claude.ai/artifact/3DjpxNkjShtDUyAh68EBJY
- Accent Sample Check (V29 vs V24): https://claude.ai/artifact/3KiAqg1Znyes8hpcppSavf

**Lab data** (`scripts/accent_lab/.data/`, gitignored, all regenerable): `live/`
fetched characters; `masks/` cut-out cache (~6.5 GB); `faceparse/` face labels with
face indexes (~7 KB each); `isnetis.onnx` (176 MB); `skin/` the face detector,
face parser and SegFormer as ONNX, plus the WD tagger (`wd-vit.onnx`, 378 MB);
`full_vNN/` one JSON result per character per version (`full/` is V33);
`full_list.json` the 599 characters with 4+ images; `tagscan.json` the tagger's
colour tags for 119 characters; older scratch scripts from the rounds. Rebuild a
page with `fullcheck --method v43 --out full_v43 --compare full_v40
--compare-label V40 --min-change 0.08 --changed-only render`.

**Porting V43 into the app — checklist:**
1. Rewrite the behaviour above in `accent_extract.py`, vectorised (numpy), keeping
   the override's precedence. Models run through onnxruntime only (no torch): the
   cut-out (176 MB) and the face detector + parser (18 MB, converted with
   `skinbench export`).
2. Per image, store a small colour summary (the hue/shade grids, coverage, profile
   figures and the hair-labelled share) with the image row instead of masks; a
   character's accent is then a sum over its images — milliseconds.
3. Backfill on the desktop (cut-outs are cached for the 4+ characters; ~65 min for the
   whole library from scratch, face labels ~7 min).
4. On the server (4 ARM cores, 23 GB), process new uploads once, in one background
   process, never inside the web workers: ~1.9 GB peak with both models loaded, a few
   seconds per image (§42).
5. Frontend: let `themeFromSeed` accept near-neutral seeds (chroma < 0.025) so
   monochrome accents (2B, Kaine, Will) display instead of falling back to teal.
6. Carry the verdicts in `lab.py` over as regression tests, and apply the owner's
   overrides for the open list.

**The owner's standing rules** (also in the assistant's memory): the main image
breaks two-colour ties (choosing among the gallery's colours, never adding one);
never leave a character without an accent; vivid over dark or grey, except that
genuinely monochrome characters go black or white rather than a tinted grey; pale
skin is never a pink identity; pinks stay distinct; a character is measured from
their own features, except "package deals" whose images nearly always show the same
pair; judge by eye on contact sheets. Main images are Mudae links mirrored on R2, and
missing ones fill in as the site is used — not a bug.

---

## 30. Skin and body-part models: size and speed, measured (2026-09-27)

Research only; V37 unchanged. The goal was hard numbers for §28's first
suggestion. Tool: `scripts/accent_lab/skinbench.py` (models in `.data/skin/`,
commands in its docstring). All numbers are the owner's desktop (Ryzen 9 7900X),
onnxruntime on CPU, real 600px gallery thumbnails.

**Candidates**

| model | what it marks | licence | weights | status |
|---|---|---|---|---|
| [siyeong0/Anime-Face-Segmentation](https://github.com/siyeong0/Anime-Face-Segmentation) | background, hair, eye, mouth, face, skin, clothes — trained on face crops | MIT | `UNet.pth` 6.4 MB (1.55 M params); **6.2 MB as ONNX** | measured |
| [deepghs/anime_face_detection](https://huggingface.co/deepghs/anime_face_detection) `face_detect_v1.4_n` | face boxes (YOLOv8n, F1 0.94) — the crop the parser needs | MIT | **12.1 MB ONNX** | measured |
| [isjackwild/segformer-b0 skin-hair-clothing](https://huggingface.co/isjackwild/segformer-b0-finetuned-segments-skin-hair-clothing) | skin, hair, clothing — trained on **photos** | — | 15.0 MB ONNX (3.7 M params) | measured, rejected |
| [See-Through](https://github.com/shitagaki-lab/see-through) (SIGGRAPH 2026) | up to 23 anime body-part layers | Apache-2.0 | SDXL-based diffusion | rejected unmeasured: 12–16 GB GPU, 2–3 min per image (≈ 2 weeks of GPU for the library) |
| Anzhc YOLO face / head-hair seg | one-class face or head masks | AGPL-3.0 | ~6 MB | not tried: one class, and AGPL on a server |

The PyTorch models were converted to ONNX once (`skinbench export`), so running
them needs only onnxruntime — the same runtime the cut-out model uses; no torch
on the server.

**Speed** (ms per image, averaged over 40 thumbnails, 1.3 faces per image):

| step | 1 thread | 4 threads | all 24 threads |
|---|---|---|---|
| face detector | 71 | 56 | 76 |
| face parser, once per detected face | 116 | 61 | 111 |
| **face path total** | **≈ 190** | **≈ 120** | ≈ 190 |
| face parser on the whole image (for comparison) | 89 | 45 | 66 |
| SegFormer | 187 | 69 | 104 |
| cut-out model (isnetis), for comparison | **2,440** | **700** | ≈ 400 (§20.1) |

The small models run *slower* on all 24 threads (thread overhead outweighs the
work); 1–4 threads is the right setting, which suits the server. The face path
costs about **a sixth of the cut-out at 4 threads, a thirteenth at 1 thread**.

**Memory** (peak resident, each model alone, over the Python + onnxruntime
baseline of ~70 MB): face detector **+70 MB**, face parser **+200 MB** (together
≈ 270 MB), SegFormer +490 MB, cut-out model **+1,600 MB**. Thread count made no
difference.

**Whole library**: measured in §31 — the full 4+ run (599 characters, 8,506
images face-parsed from scratch, plus all colour measurement) took **6.5 minutes**
with 6 processes; about 2.5 minutes once labels are cached. Labels cache at about
7 KB per image compressed. Once per image, like the cut-out.

**The server** (Oracle Ampere A1, ARM Neoverse N1) is not measured — reads on the
production box need the owner's go-ahead. An N1 core is roughly 2–3× slower than
a Zen 4 core for this kind of work, which puts the face path at about 0.4–0.6 s
per image on one core (the cut-out: about 5–7 s), in ~300 MB of RAM. Running
`skinbench speed` there would replace the estimate with a measurement.

**What each model actually marks** (contact sheet of 54 images from the
skin-group characters, 3 each: `skinbench sheet` → `.data/skin/sheet.png`):

- **Face parser on face crops — good where it reaches.** Faces, hands in frame,
  hair and collars come out right, including the hard cases for colour rules:
  Himiko Toga's blonde hair is *hair* (the colour rules cannot separate it from
  skin), Eiki Shiki's green and Makoto Kino's brown hair are hair. But it covers
  **only the head and whatever falls in the crop** — arms, legs and torsos are not
  reached (Makoto's arms, Chizuru's legs, Jotaro's chest). Face skin is a median 6% of the
  cut-out in these images (quartiles 2–10%; up to 26% in close-ups).
- **The face detector** found a face in **48 of 54 images (89%)**. The misses are
  scenes where the face is not readable (Sukuna's three dark images — which the
  cut-out model also drops — one Aoi Todo, one Kim Soleum). Group shots give
  several faces (Kim Soleum: 5–6), all parsed.
- **Face parser on the whole image — unusable.** Outside a face crop it paints
  hair and clothes labels at random over bodies and backgrounds.
- **SegFormer — unusable.** Trained on photos, it calls nearly all anime pixels
  "clothing" and finds skin only on some faces and legs.
- **Extending skin from the face by colour** (learn this image's skin colour from
  the parsed face, mark matching pixels anywhere on the cut-out): **unreliable**.
  It catches bare legs and arms well in some images (Izumi Miyamura, Chizuru) but
  swallows anything skin-coloured: Himiko's blonde hair, Makoto's cream trousers,
  Jotaro's gold, and Tooth Fairy's and Reze's whole dark bodies (81–95% of the
  cut-out). As tried it is worse than the HSV skin rules V37 already has.

**What this means for §28's suggestion 1.** A face-crop parser is cheap — 18 MB
of models, ~270 MB RAM, ~0.12 s per image on the desktop — small enough to run
on the server beside the cut-out (which dominates at 1.6 GB and ~0.7 s). What it
buys is reliable **face skin removal** and, possibly more useful, a **hair
label**: hair is often the signature colour, and it is exactly where the colour
rules confuse blonde, pink and cream with skin. It does **not** solve body skin.
No small full-body anime parser was found; the only full-body one is a diffusion
model far too heavy to run here.

The unmeasured question is the one that matters: *does removing face skin, or
weighting hair, move the flagged characters?* That needs a prototype variant
(face/skin labels removed before measurement; optionally hair counted extra)
scored with `checks`, which is a method change and awaits the owner.

---

## 31. The skin trial: V38a–V38e (2026-09-27)

The owner asked for a trial of §30's face parser, scored. Labels are computed
once per image (`scripts/accent_lab/faceparse.py`, cached in `.data/faceparse/`)
and applied to the cut-out in `foreground_only` (switches `FACE_SKIN_OUT`,
`HAIR_BOOST`). Removed pixels are painted white, like background; extra hair is
appended as rows of hair pixels, so every later measurement sees it without
changes. V37 itself is untouched (checked: identical 73/87 and seeds).

| variant | what it does | checks (of 87) |
|---|---|---|
| V37 | — | 73 |
| V38a | face, skin and mouth labels removed | 68 |
| V38b | V38a + hair counted twice | 72 |
| V38c | hair counted twice, skin left in | 74 |
| V38d | hair counted three times, skin left in | 74 |
| **V38e** | V38c, but the colour profile reads the plain cut-out | **75** |

**A pitfall, fixed before these numbers.** V37 drops a gallery image as an
unseparable scene when the cut-out covers > 85% of the frame. Painting the face
white lowered that share, so close-ups V37 had dropped were suddenly counted
(with backgrounds the cut-out model had kept): Luka went mint → brown for that
reason alone. The scene test now reads the cut-out as V37 did, before face edits.

**Removing face skin does not fix the skin group.** Face skin is ~6% of the
cut-out, and ≥ 90% of it is hue 0–60° as expected (the parser does not mislabel
hair), yet all fourteen skin-group characters keep essentially the same colour
without it: **their winning warm window is not face skin** — it is body skin,
brown shading, warm clothes and lighting, which the parser does not reach. And
it costs approved colours: Superman's red was partly his own face in the
red-shadow zone (without it, blue ties and his main image picks blue); Alpha goes
pink; Nephis crosses into the monochrome path.

**Counting hair helps.** Hair is labelled reliably and is often the signature
colour. V38e's changes on the checks: **Kyouka Jirou → purple, Ellen Joe → red**,
nothing lost. Among flagged characters without a check: Anya Forger cream → pink
and Aemeath blue → pink (both wanted), Arthur Leywin blue → red (his hair),
Lelouch cream → purple, Mirio orange (wanted yellow/orange). Three times (V38d)
also fixes A2 (white), N and Rio Futaba but loses Nadeko, Usagi and Alpha —
too strong. V38c turned Nephis, Seidou, Crona and Alisa monochrome white (silver
hair counted twice pushes them under the 30% colour line); V38e fixes that by
letting only the colour vote see the extra hair.

**Unchanged by any variant:** the skin/warm group (Sharron, Himiko Toga, Kim
Soleum, Sukuna, Aoi Todo, Tetsurou Kuroo, Jiu Niangzi, Loki, Eiki Shiki, Tooth
Fairy), Maki Zenin, N, Maomao, Nefer, Shizuku, Rio Futaba, Ruka, Xurkitree, 2B and
A2. Jotaro Kujo got navy only in V38b (skin out + hair), not in V38e.

**V38e visibly changes 34 of 599 characters** (Oklab distance ≥ 0.08; 530 change
by an invisible hex step). Several are unreviewed and could go either way:
Izumi Miyamura cream → dark red, Aqua Hoshino blue → blonde (the owner accepted
either earlier), Tanya Degurechaff red → blonde, Suwako Moriya purple → khaki,
Jade (HSR) blue → lilac, Ibuki Mioda pink → blue, Osamu Dazai → wine.

**Review page** (V38e beside V37, changed characters only):
https://claude.ai/artifact/1mRbXVm2iuf32oiKba1tYH — rebuild with
`fullcheck --method v38e --out full_v38e --compare full_v37 --compare-label V37
--min-change 0.08 --changed-only render` (new options: `--min-change` in Oklab,
`--changed-only` for one page of changes).

**Cost, measured:** the full 4+ run with face parsing from scratch took 6.5
minutes (6 processes × 4 threads; 8,506 images labelled), 2.5 minutes with labels
cached. Labels are ~7 KB per image compressed. In production the hair-label
summary would be folded into each image's stored colour summary, like the cut-out.

**Open for the owner:** judge the 34 changes on the review page. If V38e holds,
it replaces V37 as the candidate; face-skin removal should be dropped.

---

## 32. The owner's review of V38e (2026-09-27)

Verdicts on the 34 changed characters, recorded as `V38_REVIEW` in `lab.py`
(V37 passes 6 of 12, V38e 8):

- **Much better / very good:** Kyouka Jirou, Aemeath, Jade (HSR), Ellen Joe, Anya
  Forger (the pink could be clearer; `#bc5b63` is a little muddy).
- **Either is fine:** Izumi Miyamura, Tanya Degurechaff (blonde hair vs blood red),
  Ibuki Mioda (blue or the old purple-pink; slight preference for the old).
- **Old preferred:** Panty Anarchy (strongly: the old vivid yellow, not the washed-out
  one), Lillie and Omaru Polka (the old paler yellow; nitpicks).
- **Daphnis et Chloé:** the old green is preferred. Her main image has since been
  added (refetched): with it, V37 and V38e both give brick red `#b15041` — a genuine
  tie between her red braids and green dress, and the main image votes red 0.61 to
  0.37. Under the tie rule that is the expected answer; green needs an exception or
  the override.
- Everything else on the page was accepted. Overall: a mostly positive change.

**Unchanged by V38e:** Audrey Hall (`#c5b459` → `#c7b559`), Reze (`#6e599f` →
`#6d589e`), Columbina (`#9aabe8` → `#9aaae7`). Columbina's hair *is* found (221 of
253 images, 19% of the cut-out), but what the parser labels as her hair is mixed:
~41% blue-violet and ~29% wine/magenta by hue. Doubling it raises both, so her
light blue (0.44) still beats wine (0.34).

**The three shade misses share one cause.** The hue choice is unchanged for Panty,
Lillie and Omaru; the *shade* moved because the shade step also sees the doubled
hair. Panty's pale blonde hair tipped her shade to the pale class (washed out);
Lillie's and Omaru's darker hair made theirs darker.

**Several characters in one image.** The face detector finds every face; the
parser labels each crop; all hair is counted, whoever's it is. Measured over the
9,092 gallery images of the 4+ characters: 9% no face, 78% one, **13% two or
more**; for 33 of 599 characters at least half the images have 2+ faces (Himiko
Toga 7 of 11, Izumi 4 of 5, Panty 58%, Sandrone 66%; Sakurako/Kasumi and
Popola/Devola 100% — shared or paired galleries). It measurably mixes in the
other character: Himiko's hair in her one-face images is ash-blonde (`#b19b89`,
`#d1b5aa`), in her pair images browner (`#875c49`, `#99594e`); Izumi's own hair is
near-black (`#313e45`) while his pair images' "hair" is Hori's brown (`#4a2c17`) —
his accepted dark red comes from her hair.

**Suggestions:**
1. **Shade from the plain cut-out** — the extra hair votes on *which colour*, not
   on *how light*. Targets Panty, Lillie and Omaru.
2. **Count only the character's own hair.** Cheapest: learn the character's hair
   colour from their one-face images (78% of all images) and, in images with
   several faces, boost only the face whose hair matches it. No new model; it
   cannot work where nearly every image is a pair (Popola/Devola), which then keep
   V37's behaviour. The principled alternative is deepghs's character-identity
   model (CCIP, openrail licence, **150 MB**): pick the face that matches the
   character across the gallery. Heavier — about the size of the cut-out model —
   so only if the cheap rule falls short.
3. **Daphnis**: override to green, or accept red under the tie rule.

---

## 33. V39: shade without the extra hair, own hair only (2026-09-27)

The owner accepted Daphnis et Chloé's red under the tie rule ("still characteristic
of her enough"; her check now accepts red or green), agreed to §32's suggestions,
and set a rule for shared galleries: **when nearly all of a character's images
feature the same partner, they are a "package deal" and both may contribute.**

**V39** is V38e plus two switches (`methods.py`, "V39"):

- **The shade reads the cut-out without the extra hair** (`SHADE_PLAIN`). Hair
  still decides which colour, and where inside it the aim lands.
- **Only the character's own hair counts** (`OWN_HAIR`). `faceparse.py` now also
  caches which face each labelled pixel belongs to (older cache entries are
  recomputed). A gallery pre-pass takes the median Oklab hair colour of each face;
  the character's hair colour is the median over images with exactly one face; in
  an image with several faces only the face whose hair is nearest (lightness at
  half weight) is boosted, main image included. **Package deal:** fewer than 2 solo
  images, or solo images under 25% of the images with a face → every face counts,
  as in V38e. 29 of 599 galleries qualify: Popola/Devola, Sakurako/Kasumi, Izumi
  Miyamura, Tadano Hitohito, Natsu Dragneel, and characters the face detector
  rarely finds (BMO, Doraemon, Pochita, Arceus…), for which nothing changes.

**Tried and kept as V39p: the aim without the extra hair too** (`AIM_PLAIN`). It
restores Omaru Polka's old paler yellow and turns Rio Futaba from pink to brick
red (`#ad5147`), but loses Anya Forger's pink: her winning window is the warm one
at ~20° in every version, and it is her hair that moves the aim inside it from
48° (skin/cream) to 358° (her pink hair). Omaru's hair moves hers from 48° to 42°,
where the saturated class decides the shade. Anya was "much better", Omaru a
nitpick, so V39 keeps hair in the aim.

**Checks: V39 83 of 96** (V38e 81, V37 79, V39p 84 — the set now includes
`V38_REVIEW`). V39 keeps every V38e gain the owner liked (Kyouka, Ellen Joe,
Aemeath, Jade, Anya, and the accepted "either" cases) and fixes Panty (vivid
`#e4b546`) and Lillie (`#fbe7a1`). Still off from this round: Omaru (`#d0af61`,
a nitpick). Himiko Toga is back to V37's `#a25348` exactly — her own hair is
ash-blonde and does not move the warm window. Lelouch changed again: V38e's
lilac became a dark purple-navy `#464789`.

**Visible changes against V37: 18 of 599** (V38e: 33). The 16 V38e changes V39
undid were shade-only, back to V37's lightness: Aki Hayakawa, Chun-li, Cola,
Edward Elric, Finn, Hitagi, Kogasa, Komi Shouko, Nightwing, Ritsu, Tadano,
Tsumugi, Zhezhi, Lillie, Panty, plus Lelouch's new shade.

**Review page** (V39 beside V38e, only what moved since the V38e page):
https://claude.ai/artifact/1GY72otrTP7BDpRKczpqy3

**Open for the owner:** that page; whether V39 replaces V37 as the candidate.
Unchanged by every variant so far: the skin/warm group, the greens (Maki, N,
Maomao, Nefer), Shizuku, Ruka, Xurkitree, Jotaro, 2B and A2.

---

## 34. Where it stands after V39 (2026-09-27)

The owner: V39's changes are "all changes in the right direction". **V39 is the
candidate** (83 of 96 checks), replacing V37.

**Fixed since §28's list** (flagged in the full-check review, now right or
accepted): Anya Forger, Aemeath, Kyouka Jirou, Ellen Joe (via hair), Arthur Leywin
(red, his hair), Izumi Miyamura and Tanya (either accepted), Daphnis et Chloé (red
accepted). Makoto Kino (now orange-red `#c7623a`) and Suwako Moriya (now khaki
`#a2975f`) changed on the V38e page without comment.

**Still open — every character the owner flagged that V39 has not fixed:**

| issue | characters | why |
|---|---|---|
| Skin and warm tones win | Sharron, Himiko Toga (cream wanted), Kim Soleum, Sukuna, Aoi Todo, Chizuru Ichinose, Tetsurou Kuroo (dark red wanted), Jiu Niangzi, Loki, Eiki Shiki, Tooth Fairy | body skin, brown shading, warm clothes and lighting in the ~20° window; the face parser only reaches the head, and removing face skin changed none of them (§31) |
| Pink identities | Tsubasa Hanekawa, Yae Miko, Yuyuko Saigyouji (missed or too red); Centurion, Umbreon (false pale-pink path) | pinks lose to or merge with the warm window; in 6–7 image galleries one image passes the 15% pale-pink presence test |
| Nearly monochrome | Kim Dokja, Mai Sakurajima, Han Sooyoung, Gon Freecss (green wanted, gets white), Mahoraga (whiter); 2B and A2 (white wanted) | just above the monochrome line, so a minor colour wins; 2B/A2 need white, which also needs the frontend to accept neutral seeds |
| Ties and the main image | Rio Futaba (pink), Shizuku Murasaki (blue), Jotaro Kujo (skin/gold; navy wanted), Ruka Urushibara (teal only in one of four images) | the main image's colour or presence rules decide against the owner; V39p fixes Rio, V38b (skin out) gave Jotaro navy |
| Greens | Maki Zenin, N, Maomao, Nefer | HSV splits green; no green window width gets all of them and Yotsuba/David Martinez (§27–28) |
| Shade and other | Airani Iofifteen (too dark), Zeus (gold wanted), Vertin (blue; purple or muted teal wanted), Shouko Nishimiya (her pinkish light-brown hair wanted), Xurkitree (blue wanted), Omaru Polka (paler, nitpick) | individual |
| Not solvable by pixels | Audrey Hall | green is lore; her art is gold by area (§ TL;DR) |

**Levers left:**
1. **Pale-pink gate for small galleries** (§28 suggestion 2, not yet built): require
   pale pink in at least two images. Centurion, Umbreon.
2. **Skin beyond the head** — the largest group, and no small full-body anime
   parser exists (§30). The one remaining idea is to learn each image's skin colour
   from the parsed *face* (reliable) and remove matching pixels elsewhere, while
   protecting parsed hair; §30's version of this over-grabbed (blonde hair, cream
   clothes, dark bodies), so it would need to be much stricter.
3. **The manual override** for the stubborn, individual ones — 2B, A2, the greens,
   Jotaro, Ruka, Rio, Shizuku, Xurkitree, Zeus, Vertin: about 15. Each pick is also a
   label for future tuning.
4. **Ship V39** (§28 suggestion 4): port to `accent_extract.py` with the two models
   (cut-out 176 MB + face 18 MB; ~1.9 GB peak RAM, dominated by the cut-out), per-image
   colour summaries instead of stored masks, a desktop backfill, background
   segmentation of new uploads on the server, and neutral seeds in the frontend.

---

## 35. V40: the pale-pink gate (2026-09-27)

The owner accepted gold for Jotaro Kujo (V39 gives a pale gold `#f4e29c`; shown
again on the page below for confirmation before his check is changed) and asked
for §34's lever 1.

**V40** = V39 with the presence route into the pale-pink path needing pale pink in
**at least two images** as well as ≥ 15% of them (`PP_MIN_IMAGE_COUNT`); the
coverage route (median ≥ 0.8%) is unchanged. Across all 599 characters it moves
exactly one: **Centurion**, pale pink `#be8594` → burnt orange `#ad592d`. Off the
pink path her standard path picks the warm window, her dark skin; gold (her
jewellery) or her black-and-white hair would suit better, so the gate trades one
wrong colour for the skin problem.

**Umbreon is not caught.** Most of her images are scenes the cut-out cannot
separate (moon, starry sky, window) and are dropped; of the four left, two show a
person with pale skin and a pink blanket. Pale pink is then 2% of the character
(median) and in 2 of 4 images, so she passes any "two images" rule and the
coverage route. It is the "pale skin is not pink" problem with someone else's skin.

**Fixed along the way:** V39 wrote its package-deal note as the first trace line,
which the review pages read as the path and reason, so those 29 cards showed the
wrong label (colours were unaffected). The note now comes last; `full_v39` was
recomputed.

`fullcheck render --also "Name|Name"` adds named characters to a
`--changed-only` page.

**Review page:** https://claude.ai/artifact/SS55GbUYFySLed16KhVwp9

**Open-cases page** (every flagged character V40 has not fixed, grouped by issue,
V40 beside V37, plus Jotaro, Makoto Kino and Suwako Moriya to confirm):
https://claude.ai/artifact/JU9XM5YNbvCSQ39mZt6zsK — for the owner to decide
whether to ship with overrides or keep tuning.

---

## 36. Why distinct hair loses (2026-09-27)

The owner picked eight characters whose hair colour is very distinct and asked why
it was not picked up: Shouko Nishimiya, Vertin, Airani Iofifteen, Rio Futaba, Ruka
Urushibara, Yuyuko Saigyouji, Eiki Shiki, Sharron; and Gon Freecss, green in every
image yet a plain white monochrome accent. Tool: `python -m scripts.accent_lab.hairwhy
"Name|Name"` replays V40's own classifier on the pixels the face parser calls hair.

**The main cause: the skin rules delete light, warm and pink hair.** They were
tuned before the parser existed, by colour alone, and parsed hair still goes
through them:

| character | hair (median HSV) | what V40's rules do to the hair | hair's share of the vote now → if hair skipped the skin rules |
|---|---|---|---|
| Shouko Nishimiya | pinkish light brown | **73% removed as pale skin** | 17% → **81%** (her pink-brown, 352–8°) |
| Rio Futaba | light olive-brown, h 32 s 0.14 | 55% removed as skin, 16% too grey | 9% → **51%** (light brown, 32°) |
| Sharron | blonde, h 26 s 0.25 | 31% damped to ¼ (warm zone), 34% removed as skin | 22% → 50% (22°, the window that already wins; the shade is the issue) |
| Airani Iofifteen | pale pink/cream | 55% removed as skin | 12% → 21% |
| Vertin | ash grey-blonde, h 70 s 0.13 | 33% too grey to vote, 23% removed as skin | 15% → 32% (warm grey-blonde, 32–38°) |

**Other causes:**
- **Ruka Urushibara** — her hair is a very dark teal-green (V 0.25): 39% too grey
  and 21% too dark to vote; the rest does vote teal (172–178°) but only 30% of the
  vote, against red in every image. Dark colour votes weakly by design (vivid over
  dark).
- **Yuyuko Saigyouji** — her pink hair does vote pink, but the parser finds only
  9% of the cut-out as hair (her hat and scenes cover it), 4% of the vote; her blue
  kimono dominates.
- **Eiki Shiki** — her green hair is counted, but only 4 of 5 images are usable and
  each image counts equally: one sepia artwork (57% gold) and one red-fire artwork
  vote whole, while her green-teal hair spreads over three hue bands in the other
  two. Gold wins on image count.
- **Gon Freecss** — 4 of his 7 images are forest scenes the cut-out cannot separate
  and are dropped; in the other 3 his green is dull (below the 0.15 saturation that
  counts as colour), so he is monochrome (colour share 0.11). The monochrome tint
  looks only at near-grey pixels and only asks whether they lean cool or warm: his
  lean cool 58%, which gives a tint of 0.003 — none. A highlight needs saturation
  ≥ 0.55; his green is not.

**Possible fixes (not built):**
1. **Parsed hair skips the skin rules and the warm damping** (own hair only). Targets
   Shouko, Rio, Airani, Vertin, Sharron's shade. Risk: it re-opens the gold drift
   (Will, Ishtar, Dazai, Poison Ivy) for blonde and brown-haired characters, and any
   skin the parser labels as hair would vote — the checks would show both.
2. **Monochrome tint from a recurring dull colour**: when one hue family recurs in
   most images, even below colour saturation, it sets the tint's hue and strength
   instead of the cool/warm lean of the greys. Targets Gon.
3. Ruka, Yuyuko and Eiki are gallery-shape problems (dark hair, hidden hair, a few
   single-colour artworks); the override is the realistic route.

---

## 37. The owner's idea: measure backgrounds too (2026-09-27, not built)

§36's suggestions are parked. The owner's idea: instead of discarding backgrounds,
measure them separately and let an overwhelming, non-white background colour lean
the result (Gon's forests; perhaps Audrey Hall). Probe (`python -m scripts.accent_lab.bgprobe`, using the
pipeline's own cut-out decisions; colour = S ≥ 0.12):

| character | images | background's top colours (mean share of background) | note |
|---|---|---|---|
| Gon Freecss | 7: **5 where the cut-out misses him**, 2 separated | green 16%, cyan 7%, yellow 7% | the green is there, but the real loss is that 5 of 7 images are thrown away |
| Audrey Hall | 28 (24 separated) | yellow 15%, orange 13%, green 12% | backgrounds are gold-lit like her; would push gold harder |
| Lynae | 96 (81 separated) | sky blue 16%, cyan 14% | sky blue is what made her wrong in §16 |
| Kyouka Jirou | 34 | orange 13%, pink 8% | against her purple |
| Eiki Shiki | 5 | orange 22% | reinforces the gold that already beats her green |
| Reze | 122 | red 11%, sky blue 11% | |
| Superman | 13 | orange 14%, red 10%, sky blue 10% | red agrees |

**Finding:** backgrounds are dominated by two generic families — warm light
(orange/yellow: sunsets, interiors, lamplight) and sky blue — whatever the
character. Counted directly they would strengthen exactly the errors the lab spent
most of its effort removing (gold drift, Lynae's sky blue), and Audrey's
backgrounds are gold too.

**A narrower form that fits the data:**
1. **Images where the cut-out cannot find the character** (under 3% foreground)
   or cannot separate it (over 85%) are measured whole at a reduced weight instead
   of dropped. This is where Gon's green is (5 of 7 images); Lynae has 15 such
   images, so the weight must stay low.
2. **The background may only reinforce a colour already on the character** (in a
   minimum share of separated images), never introduce one — the same rule as the
   main image's tie-break. Gon's green is on him in 1 of 2 separated images, so this
   alone would barely move him; (1) matters more.
Cost: nothing new — the background is the inverse of the mask already computed.
Canaries in the checks: Lynae, Kyouka, Eiki, and the gold-drift set (Will, Ishtar,
Dazai, Poison Ivy).

---

## 38. V41: parsed hair skips the skin rules — tried, rejected (2026-09-27)

The owner chose §36's fix 1 first. `HAIR_EXEMPT` passes each cut-out's own-hair
mask (including the boosted rows) to `classify_np` and the coverage pass.

| variant | what hair skips | checks (of 96) | visibly changed |
|---|---|---|---|
| V40 | — | 83 | — |
| V41 | skin-hue and pale-skin rules, warm damping, warm-white exclusion | **71** | 103 |
| V41b | only the pale-skin rule and skin-shadow damping, only at hue 335–12 (pink side) | **76** | 43 |

**V41** freed brown and blonde hair from the warm damping, and with hair counted
twice the warm window won almost everywhere: Saber and Jeanne d'Arc blue → gold,
Zoro green → red, Sandrone, Luka, Kyouka, Panty, Lillie, Tanya, Artoria and Dazai
(back to the gold the owner rejected) all broke; 103 characters turned tan, gold or
peach. The warm damping exists precisely because brown and blonde are everywhere.

**V41b** fixed the targets it could — Shouko Nishimiya (pink-brown `#cb938f`),
Airani Iofifteen (light pink `#f6aaac`), Rio Futaba (terracotta `#b26056`, no longer
pink) — but broke seven approved characters (Nephis, Shiki Ryougi, Narumi, Tohru,
Nagatoro, Luka, Usagi, David Martinez) and turned many others brick or dusty red
(Marin Kitagawa, Lucy Heartfilia, Alice, Twinkle Star). The parser's "hair"
includes the shaded edge where hair meets skin and warm-lit strands, which sit at
exactly the hues (350–12) the skin-shadow rule was written for; the brick-red
problem of §19 comes straight back.

**Conclusion:** the skin rules are doing necessary work even inside the parsed hair
region, so a global exemption does not work. Vertin was unmoved by either (her hair
is too grey to vote, not removed). Shouko, Airani and Rio are better handled by the
override, or by a per-character gate (exempt only when the character's own hair is
consistently a pink identity), which has not been tried. Code stays in `methods.py`
(`v41`, `v41b`) for the record; V40 remains the candidate.

---

## 39. V42: failed cut-outs kept at a reduced weight — tried, rejected (2026-09-27)

The narrow form of the owner's background idea (§37, point 1). Images where the
cut-out misses the character (< 3% foreground) or cannot separate the scene
(> 85%) are measured whole at `SCENE_WEIGHT` instead of dropped — in the colour
vote, the presence and coverage tests and the colour profile (weighted median),
but not in the monochrome tone, highlight or pale-pink seed.

| variant | weight | checks (of 96) | visibly changed |
|---|---|---|---|
| V40 | dropped | 83 | — |
| V42 | 0.25 | 78 | 50 |
| V42h | 0.5 | 77 | 70 |

**Gon does not move.** Of his 7 images, 3 separate (his figure: colour share 0.02,
0.09, 0.14) and 4 are forest scenes (0.52–0.83 colour, 24–43% green). Even at 0.5
the scenes weigh 2 against the separated images' 3, so the weighted median stays at
0.14 — monochrome. It would take a weight above 0.75, more background than is safe.
His figure genuinely is nearly colourless; the green is his surroundings.

**Everyone else moves a lot.** Whole scenes bring their backgrounds into the vote:
Luka, Nadeko, Zoro, David Martinez and Jade (HSR) break at both weights; Jotaro
turns violet (his Stand), Tanya and Aoi Todo red, Suwako back to purple, Hina
Kagiyama teal → red. A few land where the owner wanted them — Zeus gold, Xurkitree
blue and Maki Zenin dark teal at 0.5 — but by accident of background, not reliably.

**Conclusion:** rejected; V40 stays the candidate. For Gon specifically, §36's fix 2
(a monochrome tint from a colour that recurs across images) could now read the
scene images for its hue without them voting in the standard path — the only
remaining non-override route, and a narrow one. `v42`/`v42h` stay in `methods.py`.

---

## 40. V43: a monochrome tint from a recurring colour (2026-09-27)

§36's fix 2, now able to read scene images. V43 runs V40 unchanged; only when the
result is a monochrome accent without a highlight does it look for one hue family
(30° HSV bands, hue > 50 so skin, brown and orange never count) present at ≥ 2% of
the pixels in **≥ 85% of images** — read on the cut-out where it separates, on the
whole image where it does not — and also on the character in at least one cut-out.
That family's chroma-weighted OKLCH hue becomes the tint, strength rising from 80%
presence to full (chroma 0.06) at 100%, keeping the side (white or black tone).

At a first bar of 60%, Kaine, Yuuki, Allen Walker and Shirakami Fubuki (colours in
67–75% of images) took faint blue or lilac tints — Kaine's white was approved, so
the bar was raised. At 85% **only two characters change across all 599**:

- **Gon Freecss** — white `#e8e8e8` → pale green `#dcf1c7` (green in 100% of
  images).
- **Neferpitou** — dark-side grey-violet `#78718f` → dusty rose `#96686d` (a red
  family in 100% of images). Not reviewed before.

Checks unchanged: 83 of 96. **Review page:** https://claude.ai/artifact/NX5Mw9oVg2LE63MN57hr7Z
If both are accepted, V43 replaces V40 as the candidate.

The owner accepted both ("it seems good"): **V43 is the candidate** (83 of 96 checks;
differs from V40 only on Gon Freecss and Neferpitou).

---

## 41. Final check: other methods, researched (2026-09-27)

The owner asked for a careful read of this document and an online search for
methods others use, to decide whether to stop here.

**Already covered by the lab** (in some form, with results above):
- **Palette extraction by clustering** (k-means, median cut, colour-thief,
  Android's Palette / node-vibrant "vibrant swatch") — these answer *dominant*
  colour, the same question as the pooled histogram; Material Color Utilities'
  quantiser + `Score`, the most refined of them, was tried and failed (§14.4).
- **Saliency / subject masks** — superseded by the anime cut-out model (§16).
- **Body-part parsing** — the face parser (§30–33); no small full-body anime parser
  exists; See-Through (SIGGRAPH 2026) is diffusion-based, 2–3 min per image on a GPU.
- **Training a colour predictor** — rejected early for lack of labels (§11).
- Research on anime colour (reference-based colourisation, colour design sheets)
  solves a different problem: filling line art, not naming a character's colour.

**Not tried — a semantic signal.** Everything above measures pixels, and §7's
first reason this is hard is that *dominant is not signature*. There is one source
that names signature colours directly: **Danbooru's tag vocabulary** (`green_hair`,
`blonde_hair`, `green_dress`, `red_eyes`…), which fans apply by meaning, not by
pixels.

- **Danbooru related tags** (public API): `audrey_hall` → blonde_hair 0.84,
  green_eyes 0.60, **green_dress 0.53**; `gon_freecss` → black_hair 0.50,
  green_shorts 0.22, green_jacket 0.18 (and white_hair 0.43 — Killua, from pair
  art); `reze_(chainsaw_man)` → purple_hair 0.40. Needs a name → tag mapping, suffers
  from co-occurring characters, and misses originals and memes.
- **The WD tagger** (SmilingWolf, Apache-2.0; trained on Danbooru) tags each image
  locally with the same vocabulary — no name mapping, covers every image.
  `wd-vit-tagger-v3`: **378 MB**, **~700 MB** extra RAM, **0.35 s per image at 4
  threads** (1.3 s at 1 thread) on the desktop; ~55 min for the library on 4 threads.
  Other sizes: moat-v2 326 MB, convnext-v3 395 MB, swinv2-v3 468 MB, eva02-large
  1.26 GB.

**Probe** (`scripts/accent_lab/tagprobe.py`, colour tags at ≥ 0.35, share of each gallery's
images): the tagger names the colour the owner wanted for many of the cases pixels
cannot solve — **Maki Zenin green_hair 46%, N green_hair 100%, Maomao green_hair
61%, Nefer green_hair 100%, Eiki Shiki green_hair 100%, Gon green_shorts 71%,
Himiko Toga blonde_hair 100% (cream), Sharron blonde_hair 100%, Yae Miko and
Yuyuko pink_hair 100%, Airani pink_hair 83%, Shouko brown_hair 75% + pink_hair 25%,
2B white_hair 100%**, and **Audrey Hall green_dress 75%, green_eyes 64%** (beside
blonde_hair 86%). It disagrees with the owner where the wish is not the hair:
**Lynae blonde_hair 95%** (her teal is accessories), Ruka black_hair (teal wanted),
Vertin grey_hair, Tsubasa black_hair; and it says little for non-humans (Xurkitree,
Umbreon). The skin-group characters with black hair (Aoi Todo, Tetsurou Kuroo, Kim
Soleum, Shizuku, Kim Dokja, Mai) come back mostly `black_*`: nearly monochrome, as
the owner saw.

**How it would be used, if built:** as a semantic prior, never the decider — the
tags name which of the gallery's *own* colour windows is the character's (hair, then
a prominent clothing colour, then eyes), in the spirit of the main image's
tie-break; the pixels still decide the shade, and a clear gallery winner (Lynae) is
not overturned. Store a few tag ids per image; tag new uploads in the background.

**Verdict:** this is the only untried method with evidence behind it, and it targets
the largest remaining failure (the semantic gap: greens, hair identities, Audrey).
It is a larger step than the variants of §31–43 — a third model and a new decision
input — and it would not fix Lynae or Ruka, whose wanted colours are not their hair.
Otherwise the pixel approach has reached its limit (§38–39): ship V43 and use the
override for the rest.

---

## 42. How much the tagger would help, and what it costs (2026-09-27)

**Simulation** (`python -m scripts.accent_lab.tagsim scan`, then `simulate`): the WD tagger on all 119
characters with a verdict or on the open list (≤ 20 images each); V43's own candidate
windows; the tag may only choose among them (≥ 0.4× the winner's strength), never
add a colour. Only distinctive tags count: hair colours other than black, white,
grey, brown and blonde (at ≥ 40% of images), else a clothing colour at ≥ 60%. A
first version that let blonde and brown hair choose backfired on Lynae, Saber,
Aurore Lee and Sandrone (identity in clothes or effects, not hair) — excluded.

| outcome | characters |
|---|---|
| **Fixes** | Eiki Shiki → green, Yuyuko → pink, Maki Zenin → green, N (aim held in green instead of gold) |
| Small nudges the right way | Yae Miko, Tsubasa Hanekawa (pinker, same window) |
| **Backfires** | Noriaki Kakyoin green → red (red hair 80%), Omaru Polka yellow → pink (pink hair 90%), Suwako Moriya khaki → red (red clothing), Jade (HSR) lilac → purple (minor) |
| Already agrees (29) | e.g. Miku, Madoka, Zero Two, Reze, Zoro, Sanae, Nefer, Maomao, Ellen Joe, Aemeath, Airani |
| Untouched (79) | everyone with black / white / grey / brown / blonde hair and no strong clothing colour — the whole skin/warm group, the near-monochrome group, Lynae, Ruka, Vertin, Shouko, Rio, Kyouka, Himiko; Audrey Hall's green is tagged (85%) but her green window is 0.399× the gold one, just under the bar |

About 4 fixes and 2 nudges against 3–4 backfires; ~9% of the sampled characters
would change. The tagger helps where a character has a distinctive hair colour the
pixels lose; it cannot help where the identity is black, blonde or brown hair, and
it backfires where the identity is not the hair.

**Costs, in context.** Server (`docs/ROADMAP.md`): Oracle Always Free, 4 ARM cores,
**23 GB RAM**, 43 GB disk free. Resident today: two gunicorn gthread workers (~70 MB
each idle, measured locally; a few hundred MB each while processing uploads), the
Mudae service (~55 MB), cloudflared and Litestream (tens of MB each, typical), and
the OS (~0.5 GB) — roughly **1–2 GB in use**, ~21 GB free. The accent models, run
once per new image in one background process (never inside the web workers, which
would load them twice):

| model | disk | RAM while running | desktop, 4 threads | desktop, 1 thread |
|---|---|---|---|---|
| cut-out (isnetis) | 176 MB | 1.6 GB | 0.70 s | 2.44 s |
| face detector + parser | 18 MB | 0.27 GB | 0.12 s | 0.19 s |
| **WD tagger (vit-v3)** | **378 MB** | **0.7 GB** | **0.35 s** | **1.28 s** |
| total | 572 MB (1.3% of free disk) | **2.6 GB all loaded** (11% of RAM) or 1.7 GB loading one at a time; with the rest of the server ~4–4.5 GB of 23 | **~1.2 s per image** | ~3.9 s |

The tagger is 30% of the per-image time and a quarter of the memory. On the ARM
server (not measured; an N1 core is roughly 2–3× slower than a Zen 4 core for this
work), a new upload would take about 3 s of background work on 4 cores, or 5–8 s
on 2 cores leaving the other two to the site, once per image; the character's
accent is then a sum of stored per-image results (milliseconds). The one-off
backfill runs on the desktop: tagging 9,440 images ≈ 35 min in one process (8
threads, measured 0.22 s per image), ~15 min split three ways; cut-outs are cached
for the 4+ characters (65 min from scratch) and face labels take ~7 min.

**Verdict:** affordable, but a poor trade on its own — a third model and ~30% more
work per image for roughly four fixes against three backfires. Recorded as the one
untried semantic lever; not recommended over shipping V43 with overrides.

---

## 43. Stopped at V43 (2026-09-27)

After §42 the owner agreed that the pixel approach had reached its limit and that the
tagger was not worth a third model: **the lab work stops at V43.** The last three
broad rules (V41, V41b, V42) each fixed a few characters and broke more approved
ones; what remains is individual, which is what the manual override is for.

**State of the branch** (`accent-lab`, not pushed; nothing in the app changed):
- `scripts/accent_lab/` holds every variant (`methods.py`, `candidate` = V43), the
  owner's verdicts as executable checks (`lab.py`), and the tools behind every number
  in this document, each runnable from the repo root (README).
- Jotaro Kujo's check now accepts the pale gold the owner accepted, so V43 scores
  84 of 96; the 12 remaining failures are all on §29's open list.
- The live extractor (`accent_extract.py`) and its tests are untouched: against
  `critique-fixes-v2`, which `accent-lab` was branched from, the lab only *adds*
  files under `scripts/accent_lab/` plus this document. `critique-fixes-v2` is not
  in `main` yet, so it merges first (or the lab commits are rebased onto `main`).
- CI's checks pass (`ruff check .`, `pytest`: 802 passed). Pyright reports type
  noise in the lab (numpy/onnxruntime are deliberately not project dependencies;
  older Pillow constant names); CI does not run it.

**Next, when the owner chooses:** port V43 into the app (§29's checklist), then apply
overrides to the open list. The lab stays as the reference and regression bench for
that port.

