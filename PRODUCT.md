# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Anyone who plays Mudae, a Discord bot that deals collectible character cards. The product is
intended to be publicly usable by any Mudae player, not restricted to one server.

Today it is effectively pre-launch: the library holds ~1,706 characters and ~8,556 custom images,
but one person has registered and only 13 images carry an uploader. The identity, moderation and
contribution machinery already in the code — anonymous browsing, optional Discord sign-in, reports,
hide-for-me, contributor rankings — is preparation for strangers rather than a description of
current traffic. Future work should treat multi-user behaviour as a real requirement and current
usage numbers as not yet meaningful.

The job: assemble a set of images for a character and get them into Mudae.

## Product Purpose

Mudae lets a player attach custom images to a character with its `$ai` command. Doing that by hand
means keeping image links somewhere, pasting them into a command that has a Discord message-length
limit, and remembering which ones are already in use.

This product is where that set is kept, curated and turned into the command. Success is a player
producing a correct `$ai` command for a character in a few seconds, from a set of images they are
happy with, without having managed any links themselves.

## Positioning

It is built around Mudae's actual constraint rather than around general image storage. `$ai`
accepts image links only from ImgChest and Imgur, so the product hosts on ImgChest and keeps that
URL canonical, while serving its own smaller renditions for display. A general-purpose image host
or gallery cannot do the one thing that matters here — hand back a link Mudae will accept.

Two further properties a neighbouring tool would have to choose deliberately: the library is shared
and deduplicated across everyone rather than per-account, and removal is always reversible.

## Operating Context

- The output is pasted into Discord, where Mudae reads it. A command that exceeds Discord's
  message limit has to be split, and the split differs for Nitro and non-Nitro accounts.
- Images are gathered from elsewhere on the web — Pinterest is the common case — and arrive by file
  upload, by dragging an image from another page, or by URL.
- Both phone and desktop are real usage. Curating a character's images is done on either.
- A Mudae self-bot can fetch a character's metadata (series, rank, card art) so a character can be
  added without typing it.
- The landing page is drawn from the library rather than from copy: the product name beside
  its headline figures, the newest images, a weekly "Most visited" ranking, the most popular
  characters and series, and a contributor list. Every section hides itself when it has nothing
  to show, so the page degrades to the parts that are true.

## Capabilities and Constraints

Confirmed and binding:

1. **ImgChest is the only viable host.** `$ai` accepts ImgChest and Imgur links only, and Imgur is
   blocked in the operator's country. Anything that produces a Mudae command must use the ImgChest
   URL, and those links are `.png`. What the browser renders may come from anywhere — WebP
   thumbnails served from Cloudflare R2 are the display path — but the canonical link does not move.
2. **The `$ai` command is the product's real output.** Every other capability exists to produce a
   better one.
3. **Nothing is ever hard-deleted.** ImgChest keeps the file regardless, so removal is a state
   change and restoring is free. Anyone can restore what anyone removed; see DECISIONS.md §1 for
   why that is deliberate rather than lax.
4. **The Mudae self-bot is peripheral.** It fetches metadata for character authoring and must not
   be treated as a constraint on the data layer or the architecture. Automating a user account
   carries a ban risk, so the product has to work without it.

Undecided, and not to be built upon in either direction:

- **Library scale.** Seeding tens of thousands of characters is an aspiration, not a plan. Do not
  trade away simplicity or the current experience for a size the library may never reach, and do
  not assume today's ~1,700 characters is a ceiling either.

## Brand Commitments

The name is **ImgManager**. No logo, wordmark, colour or voice commitments have been made beyond
what the code already establishes.

## Evidence on Hand

Real, and usable in any surface that needs numbers or imagery:

- ~1,706 characters, ~8,556 custom images, ~441 series in the live library.
- Character portraits are uniformly 225×350; custom images are whatever shape they were drawn in.
- The weekly "Most visited" ranking is real, deduplicated per visitor: one enthusiast refreshing
  cannot move it.
- Written project record: `DECISIONS.md` (why, including rejected options), `ROADMAP.md` (phase
  state), `CUTOVER.md`, `CURRENT_STATE.md`, `DESIGN.md`.

Absences future work must not fabricate: no testimonials, no press, no case studies, no pricing or
licensing, no user counts worth quoting, and no third-party endorsement. The product is not yet
open to its intended audience.

## Product Principles

1. **The command is the product.** Anything that shortens the path from "these images" to "a
   command in Discord" wins over anything that decorates that path.
2. **The library belongs to everyone, so removal must be cheap to undo.** Curation conflicts are
   solved by making mistakes reversible rather than by making destruction hard.
3. **Design for strangers, measure with honesty.** Build as though the audience is public, but do
   not present current usage as evidence of adoption.
4. **Work within Mudae's constraints, not around them.** The bot's rules on link hosts, formats and
   message length are fixed inputs; the product absorbs that awkwardness so the player does not.
5. **The artwork is the content.** Interface exists to let someone see, compare, order and collect
   images; it should take as little of the screen as the job allows.

## Accessibility & Inclusion

No formal standard has been committed. The codebase has consistently treated keyboard and
screen-reader parity as a requirement rather than an enhancement — every gallery action is
reachable without a pointer, dialogs trap and restore focus, and state changes are announced — and
DESIGN.md carries contrast rules with tests behind them. Record this as established working
practice, not as a user-stated commitment.
