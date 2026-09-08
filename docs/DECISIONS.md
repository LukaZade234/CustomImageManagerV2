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
duplicate — and every one of those has a right answer that requires no consensus at all.

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
4. **Nothing is ever destroyed.** Removals are soft; a Removed drawer restores in one click. This
   is nearly free because ImgChest never deletes the underlying file (see §2).
5. **Take counts are logged but drive nothing**, except an opt-in "sort by popular" toggle.
   Collecting them costs nothing and commits to nothing, and it means that if bloat ever does
   become real, there will be months of actual data to design against instead of another guess.
6. **Moderator and owner accounts exist as a manual fallback only** — explicitly not the primary
   mechanism, and not something the operator should need to use routinely.

Worked example — the exact scenario that motivated all of this. Someone opens a character with 10
images and wants only their own. They click remove on all 10: each is hidden **for them**, nothing
changes globally, nobody else notices. They upload their 8. The pool goes from 10 to 18. They see
exactly the gallery they wanted; everyone else is untouched; the library **grew instead of
churning**; and the operator never opened the site.

### Non-goals

- Deciding what is "worthy." Nothing in the system makes that judgment, deliberately.
- Routine human moderation. If the design requires the operator to check the site regularly, it
  has failed.

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
would, and edge databases would optimize the hop that is already cheap. PostgreSQL runs on the
same box as the origin, with `pg_dump` backups to R2 on a cron.

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
structures. `characters`, `saved_characters`, and `last_updated` can stay in the KV store — they
are not the problem.

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
caching, retry, invalidation — replacing retry and backoff logic currently hand-rolled and
duplicated across `useStore.js` and `api.js`. zustand keeps owning **UI** state: dark mode, toasts,
selection. Its per-character caching is also what makes killing the full-map fetch practical.

### Dependencies dropped, and one deliberately kept

- **`protobuf`** — declared directly but never imported by our code; it is transitive via
  `discord.py-self`. Pinning another package's transitive dependency only creates future conflicts.
- **`flask-compress`** — removed *once Cloudflare is in front*, not before. The edge does Brotli,
  which beats gzip, so origin-side compression would just burn CPU on a box we are paying for in
  uptime.
- **`flask-cors` is kept.** It looks droppable, but once the SPA is on Pages the API is genuinely
  cross-origin, and cookie identity makes CORS subtle — `*` is invalid with credentials.
  Hand-rolling that is how it gets done wrong.

### TypeScript: open

`@types/react` and `@types/react-dom` are installed although the project contains no TypeScript.
The decision is deliberately left open, but the timing is not: adopting TS is cheapest immediately
before the 1178-line `CharacterPage.jsx` and 617-line `AddPage.jsx` get split, and considerably
more expensive after. Either commit then, or remove the unused type packages.

The same timing argument applies to the frontend major upgrades (React 18→19, react-router 6→7,
zustand 4→5, Vite 5→8, which also clear 5 npm vulnerabilities): do them while the components are
still whole and a test harness exists to catch regressions.

---

## 8. Smaller decisions

- **The 1000 committed PNGs stay for now.** They are default main images for the top 1000
  characters by rank, not custom images users take away, so their value is low. They move to R2
  and eventually to ImgChest, but not as a blocker for the rework.
- **The new repository is created by the operator**, not generated here.
- **The commit-`dist` CI workflow gets deleted** once the frontend moves to Cloudflare Pages. It
  exists solely because the DigitalOcean Python buildpack cannot build a frontend, and that
  constraint disappears with DigitalOcean.
- **Mudae parsing stays as-is.** It is fragile reverse-engineering of embed output, but there is no
  alternative interface — Mudae has no API. The realistic mitigation is good error reporting when
  parsing breaks, not a better parser.
