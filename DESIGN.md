---
name: ImgManager
description: Custom character images for Mudae — organised, deduplicated, and ready to paste.
colors:
  deep-harbour-teal: "#0b7285"
  deep-harbour-teal-hover: "#095c6b"
  deep-harbour-teal-subtle: "#e3f2f5"
  cool-slate-50: "#f8f9fb"
  cool-slate-100: "#f1f3f6"
  cool-slate-150: "#e8ebf0"
  cool-slate-200: "#dde1e8"
  cool-slate-300: "#c8cdd7"
  cool-slate-400: "#a2aab8"
  cool-slate-500: "#7c8595"
  cool-slate-600: "#5c6575"
  cool-slate-700: "#444c5a"
  cool-slate-800: "#2e3440"
  cool-slate-850: "#222732"
  cool-slate-900: "#1a1e26"
  cool-slate-950: "#14171d"
  ground: "#f5f7f9"
  surface: "#ffffff"
  hairline: "#e2e6ec"
  ink: "#1c2029"
  affirm-green: "#0f7a3d"
  refuse-red: "#b3261e"
  caution-amber: "#8a5a00"
typography:
  display:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.875rem, 4.5vw, 2.5rem)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.022em"
  headline:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.5rem, 3.2vw, 1.875rem)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.0625rem, 2vw, 1.25rem)"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0"
  label:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0"
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
  pill: "999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
  10: "40px"
  12: "48px"
  16: "64px"
components:
  button-primary:
    backgroundColor: "{colors.deep-harbour-teal}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.deep-harbour-teal-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
    typography: "{typography.label}"
  button-secondary-hover:
    backgroundColor: "{colors.cool-slate-100}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.cool-slate-600}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
  button-sm:
    height: "28px"
    padding: "0 8px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "24px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
    typography: "{typography.label}"
  badge:
    backgroundColor: "{colors.cool-slate-100}"
    textColor: "{colors.cool-slate-600}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
    typography: "{typography.label}"
  segmented:
    backgroundColor: "{colors.cool-slate-100}"
    rounded: "{rounded.pill}"
    padding: "2px"
---

# Design System: ImgManager

## Overview

**Creative North Star: "The Contact Sheet"**

A photographer's contact sheet is a dense, ordered grid of real images with almost no
chrome around it, made for someone doing a job rather than someone browsing. That is
what this interface is. The character artwork is the content, the content is
photographic, and every decision about the frame exists to keep the frame out of the
way.

The register is a dense, restrained tool — Linear and Vercel rather than a consumer
product. Surfaces are white or near-black, separated by hairlines rather than shadows.
Neutrals are tinted toward blue (hue ~222) and never pure grey, because untinted grey is
the most reliable signal that no palette was chosen at all. Type is Geist, self-hosted,
with negative tracking on anything large — that tracking is most of what separates a
considered heading from a default one. Light and dark are equally first-class, derived
from one token set, following the system preference unless the visitor overrides it.

The one thing this system refuses to do is compete with the pictures. Chrome is grey;
artwork is not. That single constraint produces most of the rest: the hairline borders,
the two-shadow elevation vocabulary, the accent that appears only to mark state, and the
justified gallery rows that let images sit edge to edge at a common height without
cropping. Confirmed rejections, all of them visible as decisions in the source: Bootstrap
defaults (`#007bff` and its family), the purple-to-violet gradient cliché, untinted
greys, and bounce or elastic easing.

**Key Characteristics:**

- Hairline separation; shadows only for things that genuinely float
- Cool-tinted neutrals, never pure grey
- One accent, used only to mark state
- Images at their true aspect ratio, in justified rows
- Equal-weight light and dark, following the system by default
- 4px spacing base, 34px controls, 44px touch targets

## Colors

A near-monochrome cool-slate field with a single teal accent, tuned so the character
artwork is the only saturated thing on screen.

### Primary

- **Deep Harbour Teal** (`#0b7285` light / `#2fb3c4` dark): The only accent in the
  system. It marks state and nothing else — focus rings, the selected segment, the active
  profile tab, a pressed toolbar mode, and at most one solid button per screen. It was
  chosen specifically to sit away from Bootstrap blue and away from the purple/violet
  gradient that marks generated interfaces.

### Neutral

- **Cool Slate** (`#f8f9fb` → `#14171d`, thirteen steps): The entire structural palette.
  Tinted toward blue at roughly hue 222 so that greys read as chosen. Light mode takes
  its ground from the pale end (`#f5f7f9`) with white cards; dark mode inverts to the
  deep end (`#14171d` ground, `#1a1e26` cards) rather than dimming the light palette.
- **Ink** (`#1c2029` light / `#e6e9ef` dark): Body and heading text.
- **Hairline** (`#e2e6ec` light / `#2b313d` dark): The default separator for the whole
  system, in place of a shadow.

### Tertiary — status

- **Affirm Green** (`#0f7a3d` light / `#48c07a` dark): Success toasts, a saved state.
- **Refuse Red** (`#b3261e` light / `#f2857a` dark): Destructive actions and errors.
- **Caution Amber** (`#8a5a00` light / `#e0b341` dark): The one warning surface — the
  cookie-identity notice on the profile.

Each status colour has a `-subtle` tint for use as a background. The foreground on a
subtle tint is always the status colour itself, never the `-fg` token: `-fg` is designed
for the *solid* fill, and pairing it with the tint produces white-on-near-white.

### Named Rules

**The Art Carries the Colour Rule.** The accent marks state and nothing else: focus,
selection, the active tab, at most one solid button per screen. No coloured headers, no
gradient surfaces, no tinted cards. The character artwork is the only saturated thing on
screen.

**The Tinted Neutral Rule.** No pure grey anywhere. Every neutral carries the ~222 hue
cast. A `#888` in a diff is a bug.

**The Subtle-Tint Pairing Rule.** `--accent-subtle` takes `--accent` as its foreground;
`--accent-fg` belongs only on solid `--accent`. The same holds for success, danger and
warning. A test enforces this, because the failure mode is invisible text rather than a
crash.

## Typography

**Display Font:** Geist Variable (self-hosted, `font-display: swap`)
**Body Font:** Geist Variable
**Label/Mono Font:** system monospace stack, used only for command output

**Character:** One family across the whole system, carrying its weight range from 100 to
900 in a single variable file. Geist is a neutral grotesque with true tabular figures —
which matters here, because counts sit next to each other in every list and must not
reflow as they change.

### Hierarchy

- **Display** (700, `clamp(1.875rem, 4.5vw, 2.5rem)`, 1.25, tracking −0.022em): The
  character name on a character page. One per page.
- **Headline** (700, `clamp(1.5rem, 3.2vw, 1.875rem)`, 1.25, tracking −0.015em): The page
  title. Exactly one `<h1>` per page.
- **Title** (600, `clamp(1.0625rem, 2vw, 1.25rem)`, 1.25, tracking −0.015em): Section
  headings within a page.
- **Body** (400, 1rem, 1.6): Prose. Capped at 42rem for subtitles so lines stay readable.
- **Label** (500, 0.875rem, 1.5): Controls, table meta, list subtitles. The most common
  size in the system — this is a dense tool, and most text in it is a label.
- **Micro** (400, 0.8125rem): Hints, counts, captions under images.

Six sizes, and no seventh. `font-size` on an element whose content is a single drawn
glyph — the lightbox's `×` and arrows, a disclosure caret, the check inside a selection
disc — is sizing a shape rather than setting type, the same exemption circles have from
the radius scale.

### Named Rules

**The Negative Tracking Rule.** Anything at title size or larger gets negative letter
spacing (−0.015em, −0.022em at display). Default tracking on large type is the single
clearest tell of an unconsidered heading.

**The Tabular Figures Rule.** Any number that updates in place — counts, totals,
rankings, page numbers — carries `font-variant-numeric: tabular-nums`. Numbers that
reflow as they change read as broken.

## Layout

A single centred container at 1400px maximum, with 20px side padding collapsing to 12px
below 768px. The character page's action bar shares that measure and the card's own
padding, so the bar's contents line up with the gallery above rather than sitting inside
it. Spacing is a strict 4px base (4, 8, 12, 16, 20, 24, 32, 40, 48, 64); no
value outside the scale appears in the system.

Controls are 34px tall by default and 28px in their small variant. Anything in the navbar
takes a 44px minimum instead, because those are the most-tapped targets on a phone.

Only four breakpoints exist, and they are documented rather than declared because media
queries cannot read custom properties: **480px** (small phone), **768/769px** (phone to
tablet), **960px** (the navbar wraps to two rows), **1200px** (nav labels collapse to
icons). The stylesheet previously mixed nine unnamed values in both directions.

Image grids are justified rows, not a fixed grid: each item's `flex-basis` and `flex-grow`
are both proportional to its aspect ratio, so a row ends flush at one height with nothing
cropped. Invisible zero-height fillers absorb the leftover space on the final row,
without which `flex-grow` stretches a lone trailing item across the full width. Cards in
these rows opt out of `border-box` so the basis describes the image rather than the image
plus its padding — under `border-box` a row of mixed shapes lands up to 26px apart in
height.

Character portraits are a fixed 9:14 (`--main-image-ratio: 0.643`). Every one of the
1,000 stored portraits is exactly 225×350, so anything a different shape arrived from
elsewhere and is cropped to match rather than allowed to make a grid ragged. On a
character page the portrait is capped by height rather than width, because that is the
dimension that binds on a 9:14 image — 168px, dropping to 132px below 768px. It
identifies the character; it is not the content. Custom
images are whatever shape they were drawn in, and the layout adapts to them rather than
the other way round. The single exception is a degenerate shape: ratios are clamped to
0.4–2.5, because a 10:1 banner flattens its entire row to a sliver and a 1:10 strip makes
one absurdly tall. Those two extremes pay a small crop so that every other image in the
row keeps its proportions.

### Named Rules

**The Four Breakpoints Rule.** 480, 768, 960, 1200 (and 769 as the min-width complement
of the phone boundary). A fifth value in a media query is a bug, not a refinement — and a
test fails on one.

## Elevation & Depth

This system is flat by default and separates with line, not shadow. A hairline border is
the standard divider; surfaces sit on the page rather than above it. Depth comes from
tonal layering instead — `--surface-sunken` for recessed wells, `--surface` for cards,
`--surface-raised` for the one tier above.

Exactly two shadows exist, and they are reserved for things that genuinely float. The
previous stylesheet had six ad-hoc `rgba()` literals doing this job, which is how a system
loses its depth vocabulary.

### Shadow Vocabulary

- **`--shadow-sm`** (`0 1px 2px rgb(16 20 28 / 0.06)`): A single hairline lift, for
  small things that float one step off the page without claiming the overlay layer —
  toasts, the autocomplete dropdown, the reorder drag badge, and the selected chip
  inside the segmented control.
- **`--shadow-overlay`** (`0 16px 48px -12px rgb(16 20 28 / 0.24)`): Modals and dialogs
  only. The thing it says is "this is in front of the page", and nothing else should say
  that.
- **`--scrim`** (`rgb(16 20 28 / 0.55)`): The backdrop behind a modal.
- **`--ring`** (`0 0 0 3px` of the focus colour at 30%): Not an elevation. A focus
  or active ring, drawn with `box-shadow` because an `outline` cannot be tinted —
  used on the reorder drop target and the segmented control. It is listed here
  because it is a `box-shadow` value and would otherwise look like a third
  elevation to anyone counting.

Dark mode deepens all three rather than reusing the light values, because a shadow tuned
for white ground disappears on near-black.

### Named Rules

**The Line Not Shadow Rule.** The default separator is a 1px border. Reach for a shadow
only when the element genuinely floats above the page — and then use one of the two that
exist rather than inventing a third. `--ring` is not an exception to this: it is a focus
affordance that happens to be drawn with `box-shadow`.

These are enforced by `frontend/src/styles/tokenPairs.test.js`, not merely asserted here.
The rules in this document were false for a while — nine breakpoints against a stated four,
nine radii against a stated four — and a design document whose rules are already broken
teaches the next reader that the rules are decorative.

## Shapes

Four radii and no more: **4px** (`sm`) for small inline things — badges, thumbnails,
focus rings; **6px** (`md`) as the workhorse for buttons, inputs and selects; **10px**
(`lg`) for cards and modals; and **999px** (`pill`) for the search field, segmented
controls and the round icon buttons in the navbar.

Every radius is written as a token, never a literal; a test enforces it. The one shape
outside the scale is `50%`, used for genuinely circular controls — a circle is a shape
rather than a step on the scale.

The form language is rectangular and quiet. Corners are softened just enough to read as
deliberate, never enough to read as friendly. The radius steps up with the size of the
surface, so a badge inside a card inside a modal shows three distinct but related
roundings.

The one place the system becomes explicitly circular is the navbar: 22px radius on pill
controls and a 44px touch height, which reads as a separate band of chrome sitting above
the flat document.

## Components

### Buttons

- **Character:** Refined and restrained. Nothing announces itself.
- **Shape:** Gently rounded (6px), or fully pill when `round`.
- **Size:** 34px tall, 12px horizontal padding, label type at 500 weight. The small
  variant is 28px with 8px padding and micro type.
- **Primary:** Solid Deep Harbour Teal with white text. **One per screen at most** — it
  is the single thing on a page allowed to be a coloured shape.
- **Secondary:** The workhorse. Surface background with a `--border-strong` hairline
  outline, hovering to `--surface-hover`. Most buttons in the app are this.
- **Ghost:** No border, muted text, background appearing only on hover.
- **Danger / Success:** Solid status fills, used for destructive confirmation and for a
  destructive verb standing among ordinary ones, such as Remove in a selection.
- **Pressed** (`aria-pressed="true"`): Subtle accent tint, accent border, accent text —
  how an active gallery mode reads.
- **Loading:** A 12px spinner replaces nothing; it sits alongside the label, and the
  button reports `aria-busy`.

### Cards / Containers

- **Corner Style:** 10px.
- **Background:** `--surface`, one step from the page ground.
- **Border:** 1px hairline. No shadow.
- **Internal Padding:** 16px (`sm`), 24px (`md`), 32px (`lg`). The page-level card is
  `lg`.

### Inputs / Fields

- **Style:** Surface background, `--border-strong` hairline, 6px radius, 34px tall.
- **Focus:** The border shifts to the accent; the global focus ring handles visibility.
- **Field:** A label above, an optional hint or error below, wired together by id so the
  hint is announced with the control rather than orphaned beside it.
- **Search:** The one exception to the 6px rule — search fields are pill-shaped, which is
  what marks them as search without an icon having to say so.

### Navigation

- **Style:** A sticky band with a hairline bottom border, surface background. Pill
  controls at 44px, labels collapsing to icons below 1200px.
- **Profile control:** A single button carrying the visitor's handle. Signing in and out,
  the theme, and every preference live behind it rather than in the bar.

### Action bar

- **Style:** Fixed to the bottom of the viewport while a gallery mode is open, surface
  background, hairline top border, the overlay shadow. Three tiers inside it: the count
  is plain text, the selection helpers are ghosts, and only the verbs read as buttons —
  one solid accent, the destructive one in danger.
- **Why the bottom:** the controls of an open mode are the only way out of it, and a
  character can hold 256 images. Anything anchored to the heading row is a full scroll
  away from whatever you just selected. A sticky rule cannot fix this: a sticky element
  travels only as far as its own parent, and that parent is one row tall.
- **Rule:** nothing inside it that can hold focus may disappear under the caret. A
  control whose meaning flips changes its own label rather than being replaced, and stays
  enabled at both ends, because a button that disables itself when clicked drops focus as
  surely as one that unmounts.

### Segmented control

- **Style:** A pill-shaped well in `--surface-sunken` with a 1px border and 2px inner
  padding; the selected option is a raised surface chip inside it.
- **Use:** Name versus Series search. It is a real radiogroup, not two buttons that look
  like one.

### Contact strip

The ranked lists on the landing page — "Most visited this week" and "Most popular
characters". The page is a proof sheet of the library, and the ranking is a proof sheet
of the week.

- **Style:** A band of frames butted edge to edge with 1px hairline dividers inside one
  rounded hairline border, captions beneath each shot. Every frame is the same size by
  construction: one aspect ratio (`--main-image-ratio`) and a cover fit, so no portrait
  crops differently from its neighbour.
- **Ranking:** The rank is a tabular micro figure above the name and series; on "Most
  popular characters" the rank slot shows the image count instead.
- **Responsive:** Below 768px the grid stops wrapping and becomes one horizontally
  scrollable row of half-width tiles — the same move the "Just added" strip makes.
  Strips are draggable with the mouse via `useDragScroll`, which recognises a drag only
  after a 6px slop and swallows exactly the one click a drag produces, so links inside
  it still navigate.

### Series bar

- **Use:** "Most popular series" on the landing page — a ranking where relative size is
  the point.
- **Style:** One row per series: the name, a tabular `images · characters` pair, and a
  2px hairline track underneath whose fill is the series' share of the largest character
  count (`--share`, set per row against the leader, which is not necessarily the first
  row).
- **Why a bar:** eight identically sized tiles are the one shape that hides what "most
  popular" means. The bar measures characters while the order measures images, so a
  series wide in one and narrow in the other shows it. Hover shifts the fill and name to
  the accent.

### Signature component — the justified gallery

The defining component of the system. Images sit in rows that end flush at a common
height, each one at its true aspect ratio, with the stored dimensions driving the layout
so nothing reflows as files arrive. Each item is a single real `<button>` whose meaning
follows the gallery's current mode — open, or select. Hidden images are dimmed rather
than removed, ownership is surfaced on the images you have selected, where it decides
which verb the toolbar offers, and reorder is a pointer-events drag with a long-press on
touch, an arrow-key move for the keyboard, and one saved order per move rather than a
toast per drop.

There are three modes and not five. Browse opens an image; select picks images; reorder
moves them. The four old modes — command, remove, hide, download — were one interaction
with the verb chosen before the selection existed, so the toolbar had to offer every verb
up front and then grey out the ones that turned out not to apply.

The `$ai` command has its own door in the character header, and it opens the selection
with every image already chosen rather than copying them. A button that copies everything
the instant it is pressed leaves no way to mean "all of them except those three", which
is the thing people actually want from a command.

## Do's and Don'ts

### Do:

- **Do** put every colour in `tokens.css`. A hex literal anywhere else is a bug — the
  system was built by removing 387 of them.
- **Do** use the four radii (4/6/10/999) and the 4px spacing scale. A value outside the
  scale means the scale is wrong; fix the scale.
- **Do** pair a `-subtle` tint with its own base colour as foreground, never with `-fg`.
- **Do** give large type negative tracking (−0.015em at title, −0.022em at display).
- **Do** use `tabular-nums` on any figure that updates in place.
- **Do** let images keep their real aspect ratio in galleries, and crop only character
  portraits, which have one canonical shape.
- **Do** define every colour in the base `:root` block. A token whose only definition
  lives in a media query renders as nothing in a browser that never matches it.
- **Do** reach for `Button`, `Card`, `Input`, `Field`, `Modal`, `Badge`, `EmptyState`
  before writing a new control.
- **Do** give every dialog a visible close button beside its title. Backdrop dismissal
  and Escape are conveniences layered on top of real controls — on a phone the backdrop
  is a thin band nobody can reliably hit and Escape needs a keyboard, so a dialog with
  no visible button has no way out of it. The rule was written before the button
  existed; a test now enforces it.

### Don't:

- **Don't** saturate the chrome. No coloured headers, gradient surfaces or tinted cards —
  the artwork is the only saturated thing on screen.
- **Don't** use pure grey. Every neutral carries the ~222 hue cast.
- **Don't** use Bootstrap's palette, or a purple-to-violet gradient. Both were removed
  deliberately.
- **Don't** add a third shadow. Two exist; a new one means the depth vocabulary is being
  reinvented.
- **Don't** use bounce or elastic easing. One curve
  (`cubic-bezier(0.2, 0, 0.13, 1)`) and two durations (120ms, 180ms).
- **Don't** introduce a fifth breakpoint.
- **Don't** put more than one solid accent button on a screen.
- **Don't** show a control that cannot act. A verb belongs on screen when the selection
  contains something for it to act on, and absent otherwise — a disabled button with a
  count of zero is a dead end wearing the clothes of an action.
- **Don't** write an inline `style` to resize a control. That is what the size variants
  are for, and the inline override is the exact thing the primitives replaced.
- **Don't** remove focus outlines. One ring, on `:focus-visible`, everywhere.
- **Don't** write a page's responsive rules in a different file from its base rules. A
  media query adds no specificity, so a later rule of equal specificity wins at every
  width. Nine declarations for the character page lived in `components.css`, were beaten
  by `pages.css`, and had never once applied — the header was written to stack on a phone
  and never did. Keep both halves of a rule in one file, and let the import order in
  `index.css` mean what it says.
