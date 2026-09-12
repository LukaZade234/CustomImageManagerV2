---
target: CharacterPage
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
target_identity: "file:/var/home/lperovic/Documents/CustomImageManagerV2/frontend/src/pages/CharacterPage.jsx"
target_fingerprint: "sha256:cab5a54602955ec62f558c76ada4df74f59ea68643ab3c1caa9a788a8ffe3333"
target_path: /var/home/lperovic/Documents/CustomImageManagerV2/frontend/src/pages/CharacterPage.jsx
timestamp: 2026-09-11T19-05-35Z
slug: frontend-src-pages-characterpage-jsx
---
**Method:** dual-agent (A: design review, isolated · B: deterministic scan, isolated)
**Target:** frontend/src/pages/CharacterPage.jsx and collaborators · Operate surface
**Caveat:** no browser automation available; both assessments worked from source.

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Mode is signalled only by which buttons render |
| 2 | Match system / real world | 3 | One action, two names: "Get $ai Command" vs "Copy Command" |
| 3 | User control and freedom | 3 | Undo and Removed drawer good; no Escape, no undo on Unhide all |
| 4 | Consistency and standards | 2 | Selection badge 60px in remove, 40px elsewhere; radii and motion off-scale |
| 5 | Error prevention | 3 | Honest confirm dialog; nothing guards reorder-Cancel or Unhide all |
| 6 | Recognition rather than recall | 1 | Nothing says which mode you are in; toolbar scrolls away |
| 7 | Flexibility and efficiency | 2 | No shortcuts, no range select, web drop capped at one image |
| 8 | Aesthetic and minimalist | 2 | Gallery exemplary; seven equal-weight buttons above it are not |
| 9 | Error recovery | 3 | Consolidated upload report excellent; raw err.message in eight places |
| 10 | Help and documentation | 3 | Reorder details thorough; hide-vs-remove unexplained before entry |
| **Total** | | **24/40** | Acceptable |

## Design specificity verdict

Authored for this product, with a generic middle layer. Product-specific and
untransplantable: the $ai command pipeline with its Nitro/non-Nitro split, the
remove-mine/hide-theirs ownership split, the thumbnail-vs-canonical-URL split, the
justified gallery, and --main-image-ratio. Generic and liftable: the toolbar's seven
equal-weight secondary buttons, the centred 60px selection disc, the character header,
the reorder hint panel. The gallery is a signature component; everything wrapped around
it is default.

## Deterministic scan

The specified invocation returned a FALSE CLEAN. The engine computes on resolved CSS;
scanning pages/ and components/ never reaches a stylesheet. Verified:
  detect frontend/src/pages frontend/src/components -> []
  detect frontend/src                                -> 2 findings
Findings: overused-font on Geist (FALSE POSITIVE - documented reasoned choice, tabular
figures + self-hosting); side-tab on .toast border-left 4px (likely real, unauthorised
by DESIGN.md).

## DESIGN.md is partly aspirational

Independently verified. The document committed at 0acbd1f states rules the code breaks:
- "Four breakpoints" -> nine values present (560, 640, 900, 1100 extra)
- Four radii -> nine distinct values; 8px used 16x; 42 literals vs 37 token uses
- "Two shadows plus a scrim" -> a third exists (color-mix focus ring, 3 uses)
- One easing, 120/180ms -> 9 of 21 transitions conform to neither
Several violations were introduced during the profile and home-page work.

## Priority issues

[P0] Reorder is pointer-only; no keyboard path exists. useGalleryReorder exposes only
pointer handlers - no onKeyDown, no aria-grabbed, no move controls. Ordering is the
product's output ($ai emits in gallery order). The help panel instructs users to drag,
offering no alternative. Fix: ArrowLeft/Right through the existing moveGroupInArray path,
move focus with the item, announce via a polite live region.

[P1] No persistent mode indication. Heading stays "Custom Images" in all five modes;
toolbar scrolls away. A click expected to open a lightbox silently arms an image for
deletion. DESIGN.md describes aria-pressed as "how an active gallery mode reads" and the
page uses it nowhere. Fix: reflect mode in the section heading, make the toolbar sticky
while mode !== browse, add role="status".

[P1] Entering any mode destroys keyboard focus. The clicked button unmounts; focus resets
to body. Five modes, five focus losses, no announcement. Fix: move focus deliberately to
the mode's primary action on entry and to the re-entry button on exit.

[P1] "Character not found" shown during normal loading (line 211). The page never reads
the store loading flag. Every refresh, bookmark and pasted Discord link opens with an
error. Fix: branch three ways - loading skeleton, absent, present.

[P2] Every reorder drop fires a success toast and a full refetch. Twelve adjustments =
twelve toasts over the gallery being edited; trains users to ignore undo-bearing toasts.
Fix: suppress per-drop toast, single confirmation on Done, skip the refetch.

## Persona red flags

Alex (power user): $ai flow split across two regions; "Done" in reorder is a no-op while
"Cancel" is a destructive server write - labels backwards; web drop imports exactly one
image (slice(0,1)); no Escape; no shift-range select; uploads strictly serial; a native
title tooltip on every one of 256 images.

Sam (keyboard/screen reader): reorder entirely unavailable; focus destroyed per mode
change; mode changes unannounced; the sentence explaining each disabled dead-end lives in
a title on a disabled element; lightbox drops the character name and attribution the
opening button carried.

## Minor observations

Dead CSS from the pointer-events rewrite (.draggable, .dragging, .delete-btn). A gradient
from a colour to itself (pages.css:288). Font sizes off-scale (0.9em, 0.95em, 11px). The
save-button paints solid accent in its UNSAVED default state, so two solid fills can
coexist against the one-per-screen rule. clampRatio + object-fit: cover does crop extreme
shapes, contradicting "custom images are never cropped". The gallery has no empty state,
though EmptyState is used in three other places. cancelReorder writes a stale baseline
array - the exact pattern a comment elsewhere identifies as the old clobbering bug.

## Questions to consider

1. Four of five modes are the same interaction; the gallery already knows
   (const selecting = ai || remove || download || reordering). Select first, verb second:
   browse drops from seven buttons to three and the "Remove mine (0)" dead end becomes
   structurally impossible.
2. Mode is the most consequential state and the only one with no visual representation.
3. The brief says artwork is the only saturated thing; selecting artwork covers its centre
   with a 60px solid disc, 50% larger in remove mode than anywhere else.
4. "Done" does not save and "Cancel" is not free. Should either button exist?
