# Decisions and Rationale

Why the v2 rework is being done the way it is. Each entry records the problem, the options that
were considered, **why the rejected ones were rejected**, and what was decided.

The rejections matter as much as the decisions. Several ideas here are the obvious first thing a
newcomer proposes, and each was worked through and found to fail for a specific, non-obvious
reason. Read those before suggesting an alternative.

---

## 1. Image deletion, griefing, and curation

The central design problem, and the longest discussion. Everything about identity and moderation
in this project follows from it.

### The problem

Any visitor can delete any image. Two distinct failure modes were observed:

1. **Griefing** — deliberate destruction, either malicious or careless.
2. **Well-meaning replacement** — and this turned out to be the more common and more important
   case. Users clear all of a character's existing images to make room for their own. They are not
   trying to harm anyone; they want their preferred images to be the ones on the page.

A third question sat behind both: if someone adds images only they like, which aren't good enough
to belong, what *should* happen? Is removing them justified?

### Rejected: mandatory accounts

Forcing sign-in would give full accountability. Rejected because the app's entire value
proposition is **convenience** — grab an image, take it to Mudae, leave. A login wall in front of
that discourages the casual use the tool exists to serve.

### Rejected: public gallery + private per-user galleries

A shared read-only public library, plus a private gallery per user where they can do as they
please. Rejected on three counts:

- It defeats the point of a single shared gallery.
- It actively **discourages growing the public library** and encourages private hoarding, since
  the private space is where you have full control.
- It has no answer for how the public library grows — who decides what gets promoted from private
  to public, and by what standard?

### Rejected: tag every image with its uploader, and that's it

Attribution alone, with everyone still able to delete anything. Rejected because it solves
nothing: anyone can still add anything, others can no longer hold them responsible by removing bad
images, and enforcement falls back to manual moderation — which is not feasible.

### Rejected: removal by quorum from hide signals

Let anyone hide an image; once N distinct people have hidden the same one, remove it globally. The
attraction was that the "vote" is a free side effect of an action people take for their own
reasons, so nobody has to be bothered to participate.

Rejected for a fatal reason: **the hide signal is anti-correlated with quality.** Most users never
bother hiding anything — they grab what they want and leave. The people who *do* hide in bulk are
precisely the selfish ones clearing a page to make room for their own uploads. So aggregating hide
signals would systematically remove *good* images, driven by users whose motive has nothing to do
with quality. And the userbase is far too small for good-faith participation to outweigh a few
selfish users.

### Rejected: automatic retirement by disuse

Instead of removal signals, measure **takes** — downloads and `$ai` command copies, which the app
already collects as `selectedUrls`. An image that has been visible for months, seen by many
people, and taken by nobody but its uploader is demonstrably unwanted, so retire it automatically.
The appeal was that this signal is unfakeable: to suppress someone's image you would have to make
other people not download it.

Rejected because **users mostly take only their own images.** Given enough time, nearly every
image accumulates zero third-party takes, so the rule eventually retires everything. The signal is
real but far too sparse at this population size to support a removal decision.

### Not the same thing: takes as your own memory aid

Takes are read now — but only ever as **one person's own history shown back to them**, never as an
aggregate. The character page offers two selection helpers, "Select copied" and "Select not copied",
scoped to the viewer, so someone who has already registered images with Mudae can see which ones and
pick the rest. `image_takes.batch_id` groups the rows from one "Copy `$ai` command" action, which is
what makes "the ones I copied last time" an exact set rather than a guess at a time window.

This does not overturn the rejection above, and the distinction is the whole reason it is safe:

| Rejected: retirement by disuse | This: your own selection helper |
|---|---|
| An **aggregate** across everyone | **One viewer's** rows, filtered by their identity |
| A **judgment** that an image is unwanted | A **memory aid**; says nothing about worth |
| **Visible to others**, changes what they see | **Private**; nobody else's view changes |
| **Acts** — retires the image | **Shows and selects**; the human still decides |

The failure mode that killed the original idea was sparsity: almost every image has zero *third-party*
takes. That is irrelevant here, because the helper asks "which images did **I** copy", and the answer
to that is never empty for the person asking. Should anyone ever propose reading takes for ranking,
retirement, or anything another user can see, this entry is the line they would be crossing.

The history is cookie-bound, like ownership and saved lists: clearing cookies loses it. That is
stated in the UI rather than left to be discovered.

### Rejected: voting or ranking

Up/down votes, or sorting by score so weak images sink. Rejected on two grounds:

- Nobody would bother voting in practice. There is no existing engagement loop to attach it to.
- It solves a crowding problem that does not exist. A character has ~10 images on average and 200
  at the extreme, and users browse *characters*, not individual images — the whole set is visible
  on one page regardless of order. Ranking cannot hide anything, so it changes nothing.

### The root cause

Four mechanisms, four different failure modes, one shared cause: **the userbase is too small to
produce a reliable aggregate signal in either direction.** Removal signals are biased, take
signals are sparse, explicit votes will not be cast. Any design that infers community consensus
will fail here.

### The reframe

The breakthrough was noticing what users actually do with an image. The two actions available are
**Download selected** and **Copy `$ai` Command** — both operate on a per-image selection, and both
mean "I am taking this away with me."

So a character page is a **menu, not a collection.** Nobody consumes it as a finished artifact;
they open it, pick one to three images, and leave. Every visitor leaves with a different subset.

Two things follow:

- **Nothing about anyone's use of this app requires the list to be short.** If someone adds five
  mediocre images, the page goes from ten thumbnails to fifteen and a visitor scans for one extra
  second. A longer menu is not a broken menu. Growth is bounded anyway, because uploading is real
  effort and effort is scarce — nobody floods the site for free.
- **The deletions were never a moderation problem.** They were people using the only subtractive
  tool available to express a *personal selection* against a *shared resource*. The app already
  has a per-user selection concept — `selectedUrls` — it just evaporates on reload.

So: stop policing the deleting. **Remove the reason to delete.**

The premise being dropped is that "unworthy" images are a problem requiring a mechanism. They are
not. The only genuinely harmful additions are **objective** — wrong character, dead link, NSFW,
duplicate, AI artwork — and every one of those has a right answer that requires no consensus at all.

### The decision

1. **You can only remove images you added.** One rule, no thresholds, timers, or quorums.
   Griefing becomes *unimplementable* rather than merely deterred or reversible — there is no
   button that removes another person's image. This also fully handles the well-meaning replacer.
2. **Hide-for-me** handles all matters of taste. Per-identity, instant, unlimited, invisible to
   everyone else, costing nobody anything and requiring no justification. This is the pressure
   valve, and it is what the bulk-deleters were actually reaching for.
3. **Report** handles only the objective cases, with a reason attached, auto-removing at 2 distinct
   reports. Its friction is a feature — someone clearing a page will not file ten reasoned
   reports.
4. **Nothing is destroyed by the ordinary verbs.** Removals are soft; a Removed drawer restores in one
   click. This is nearly free because ImgChest was assumed never to delete the underlying file (see
   §2). A later staff **permanent delete** is the sole exception: it removes the ImgChest post,
   which the API does allow, and keeps the row as a tombstone so the record survives.
5. **Take counts are logged but drive nothing**, except an opt-in "sort by popular" toggle.
   Collecting them costs nothing and commits to nothing, and it means that if bloat ever does
   become real, there will be months of actual data to design against instead of another guess.
6. **Moderator and owner accounts exist as a manual fallback only** — explicitly not the primary
   mechanism, and not something the operator should need to use routinely.
7. **Reordering a shared gallery is tied to a Discord account.** Position is prominence, so pushing
   images down is removal's practical equal — but unlike removal it had no rule and left no trace.
   It now requires a linked account and is rate limited. It is deliberately *not* owner-only: the
   gallery is shared, and any signed-in person may still curate the order. The account (rather than
   the cookie) is what a suspension or ban can be held to, since clearing a cookie mints a fresh
   pseudonym for free — the same reasoning as uploads.

Worked example — the exact scenario that motivated all of this. Someone opens a character with 10
images and wants only their own. They click remove on all 10: each is hidden **for them**, nothing
changes globally, nobody else notices. They upload their 8. The pool goes from 10 to 18. They see
exactly the gallery they wanted; everyone else is untouched; the library **grew instead of
churning**; and the operator never opened the site.

### Non-goals

- Deciding what is "worthy." Nothing in the system makes that judgment, deliberately.
- Routine human moderation. If the design requires the operator to check the site regularly, it
  has failed.

### The ownership-claim exception (temporary)

Rule 1 above ("you can only remove images you added") rests on `custom_images.added_by`, and the
8,500-odd images imported from v1 have `added_by IS NULL`. Migration 004 calls that permanent in as
many words — ownership must always be recorded, or images "would fall into the same unowned bucket
as the 8,547 migrated from v1, permanently, with no way to reclaim them" — and
`db.remove_custom_images` refuses to let an ordinary user touch a NULL-owner row. That is what makes
griefing the inherited library unimplementable.

This feature is the single, staff-gated way back out, for the original userbase who uploaded those
images on v1 before ownership existed and should not lose them to the migration. It does not weaken
the rule, and the reasons are worth stating because the shape looks like a reversal:

- **Nothing transfers on its own.** Filing a claim writes a request row and stops. Only a moderator
  approving it performs the `UPDATE`, so a malicious claim achieves nothing but a moderator's time.
- **The transfer is NULL-only.** An image someone already owns is never taken, even on approval.
  A claim against a fully-owned character is refused with nothing left to claim.
- **It is not a queue that accumulates pending work.** The distinction §5 draws for the moderation
  surface is preserved: claims are a bounded reconciliation of a fixed backlog, not a continuing
  stream of incoming work. When the banner stops appearing, the feature has finished its job.
- **It is temporary and one-directional.** Once every character is claimed (or the operator removes
  the affordance), the unowned bucket is closed again, and any future import would need its own
  decision. Nothing here reopens the general case.

Two claimants for one character are allowed while pending, because the moderation queue is more
useful when it shows rivals; approving one auto-rejects the rest with a notification, since the end
state is one owner. A rejection is not a ban — the claimant may ask again, and the unique index that
enforces "one pending claim per person per character" is scoped to `pending` for exactly that.

The record of *who was given what* survives in `ownership_claims` (`decided_by`, `decided_at`,
`images_granted`), so the bestowal is auditable rather than silent.

---

## 2. ImgChest is mandatory

Mudae's `$ai` command accepts image URLs **only from ImgChest and Imgur**, and Imgur is blocked in
the operator's country. An image hosted anywhere else cannot be used in Mudae, which is the app's
entire purpose.

This makes ImgChest a hard external constraint, not a technology choice, and it is not open to
being refactored away in favour of R2, S3, or self-hosting — however much better those would be as
storage.

**A backup mirror is a different idea and is wanted.** Keeping a second copy of every image
elsewhere protects the library against ImgChest losing files or shutting down. The ImgChest link
stays canonical and is what gets handed to Mudae; the mirror is insurance only.

A useful consequence: because nothing ever deletes from ImgChest, every image in the app's history
is still live at its URL. Soft delete and restore are therefore essentially free, and the
moderation design in §1 depends on this.

### The one-time cut-over cleanup

Nothing has ever been deleted, so the account still holds every upload the app and v1 ever made —
including images no database still references, and griefed or otherwise inappropriate uploads made
before moderation existed. The cut-over is treated as the one moment to reconcile the account against
what is actually used, and everything else is then deleted permanently. This is a deliberate
exception to the paragraph above: the "never delete" property holds *during* operation, and this is
the single planned reconciliation of the backlog.

The keep sets are **in use** (from a manual Discord export of the URLs named in Mudae's `$ai` lists,
deduplicated across servers) and **on the site** (`custom_images`, in any state — so an image removed
on the site but still used in Discord is a keeper, not a deletion). Anything in neither set is a
deletion candidate. In-use images the site does not have are re-added in the `removed` state, so
they surface in the Removed drawer and can be restored; they land with `added_by IS NULL` like every
other migrated row, so staff restore them.

The cleanup is **planned, not routine**, and is gated three ways: the script does nothing without
`--execute`, it writes a preview first that a human reads, and the preview is surfaced in the app as
an **owner-only** tab so the operator reviews it in the same place the decision was made. The app
never deletes — the destructive half stays a CLI. It supersedes the one-off
`backfill_imgchest_post_ids.py` pass by computing the same file-to-post map itself.

**Ordering is load-bearing.** Content fingerprints and image dimensions both re-read the image bytes
from ImgChest, so they must run **before** the cleanup; deleting first makes them impossible for the
files concerned. See `CUTOVER.md`, [ImgChest cleanup](#imgchest-cleanup).

---

## 3. Hosting

### Requirements

Real CPython with native extensions (`Pillow`, `psycopg`, `discord.py-self`); outbound WebSocket
to Discord; requests lasting 30s or more, plus SSE streaming; PostgreSQL; globally distributed
users; free or near-free; a custom domain.

### Rejected: Cloudflare Workers for the API

Workers run JS/WASM. Python Workers cannot load native CPython extensions, so `discord.py-self`,
`Pillow`, and `psycopg` are all impossible, and a 30-second Discord login does not fit the
execution model regardless. **Cloudflare D1 is rejected with it** — it is SQLite reachable only
through a Worker binding, so a Flask process on a VM cannot use it.

This rejects Cloudflare as a *compute* platform only. Cloudflare is still used heavily for
everything else.

### Rejected: Vercel / Netlify functions, Render free tier

Serverless models cannot hold the long-lived connections or long request durations. Render's free
tier spins down after idle, and a cold start would break both Mudae lookups and SSE streams.

### Decision

**Cloudflare for everything except compute:**

- **Cloudflare Pages** — the React SPA, free, global edge, custom domain
- **R2** — the 1000 character PNGs, free egress, replacing Flask serving them off local disk
- **DNS + CDN** in front of everything
- **Cloudflare Tunnel** — exposes the origin with no port forwarding, static IP, or firewall
  changes, with TLS terminated at the edge

**One real box as the origin**, running Flask and PostgreSQL together.

### Why global latency is acceptable

The concern was that active users on the other side of the world would suffer against a
single-region origin. The resolution is to separate the traffic: once the SPA and every image are
served from Cloudflare's edge, the only thing crossing an ocean is **small JSON API calls**. One
round trip of 200–300ms to load a character page is entirely acceptable, and the heavy payloads —
which is what latency actually hurts — never leave the edge.

### Why the origin host choice is deliberately deferred

Both candidates are viable:

- **Oracle Cloud Always Free** — a permanently free 4-core ARM / 24GB VM with datacenter uptime,
  in a region chosen for the userbase. Risks: awkward signup, capacity shortages in popular
  regions, and Oracle reclaiming idle instances.
- **A home server** (repurposed PC) behind Cloudflare Tunnel — free and fully controlled, but
  uptime depends on domestic power and internet, and upload bandwidth caps throughput.

Because the Tunnel makes them interchangeable from the outside, **switching later costs one
config change.** Deciding now would be a guess; deciding at build time costs nothing. Both paths
are documented in `ROADMAP.md`.

Worth noting that running the Discord self-bot from a residential IP is arguably *less* likely to
attract attention than from a datacenter one.

### Why the database sits with the app, not at the edge

The app makes several database round trips per request; the user makes one request. Co-locating
the database with the application therefore removes far more total latency than edge-locating it
would, and edge databases would optimize the hop that is already cheap. The database therefore
lives on the origin box.

**Superseded in part by section 8:** this originally specified PostgreSQL with `pg_dump` backups on
a cron. The engine is now SQLite, replicated continuously to R2 by Litestream. The reasoning above
is unchanged and in fact strengthened — with SQLite there is no network hop to the database at
all.

---

## 4. Identity: cookie pseudonyms, with Discord optional

Ownership requires knowing who added what, but §1 rejected mandatory accounts.

**Decision:** issue a signed cookie on first visit carrying a stable pseudonymous id and a
generated handle — the approach Figma and Google Docs use for anonymous visitors. There is no
login screen, no password, and no friction; the user never notices. That yields attribution, a
real notion of "your images," per-identity rate limiting, and per-identity hidden sets.

**Sign-in is an upgrade, never a wall.** An optional "Sign in with Discord" binds the existing
pseudonym to a real account, making identity survive cookie loss. The userbase already lives in
Discord for Mudae, so it is one click for them.

**Why weak identity is acceptable here.** Clearing cookies produces a new identity, so this is not
secure identity — and it does not need to be. It exists for accountability and UX, not for guarding
secrets. Because no destructive action is available to *anyone* under §1, an evader gains nothing
by evading: the worst outcome is losing your own hidden set and your ability to remove your own
past uploads.

**Adding an image requires the Discord upgrade.** A cookie-only visitor may browse, save, hide,
report, restore and edit metadata freely, but every endpoint that uploads bytes to ImgChest
(`/api/custom-image`, `/api/import-custom-images-from-urls`, `/api/set-main-image`, `/upload`, and the
file branch of `/api/add-character`) is behind `require_signed_in`. **Creating a brand-new character
is gated too**: `/api/add-character` accepts a name the catalog already knows and refuses an unknown
one to a cookie-only caller, so the library grows from Discord-linked accounts while
`/api/catalog/add-character` (a known character, no upload) stays open. The reason is the one gap in
the paragraph above: uploading is the only action that spends a shared resource (the ImgChest key),
and adding arbitrary entries is the other way the library can be shaped from an anonymous cookie. A
cookie is free to mint, so "who did this" has to survive clearing it — which is also what makes a ban
or a suspension mean anything at all.

**Implementation note:** Discord OAuth requires a **newly registered Discord application**. The
existing `DISCORD_USER_TOKEN` is a self-bot account token and cannot be used for OAuth. The two
are unrelated and must not be conflated.

`SECRET_KEY` — currently set but never read — becomes load-bearing, and must be a stable
production secret. If it changes, every identity cookie is invalidated and every user silently
becomes a new person.

---

## 5. Roles: user, moderator, owner

Added as an explicit **fallback**, after the automated mechanisms in §1 were settled.

The reasoning: §1 deliberately leaves some cases unhandled — genuinely bad content that nobody
happens to report, disputes, spam waves. Rather than build more automation for rare cases, there
is a manual escape hatch. Moderators can remove any image and restore from the drawer; the owner
can additionally promote and demote moderators.

The owner is bootstrapped from an `OWNER_DISCORD_ID` environment variable matched at Discord
login, so there is no chicken-and-egg problem and no admin password to leak.

**This is a fallback, not the design.** If routine operation requires moderators to act, something
in §1 is wrong and should be fixed there instead.

A staff-only **inspection surface** was added later (`/profile/moderation`; see `MODERATION.md`).
It sits inside the profile as one more tab rather than in the topbar, and does not contradict the
paragraph above, because it is not a queue: it holds nothing, counts nothing pending, and changes no
chrome with site state. It answers *"what has this person been doing?"* when the operator already has
a reason to look, which is inspection rather than routine moderation. Five of its verbs are live —
**restore** an image (already non-destructive), the **owner-only** promote/demote of a contributor's
role, **warn** (a message and a staff record), and **suspend / ban**, which restrict the account to
reading while a banner tells the person why (owner-only to lift). The topbar instead carries
**Notifications**, the channel these ride: the app messaging one account, and the owner messaging
everyone or the moderators. It is a message log, not a worklist. The one verb still inert is
permanent delete, which needs its irreversible-file decision first. `image_reports` stays unread.
Image verbs are placed here as well as on the character page because a pattern — the same person
removing images across many characters — is only visible in one place; that still requires opening a
contributor on purpose. If a
later phase adds a pending count, a badge, or action logic driven by site state, that is the signal
to re-read §1 and fix what is generating the backlog.

---

## 6. Data model: real tables instead of JSONB blobs

The current schema is a two-column `kv_store` holding four whole JSON documents, and a custom
image is a bare URL string in an array — with nowhere to record an owner.

Bolting records into the blob and adding side tables keyed by image id would work, but a proper
`custom_images` table is **simpler overall** and fixes a real bug for free: the existing
read-modify-write of an entire document, under `autocommit=True` with no transactions across two
gunicorn workers, silently loses concurrent writes today. Users experience that as images
vanishing, which is indistinguishable from griefing but entirely unrelated.

Ownership, soft-delete state, reports and takes all become columns and joins rather than parallel
structures.

**Extended by section 8**, which supersedes this section's final scope. An earlier draft kept
`characters`, `saved_characters` and `last_updated` in the KV store on the grounds that they were
not causing problems. That was too conservative: `last_updated` is a parallel map that has to be
kept in step, `saved_characters` is a single list shared by every visitor, and keeping the
character name as a key is what makes renaming a 67-line cascade. All of them become tables.

---

## 7. Libraries and toolchain

### Concurrency comes *after* the data layer, not before

The obvious quick win is to raise gunicorn's concurrency — today it runs `--workers 2` with the
default sync worker class, meaning **two concurrent requests site-wide** against requests that take
up to 55 seconds (Mudae lookup) or minutes (series import, image upload). One import plus one
upload session makes the site appear down for everyone else.

It was tempting to fix that first because it is nearly a one-line change. **That would have been a
mistake.** The read-modify-write data-loss bug gets worse with concurrency: more simultaneous
requests means more collisions on the JSONB blob and more silently lost writes. Raising concurrency
before Phase 2 would trade a visible problem for an invisible one.

So the worker change is deliberately sequenced after the data layer is transactional.

### `gthread`, not `gevent`

The usual advice for a blocking WSGI app is gevent, and that advice is wrong here: gevent
monkey-patches sockets, which conflicts with the `asyncio.run()` Discord client in
`mudae_discord.py`. asyncio and monkey-patched sockets do not coexist reliably.

`gthread` patches nothing — it just gives each worker a thread pool, and Python releases the GIL
during I/O, which is what nearly all of this app's blocking actually is (waiting on Discord,
ImgChest, and Postgres).

There is also a free win: `--workers 1 --worker-class gthread --threads 8` gives 8 concurrent
requests instead of 2, one copy of the app in memory instead of two, and — because there is only
one process — **makes the Discord `threading.Lock` correct**, since the reason it fails today is
that two worker processes hold two independent locks.

### Tests before the data-layer rewrite

Originally testing was the last phase. That was an ordering error. The test that matters most —
"concurrent adds to one character both persist" — *is* the acceptance criterion for the data-layer
rewrite. Written afterwards it proves nothing; written first it fails against the current code and
then flips green, which is the only real evidence the data-loss bug is dead.

### `uv` for the Python toolchain

Four sources currently disagree about which Python this is (`.python-version` 3.13, the venv
3.14.6, the Dockerfile 3.11, pyright 3.11), there is no lockfile, and 8 of 10 dependencies have no
upper bound — `flask>=2.0` would accept Flask 4.0 and break the build with no code change.

`uv` fixes the interpreter pin, the lockfile, and the environment in one tool rather than three.

### psycopg 3, and no ORM

`psycopg` 3 with `psycopg_pool` replaces `psycopg2-binary` and brings pooling with it, so
connection pooling stops being a separate task. **Done in Phase 2.**

The decision that mattered more than the driver: `db.py` exposes **no setter**. Writes go through
`mutate_*`, which holds an advisory lock across the read and the write. Keeping `set_x()` around
"for convenience" would have left the racy two-call pattern available, and it would have crept back
in. Removing it makes the correct path the only path.

**SQLAlchemy was considered and rejected.** Five small tables and a handful of queries do not
justify an ORM; raw SQL through psycopg3 with Alembic for migrations stays more legible, and a
future session reading plain SQL does not have to reverse-engineer a mapping layer to understand
what the database actually does.

### react-query *and* zustand, not one or the other

These look redundant and are not. `@tanstack/react-query` owns **server** state — fetching,
caching, retry, invalidation — replacing retry and backoff logic that had been hand-rolled and
duplicated across `useStore.js` and `api.js`. zustand keeps owning **UI** state: dark mode, toasts,
selection. Its per-character caching is also what makes killing the full-map fetch practical.

Adopted in Phase 9. The gallery query and the catalog hooks (search, suggest, match) came first
because they were where the duplication lived; `saved`, `stats` and `me` followed, and the store is
now UI state only. Signing out invalidates every query, because an identity change is exactly a
change in what the server is answering.

### Dependencies dropped, and one deliberately kept

- **`protobuf`** — declared directly but never imported by our code; it is transitive via
  `discord.py-self`. Pinning another package's transitive dependency only creates future conflicts.
- **`flask-compress`** — **removed** in `5c62b9c`, once Cloudflare was in front and confirmed to
  be compressing. The edge does Brotli, which beats gzip, so origin-side compression only spent CPU
  on a box we pay for in uptime. The ordering was the whole point: it stayed until the CDN was
  proven, because removing it first would have meant serving everything uncompressed and blaming
  the CDN for it.
- **`flask-cors` is kept.** It looks droppable, but once the SPA is on Pages the API is genuinely
  cross-origin, and cookie identity makes CORS subtle — `*` is invalid with credentials.
  Hand-rolling that is how it gets done wrong.

### TypeScript: open

`@types/react` and `@types/react-dom` are installed although the project contains no TypeScript.
The decision is deliberately left open, but the timing is not: adopting TS is cheapest immediately
before a large component is restructured, and considerably more expensive after. `AddPage.jsx`
(745 lines when this was written) has since been split, so that particular window has closed; the
choice now stands on its own merits. Either commit, or remove the unused type packages.

The same timing argument applies to the frontend major upgrades (React 18→19, react-router 6→7,
zustand 4→5, Vite 5→8, which also clear 5 npm vulnerabilities): do them while the components are
still whole and a test harness exists to catch regressions.

---

## 8. The v2 data model

### SQLite on the origin box, not PostgreSQL

Neon is being dropped for cost, and the replacement is **SQLite in a single file**, continuously
replicated to Cloudflare R2 by Litestream.

The deciding facts are about size and write pattern, not about the database. There are ~1,700
characters in the working set today and perhaps 50,000 if the full Mudae roster is ever seeded;
custom images are URL strings. That is **tens of megabytes at the outside**, and writes are
human-paced — someone adding an image, bookmarking, or hiding something. Nothing here needs a
database server.

What SQLite buys:

- **No service to operate.** On a self-hosted box, Postgres is another thing to patch, monitor and
  restart after a reboot. SQLite is a file the application opens.
- **`sqlite3` is in the standard library**, so `psycopg` leaves the dependency list.
- **Better durability than a dump cron.** Litestream streams every change to R2 continuously, so a
  dead server costs seconds of data. A `pg_dump` schedule costs however long since the last run.
  Durability is the primary goal — this library is irreplaceable accumulated work.
- **Inspection is copying a file** and opening it in a desktop GUI, rather than an SSH tunnel to a
  database client.

The real trade-off is single-writer. At this write volume it is theoretical, and SQLite in WAL mode
handles multiple reader processes and several worker threads without difficulty.

**An argument that was used and then withdrawn:** an earlier draft justified SQLite partly on the
grounds that the Discord self-bot forces a single process anyway. That reasoning was wrong. The
bot's single-process behaviour is an artifact of running it inside the web application, and Phase 8
moves it out regardless. It is an authoring-time convenience that nobody waits on during normal
use, and it must not be treated as a constraint on the data layer, the worker count, or anything
else. The SQLite decision stands on operational grounds alone.

### Characters get a surrogate id

The character *name* is currently the primary key across four separate documents, which is why
`edit_character` is 67 lines — most of it a rename cascade updating three documents in sequence,
able to half-fail. With `characters.id`, renaming is one `UPDATE` and the cascade and its failure
modes cease to exist. `name` stays `UNIQUE`, so the existing `/character/<name>` routes keep
working by looking the name up.

### Everything becomes a table; nothing stays JSON

```
characters      (id, name UNIQUE, series, rank, main_image_url, updated_at)
identities      (id, handle, discord_id UNIQUE, role, created_at)
custom_images   (id, character_id FK, url, content_hash, position,
                 added_by FK, added_at, state, removed_by, removed_at, removed_reason,
                 UNIQUE (character_id, url))
saved           (identity_id, character_id)
user_hidden     (identity_id, image_id)
image_takes     (image_id, identity_id, kind, at, batch_id)
image_reports   (image_id, identity_id, reason, at)
```

Three consequences worth stating:

- **`last_updated` stops being a document** and becomes `characters.updated_at` — one column
  instead of a parallel map that has to be kept in step with everything else.
- **`UNIQUE (character_id, url)`** makes duplicate rejection a property of the schema rather than a
  task to remember.
- **Bookmarks become per-person.** `saved_characters` is currently a *single global list*: if
  anyone bookmarks a character, everyone sees it. That is almost certainly not intended, and it
  fixes itself the moment bookmarks hang off an identity.

The Phase 2 advisory lock can go once images are rows: two inserts into `custom_images` do not
contend, so there is nothing left to serialise.

### Uploading the same picture twice

`custom_images.content_hash` was declared in Phase 1 and left unwired. It holds the **sha256 of the
stored file** — the normalised WebP that ImgChest actually receives, not the raw upload — and the
upload path checks it *before* calling ImgChest. Both halves matter. Before, because ImgChest
refuses to delete the only image in a post, so a duplicate that reached it would be permanently
orphaned, not merely redundant (see "Permanent delete" below). Of the stored file, because that is
the only version the backfill can ever see: hashing the raw upload would make every pre-existing
image unmatchable forever. Encoder drift is the accepted cost, and the fingerprint is recomputable.

The rules:

- **Same character is a block, by default.** The upload is skipped and reported, and the client
  shows the copy already there beside the one being added. The visitor can override
  (`allow_duplicates`), because refusing outright would be wrong when the repeat is intentional —
  but the default for an accident is to stop.
- **Another character is a note, never a block.** The same art on a second character is usually
  deliberate; the response says where else it lives and gets out of the way.
- **Exact bytes only.** A re-encoded, resized or re-compressed copy hashes differently and is not
  matched. That is deliberate: a perceptual hash on the add path would occasionally refuse a
  genuinely new picture, so the fuzzy match belongs to a moderation *review* surface (a planned
  Phase 2 addition), not to the upload gate.
- **Purged rows do not block.** Their source is gone from ImgChest, so there is nothing to restore;
  blocking would make the picture impossible to re-add.
- **Removed rows do block, and say so.** The copy still exists and can be restored, so the dialog
  offers a **Restore it** button that puts the original back rather than adding a second one.

The check is server-side for both entry points — file upload and web-URL import — because the
import path fetches the bytes on the server, where the client has nothing to hash. The existing
`content_hash` and `idx_custom_images_hash` carry it; no migration was needed. For the library that
predates the gate, `scripts/backfill_content_hashes.py` fills the fingerprint in (it has to
download each image, which is exactly why the hash is of the stored file), and the moderator
**Duplicate images** review at `/profile/moderation/duplicates` groups each character's own copies
by it — the same file twice on one character — because the same picture on several characters is
usually deliberate. An extra copy is deleted for good (ImgChest file included) by staff, owner
included, since it is a genuinely redundant upload rather than someone's work; a copy already removed
can be restored instead. The add-time gate only ever sees a fingerprint that already exists; the
backfill is what gives the old rows one.

### 50,000 characters: searchable names, pages on demand

If the full Mudae roster is seeded, most of those characters will never receive a custom image.
Rather than 50,000 mostly-empty pages, all names are **searchable and autocompleteable**, and a
character page becomes meaningful when someone first adds an image to it. Browsing stays useful,
and the Discord bot stops being needed for name and series lookup.

**This is not yet actionable.** A search for a public dataset turned up `LilJamJam/MudaeDB`
(series-bundle notes in Markdown, not a character list) and `marsn3/mudaetracker` (the Top 1000,
which is already in hand). No ready-made 50k dataset was found; `mudae.net` is the likelier source
but would need scraping. The schema is therefore built to *support* 50k, while seeding continues
from the existing ~1,700.

**The blocking prerequisite, now met.** The frontend used to load *every* character into the
zustand store on startup and filter client-side. At 1,000 that was ~150 KB; at 50,000 it would be
7–10 MB per page load, which is untenable — especially for the overseas users the hosting plan
exists to serve. Search and autocomplete now run on the server (`GET /api/catalog/search` and
`/api/catalog/characters`) over the catalog and the working set, and the character page fetches the
one record it shows, so nothing scales with the roster before it grows. The working set stores the
same folded `name_key` the catalog does (migration 011), so a name lookup is one indexed row rather
than a scan folding every character in Python. The client-only `GET /api/characters` was retired with
it.

### The Mudae catalog: a working set plus a search corpus

The scrape that was missing above is now in hand. Mudae's `$wa` / `$ima` listings can be copied out
as text — series header, then `#rank - Name · ($pools) - https://mudae.net/uploads/...png` — and
imported in bulk, which removes the self-bot from the *seeding* path entirely. Two facts made this
worth acting on rather than filing away:

- **`mudae.net` portraits are hotlinkable and already the right shape.** They are served with
  `access-control-allow-origin: *` and no referrer gate, and the sampled ones are 225×350 — exactly
  `--main-image-ratio`. The 1,000 committed PNGs are almost certainly these same images re-hosted.
- **Portraits are not part of a `$ai` command.** The ImgChest-only rule is a constraint on custom
  images, not on what a portrait may be. So `characters.main_image_url` can hold a `mudae.net` URL
  with no ImgChest upload, which is what the Mudae import path used to do needlessly.

The data model splits the two jobs, matching the "searchable names, pages on demand" idea above:

- **`character_catalog`** is the scrape: name, series, rank, pool (parsed into waifu/husbando ×
  anime/game booleans), the `mudae.net` portrait, and `scraped_at`. It is the searchable corpus.
- **`characters`** stays the working set: names someone has saved, customised or added. A catalog
  name does **not** become a working row until someone acts on it.
- **`name_key`** (NFKC + casefold + collapsed whitespace) is the match key, because SQLite's
  `COLLATE NOCASE` folds ASCII only and would miss `Pokémon`/`Pokemon` or an NFD spelling.

The importer merges every extract by `name_key` before writing: extracts overlap heavily, identical
repeats are dropped, and when two captures disagree the better (lower) rank wins. It is idempotent,
dry-runnable, and never overwrites a working row's field it did not find in the catalog.

**Catalog gap-fill and rank refresh: considered and declined.** Fetching, by series, only what the
catalog lacks or has let drift (a series with no rows, rows with an empty rank/series/portrait/pool)
and keeping ranks current was the obvious last job for the self-bot. It is not worth doing. Ranks
move constantly and each series costs one Discord identify, so it is unbounded ongoing maintenance
for a number nothing acts on; and the character gaps are already mostly closed, so what remains is
individual names that can be added on demand through the existing Add flow — precisely when someone
wants them. The mechanism stays (`$imartsmi-` plus the idempotent upsert) if a real need appears;
there is deliberately no background reconciliation. Series pages remain a natural next phase.

Mirroring the portraits to R2 as WebP (~18 KB each, ~8× smaller than the PNGs,
free egress) has since landed: `scripts/mirror_portraits_to_r2.py` fetches each `mudae.net` portrait,
encodes WebP, uploads to R2 and records the key in `characters.main_image_thumb` /
`character_catalog.mudae_image_thumb`, and the frontend prefers it via `portraitUrl`. Because the main
image is display-only and the catalog's Mudae portrait is the canonical public image, a working row
takes that mirror even when its `main_image_url` is a hand-uploaded ImgChest file -- the main image is
meant to be the character's true art, not whatever someone last set. Server-side
catalog search and pool filters, once on this list, have landed too: `/api/catalog/search` replaces
the full-roster fetch, and the catalog's four booleans back a `pool=` parameter on the suggestions
API and the facet chips in the Add form. The catalog only *adds*
a table, so none of them are blocked by this one. `remote_images._allowed_portrait_url` is
deliberately separate from the user-facing download proxy's allowlist: the internal accent fetch may
read Mudae, a visitor's "download this image" may not.

### The `$im` card's gender and pools

`$im` shows more than a name and a rank: the gender beside the series (`NieR: Automata :male:`) and
the pools the character belongs to underneath (`Game & Animanga · 201`). Both were being parsed past
and thrown away. They are now read off the card and stored on the working row (`is_female`,
`is_male`, `pools`), because the alternative is a second Mudae request later to recover what the
first reply already said.

The gender arrives as a custom Discord emoji, which `_strip_md` removes before the series is read,
so it is parsed from the raw description; the shortcode and Unicode forms are accepted too. A
character can be in both gender pools, so the two flags are independent. `pools` is the label as
Mudae prints it, not the catalog's tag codes: it is a caption for the character page, and the
catalog's own booleans remain what filtering reads. A lookup that comes back without a gender never
clears a stored one — a sparse card is not evidence the character changed.

The catalog carries the same two things in its pool codes, so most characters have them without a
lookup at all: `w`/`h` is the gender (waifu/husbando) and the second letter the roulette (`a`
Animanga, `g` Game), so `wa` is a woman in the Animanga pool and `hg` a man in the Game one.
`scripts/backfill_character_traits.py` derives both from the catalog, idempotently and without
touching `updated_at` (it is not a user edit); a `$im` lookup remains the authority where the two
disagree.

The Edit form also sets them by hand, using the same four toggles as the Add form. That path is
deliberately **exact**, not merge-only: `db.update_character` writes whatever the editor holds,
including clearing a gender or emptying `pools`, where `set_character_traits` and a `$im` refresh
never clear. The distinction is the source — a card that arrived sparse is not evidence, but a
person pressing Save is. An edit stays on the working row (`is_female`, `is_male`, `pools`); the
catalog's facets are the scrape and are left alone, so search filtering still reads the catalog.

### A hand-picked accent override

The measured accent is the dominant chromatic colour the art agrees on. It is occasionally wrong
in a way no statistic can fix: the colour a community reads as a character's is sometimes not the
one with the most pixels. Audrey Hall is blonde-haired and green-dressed, and gold wins on area,
in every variant of the pooling tried — mass-pooled, per-image top-K vote, coarse hue buckets.

So the accent can be **overridden**: a moderator or the owner arms a picker on the character page
and clicks a pixel on the portrait or a gallery image, and that colour becomes the character's
(one endpoint, saved on the click). The pick is taken server-side, from the thumbnail file or the
portrait URL keyed by row id — the client sends only the point within the image, never a URL — so
the sample is the actual pixel that was clicked.

Two design choices worth holding:

- **Write-through, one source.** The override is written to `accent_override` *and* to
  `accent_seed`, so the many read paths that already show a character's colour (the list, saved
  rows, the gallery) need no change. `accent_override` is the flag; `accent_extract` returns it
  and refuses to recompute over it, including the batch `recompute_accents.py`. Clearing nulls
  both, and the next visit measures afresh.
- **Staff-only.** The accent is one value on the character row that every visitor sees, so it is
  not a per-identity preference. Everyone else keeps the measured colour.

The picks are also the calibration set for any future rework of the extractor: each one is a real
character with a human-chosen target, which is exactly what a threshold search or a small model
would need. The remaining open problem is the opposite direction — inferring the *subject* colour
when a dominant background or hair out-votes it — for which foreground segmentation is the
promising route, not more colour statistics.

The full history of the extractor — every idea tried, every version reverted, and the numbers
behind each — is in **[ACCENT.md](ACCENT.md)**. Read it before changing the accent logic.

### Bulk-adding a series: one DM, then review

Bulk-adding used to run `$ima` for the series and then one `$im` per character, which is both slow
(one Discord interaction per character) and blind (it writes as it goes). `$imartsmi- <series>` does
the whole job in one command: Mudae DMs the account the full roster with claim ranks, pools and
`mudae.net` portrait URLs, split across as many messages as the list needs. The flow is now fetch,
review, apply:

- **Fetch** runs one `$imartsmi-` call; `$ima` is never sent. The DM parts are collected until the
  header's total is reached or the messages stop arriving.
- **Review** shows the roster split into "not in the library" and "already in the library", with the
  fields applying would change. Nothing is written yet.
- **Apply** creates the missing characters and updates the existing ones. It writes only the fields
  that differ (series, rank, portrait), so re-running an unchanged series is a no-op. Portraits are
  the DM's `mudae.net` URLs, written directly with no ImgChest upload — the same rule the catalog
  add uses.

The parser is separate from the paste parser because the DM format is different: a header without
the ` - ` separator (`Lord of the Mysteries   0/55`), then alias lines, pool totals and value stats
around the character lines. Only the header and the `#rank - Name · ($pools) - url` lines carry
data, so an alias block never becomes a parse failure.

### The self-bot is a liability, so Mudae is optional by design

The Discord integration is a **self-bot**: it signs in as the operator's own account
(`DISCORD_USER_TOKEN`) and drives `$im` / `$imartsmi-`. Automating a user account is against
Discord's ToS, and a user account does not run in an app sandbox — the failure mode is the account
itself.

**What a ban would cost.** Every Mudae-backed feature dies at once: looking a character up instead
of typing it in, "update main image from Mudae", and the one-command series fetch. Rank and pool
refreshes stop too. Nothing else does — browsing, uploads, ImgChest, the catalog, moderation and the
portrait mirrors are all independent of Discord, and Mudae portraits already mirrored to R2 keep
being served. The blast radius is bounded because the integration was kept a *metadata fetcher*
rather than a data source (see "The Mudae catalog"): the catalog is its own table, seeded in bulk,
and the self-bot is not on any request path that a normal visit takes.

**Decisions taken because of that:**

- **A dedicated process owns the connection.** `mudae_service.py` is the only
  thing that signs in; the web workers forward jobs over a Unix socket. This is
  not only tidiness — gunicorn's two workers each had their own lock, so two
  Mudae requests could connect at once, and every lookup paid a fresh Discord
  *identify*. One process serializes for real, and the token lives in one unit's
  environment instead of the whole API's.
- **Keep it off, not always on.** The client connects when a job arrives and
  disconnects once the queue has been empty for `MUDAE_IDLE_SECONDS` (10
  minutes). A permanently-online user account is the most visible thing a
  self-bot can be; an intermittent one that appears only while someone is
  curating is quieter, and the cost is a single identify on the next lookup.
- **Queue, don't refuse.** Jobs wait in a short FIFO queue (4 deep) rather than
  the old "another request is in progress" refusal, since the realistic case is
  one person clicking twice. Past the cap the request is refused with a 503, and
  a job that cannot start in time fails fast rather than holding a worker.
- **Move it to a throwaway account when convenient.** The token belongs to the
  operator's personal account today, which is exactly the account a ban would
  hurt most. A dedicated alt contains the damage; it is not urgent, but it is the
  intended end state.
- **Assume a silent format change.** Mudae has no API and its embeds are
  reverse-engineered, so a parse failure is treated as expected, logged with the
  raw reply, and surfaced as "its format may have changed" rather than a blank
  refusal — the next thing to check when a lookup stops working.

---

## 9. The visual design system

**Problem.** The owner's assessment, unprompted: the UI "feels very cheap and doesn't give a sense
of robustness at all, instead it feels like something made casually not at all like a proper website
you would expect for something serious." That judgement was correct, and the causes were specific
rather than a matter of taste — the diagnosis is in `ROADMAP.md` Phase 11.

**Register: a dense, restrained tool.** Considered and rejected:

- *An editorial gallery* — generous whitespace, large type, images as the primary surface. More
  distinctive, but lower density fights the model the moderation design is built on: visitors treat
  a character page as a **menu** they pick one to three images from and leave. Fewer images per
  screen makes a longer menu worse, and the menu is expected to get longer.
- *A warm, characterful product* — a defined accent with personality, softer geometry, a display
  face, small moments of motion. Rejected because the content is anime character art, which is
  already extremely colourful. Chrome with its own personality competes with it; chrome that
  recedes lets it carry the page. The same reasoning moved the accent off Bootstrap blue to a
  teal-cyan and dropped the accent colour from search-result titles.

So: hairline borders rather than soft drop shadows, flat surfaces with elevation reserved for
genuine overlays, tight tracking on headings, colour carrying state and meaning only.

**Light and dark are equal.** Neither was designed first. Both derive from one token set and the
site follows `prefers-color-scheme` by default, which it previously did not do at all. The
alternative — keeping light canonical and deriving dark from it — was rejected because that is
exactly how the site ended up with 144 hand-written `body.dark-mode` override selectors: dark as an
afterthought applied on top rather than a peer of light.

**Impeccable was evaluated, skipped, and later adopted.** `impeccable.style` is a design skill
pack for AI coding agents — 23 commands, an anti-pattern list, and 61 deterministic detector
rules; genuine, widely adopted, Apache-2.0. It was initially not adopted, for one reason: its
leverage is highest when there is a design system for it to align things to, and there was none.
Running its polish commands against 2874 lines of ID-selectored legacy CSS would have produced
scattered local improvements that immediately drifted apart again.

It was revisited once the system existed, exactly as anticipated, and is now installed as a
hooks-free skill under `.claude/skills/impeccable` (the `critique` output it produced is kept in
`.impeccable/critique/`). The install deliberately avoids `npx impeccable install`, which
downloads a binary into `~/.impeccable/bin/` and installs hooks that run on every file edit.

**Sequencing: foundation before Phase 6, surface after.** The token layer and the primitives are a
pure refactor with no rework risk, and they make Phase 6's new controls — ownership badges,
hide-for-me, report — cheap to build correctly. The CharacterPage gallery and the home page
information architecture waited until Phase 6 had settled what each gallery item must show, and
both have since been rebuilt (ROADMAP Phase 11) — the gallery as justified rows with three modes,
the home page as a set of library-drawn sections.

---

## 10. Smaller decisions

- **The 1000 committed PNGs stay for now.** They are default main images for the top 1000
  characters by rank, not custom images users take away, so their value is low. They move to R2
  and eventually to ImgChest, but not as a blocker for the rework.
- **The new repository is created by the operator**, not generated here.
- **The commit-`dist` CI workflow is deleted** _(done)_ once the frontend moved to Cloudflare
  Pages. It existed solely because the DigitalOcean Python buildpack could not build a frontend,
  and that constraint disappeared with DigitalOcean. `.github/workflows/` is gone and `dist/` is
  no longer committed.
- **Mudae parsing stays as-is.** It is fragile reverse-engineering of embed output, but there is no
  alternative interface — Mudae has no API. The realistic mitigation is good error reporting when
  parsing breaks, not a better parser.
