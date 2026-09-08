# Roadmap — v2 Rework

Everything to be done, grouped by area and roughly ordered by dependency. Rationale for the
larger decisions is in `DECISIONS.md`; the description of what exists today is in
`CURRENT_STATE.md`.

Phases 0-4 are the fundamentals and should be done in order — each one makes the next safe.
Phases 5 onward are largely independent of each other.

---

## Phase 0 — Runtime and toolchain — **COMPLETE**

Nothing downstream is trustworthy until the environment is reproducible and one Python version is
agreed on. On arrival four sources disagreed (`.python-version` 3.13, the venv 3.14.6, the
Dockerfile 3.11, pyright 3.11), there was no lockfile, and 8 of 10 dependencies had no upper bound.

- [x] **Adopted `uv`.** `pyproject.toml` + `uv.lock` replace `requirements.txt`. `uv sync --locked`
      verifies the lockfile matches.
- [x] **Standardised on Python 3.13.** Verified empirically first: `discord.py-self==2.1.0` — the
      pinned, unmaintained dependency and the most likely thing to break — installs and imports
      cleanly on 3.12, 3.13 **and** 3.14, so the choice was free. 3.13 chosen for its long support
      window; 3.14 is a poor bet for a project pinned to an unmaintained library.
- [x] **All dependencies now carry upper bounds.** `flask>=2.0` would have accepted Flask 4.0.
- [x] **Dropped `protobuf`.** Transitive via `discord.py-self`; verified protobuf 7 works with
      `discord_protos`, so the old `<7` bound was a forward-guard, not a known break.
- [x] **Added `ruff`.** 42 safe fixes applied; the codebase is formatted. `pyrightconfig.json`
      folded into `pyproject.toml`, and `pyright` is now an actual dev dependency.
- [x] **Rebuilt the `Dockerfile`** on `python:3.13-slim`, installing from `uv.lock` with
      dependencies in their own cache layer, and `npm ci` instead of `npm install`.
- [x] **Upgraded all four frontend majors:** React 18→19, react-router-dom 6→7, zustand 4→5,
      Vite 5→8 (plugin-react 6). Done one at a time with a build check after each. **npm audit is
      now clean** — all 5 vulnerabilities gone.
- [x] **Added `biome`** (`biome.jsonc`). 226 findings triaged down to 19 real ones by disabling
      three noisy rule sets, with the reason for each recorded in the config. Safe fixes applied.
- [x] **Adopted TypeScript incrementally.** `tsconfig.json` with `allowJs: true` and
      `checkJs: false`, so existing `.js`/`.jsx` keep working untouched and only converted files
      are checked. `src/types.ts` holds the current API shapes and is the first thing Phase 3
      updates.
- [ ] **Remove `flask-compress`** once Cloudflare is in front; the edge does Brotli, which beats
      gzip, and origin-side compression just burns CPU. **Deliberately not done yet** — it must not
      land before the CDN (Phase 5).

Keep `flask-cors`: once the SPA is on Pages the API is genuinely cross-origin, and cookie identity
makes CORS subtle enough (no `*` with credentials) that hand-rolling it is a mistake.

### Deliberately deferred out of Phase 0

- **The Biome format sweep across `src/`.** Unlike Python formatting, reformatting JSX rewraps
  markup and inserts `{' '}` to preserve whitespace. With no test suite yet and
  `CharacterPage.jsx` due to be split in Phase 10, the risk/benefit is wrong right now. The
  formatter is configured and matches the existing style (single quotes, no semicolons, 2-space);
  run `npm run format` as part of Phase 10, when the files are being rewritten anyway.
- **16 ruff and 19 biome findings that need judgement** (`SIM102`, `SIM103`, `B904`, `E741`,
  `useParseIntRadix`, `noArrayIndexKey`, `useExhaustiveDependencies`). These alter logic, so they
  wait for the Phase 1 test harness.

### Verified

`uv sync --locked` clean; `ruff format --check` clean; gunicorn boots on 3.13 and serves
`/api/health` and the SPA shell; frontend builds; `tsc --noEmit` passes; the served page
references the new bundle, the bundle returns HTTP 200 as `text/javascript`, and the SPA
deep-link fallback (`/character/Rem`) returns 200.

---

## Phase 1 — Test harness — **COMPLETE**

**This was originally Phase 7, and that was an ordering error.** The headline test —
"concurrent adds to one character both persist" — is the acceptance criterion for the data-layer
rewrite in Phase 2. Without it there is no way to prove the data-loss bug is actually fixed, so it
had to come first.

- [x] **`pytest`** on the backend, **`vitest` + `@testing-library/react`** on the frontend.
- [x] **The concurrency test is written and it fails**, exactly as predicted: with two threads
      forced to interleave by a barrier, one image is silently lost. The bug is now demonstrated
      rather than argued. It carries `@pytest.mark.xfail(strict=True)`, so the suite stays green
      *and* the bug cannot be quietly fixed and forgotten — when Phase 2 lands, the test XPASSes,
      which **fails the suite** until the marker is removed.
- [x] **Production-database guard.** `upload_imgchest.py` calls `load_dotenv()` at import time and
      `.env` holds the live Neon URL, so an unguarded test run would write to real user data.
      `tests/conftest.py` overwrites `DATABASE_URL` at collection time — before any application
      module is imported — and refuses to run against a non-local host or a known managed-database
      hostname. All three behaviours are verified, including that `load_dotenv()` does not override
      a pre-set variable.
- [x] **Zero-setup test database.** If `TEST_DATABASE_URL` is unset, the harness starts a throwaway
      `postgres:16-alpine` container via podman and reuses it between runs.
- [x] **Frontend tests worth having, not just a smoke test.** 21 tests covering the `$ai` command
      splitter (every part within Discord's limit, every part independently pasteable, no URL ever
      split or lost — asserted across a sweep of limits) and download filename de-duplication.
      These cover both functions where Phase 0's `let`→`const` fixes landed. A `Toast` component
      test proves React 19 + testing-library 16 + zustand 5 work together after the upgrades.
- [x] **`docs/DEVELOPMENT.md`** records the commands and the conventions behind them.

### Still to cover, as the features land

Ownership rule, report thresholds, dedupe, and role permissions — see the Testing detail section
below. Those tests are written alongside the phases that introduce the behaviour.

### Verified

`uv run pytest` → 2 passed, 1 xfailed. `npm test` → 21 passed. Both documented commands were run
as written; `pythonpath = ["."]` was added to `pyproject.toml` after `uv run pytest` turned out to
fail where `python -m pytest` succeeded (the entry point does not add the CWD to `sys.path`).

---

## Phase 2 — Data layer — **COMPLETE**

Fixed the silent data loss. `db.py` previously held one module-global psycopg2 connection with
`autocommit = True` and no transaction anywhere, so concurrent read-modify-writes of the JSONB
document lost data.

- [x] **Moved to `psycopg` 3 with `psycopg_pool`.** The pool replaces the single global connection,
      its lock, and its keepalive thread — it hands out only verified-alive connections, so a
      database restart surfaces as a retry rather than an error.
- [x] **Every read-modify-write is now one transaction**, holding a Postgres advisory lock across
      the read and the write.
- [x] **There is no public setter any more.** `set_custom_images`, `set_saved_characters`,
      `set_last_updated` and `_set_characters_raw` are gone. The only way to write is `mutate_*`,
      which takes a function that edits the document in place. The unsafe pattern is not merely
      discouraged, it is **unavailable** — which is what stops it being reintroduced later.
- [x] **All 11 call sites migrated** across `upload_imgchest.py` and `scripts/`, including the
      rename cascade in `edit_character`.
- [x] **The Phase 1 concurrency test is green** and the `xfail` marker is gone. Two stronger tests
      were added: 20 concurrent adds to one key lose nothing, and concurrent writes to *different*
      keys neither serialise nor deadlock.
- [x] **13 endpoint tests** pin the status codes, since the rewrite changed the control flow — the
      mutator now reports *why* it failed so the route can still return 404 vs 400 vs 200.
- [x] **Pool shutdown is clean.** Registered an `atexit` handler after finding that gunicorn worker
      restarts otherwise stalled ~5s per pool thread, logging `couldn't stop thread ... within 5.0
      seconds`. Verified zero warnings on SIGTERM.

### Behaviour change worth knowing about

**Reorder no longer discards concurrent uploads.** It used to assign the client's `new_order`
wholesale, so any image added between page load and submit was silently deleted. It now applies the
requested order to images that still exist and appends any it did not know about. Covered by
`test_keeps_images_added_after_the_client_loaded_the_page`.

### Note on the advisory lock

It serialises writes per *key*, not per character — every custom-image write contends with every
other. At this scale that is the right trade: simple and obviously correct. Phase 3 replaces the
blob with one row per image, after which writes stop contending at all and the lock can go.

### Verified

`uv run pytest` → 18 passed. `npm test` → 21 passed. Gunicorn with 2 workers serves reads and
writes against the pool, and shuts down cleanly on SIGTERM.

---

## Phase 3 — Data model — **COMPLETE**

JSON documents replaced by tables, on SQLite. Engine and shape settled in
`DECISIONS.md` §8.

- [x] **Moved to SQLite.** `sqlite3` is stdlib, so `psycopg` left the runtime dependencies
      entirely — it survives only in the dev group, for the one-time read of the v1 database.
      Per connection: `foreign_keys = ON` (SQLite ignores `REFERENCES` without it),
      `journal_mode = WAL`, `busy_timeout = 5000`, `synchronous = NORMAL`.
- [x] **Eight tables**, in `migrations/001_initial.sql`, applied in filename order and recorded in
      `schema_migrations`. Verified that foreign keys, `CHECK` constraints and
      `UNIQUE (character_id, url)` all actually enforce.
- [x] **Surrogate id for characters.** The 67-line rename cascade in `edit_character` is **gone** —
      images, bookmarks and the timestamp all hang off `characters.id`, so `update_character` is
      the entire rename.
- [x] **`last_updated` became `characters.updated_at`.** Deliberately **nullable**: NULL means
      "never modified", matching v1, where untouched characters were absent from the map and sorted
      last. A `NOT NULL DEFAULT now` would have made 775 never-touched characters appear as the
      most recently updated.
- [x] **Bookmarks are per-identity.** The v1 global list turned out to be empty, so nothing had to
      be reassigned. `LEGACY_IDENTITY_ID` bridges until Phase 6 supplies a real identity.
- [x] **Advisory lock dropped.** Two inserts into `custom_images` do not contend; there is nothing
      left to serialise.
- [x] **Migration script**, idempotent, against the real 660 KB export.
- [x] **Test harness simplified.** The podman/PostgreSQL container is gone; each run gets a
      temporary SQLite file. The guard survived in a new form and all three behaviours are
      verified.
- [x] **Per-character reads are targeted.** `/api/custom-image/<name>` was loading every
      character's images and discarding all but one — an artifact of the document layout.

### What the real data taught us

Running against the live export found things no synthetic fixture would have:

- **`Levy McGarden` existed twice** — once seeded (rank `788`, local filename) and once re-added
  through Add Character (no rank, ImgChest URL). `UNIQUE (name)` would have rejected the second.
  Merged last-non-empty-wins, keeping both halves.
- **`deletesoon`** is a `last_updated` key with no character. Skipped and reported.
- **775 of 1,705 characters have no timestamp at all**, which is what forced `updated_at` to be
  nullable.
- **14 characters had empty image lists.** v1 served `"Flamme": []`; v2 omits the key. Benign —
  the frontend computes `?.length || 0` and the stat already filtered `length > 0`.
- Names contain apostrophes (`Jeanne d'Arc`) and non-ASCII (`Hange Zoë`, `Übel`); verified intact
  end to end over HTTP.

### A bug written and caught inside this phase

`_ensure_character` was implemented as check-then-insert, which is a race: two threads both see the
name missing, both insert, one dies on the UNIQUE constraint.
`test_many_concurrent_adds_all_persist` caught it immediately. Both occurrences were replaced with
`INSERT ... ON CONFLICT DO NOTHING`. This is the same read-modify-write hazard Phase 2 removed,
in a different shape — worth remembering that fixing a class of bug in one place does not stop it
reappearing in another.

### Verified

Migration: 1,706 → 1,705 characters (one merge), **all 8,547 images**, image order preserved for
all 721 characters, 930 timestamps applied, zero orphans, idempotent on re-run, 2 MB file. Suite:
19 passed. Gunicorn with 2 workers serves the migrated data — 1,705 characters, a 256-image
gallery, unicode and apostrophe names — and shuts down cleanly.

---

## Phase 4 — Concurrency and worker model — **COMPLETE**

Deliberately sequenced after Phase 2/3: raising concurrency while writes could still lose data
would have produced *more* collisions, not fewer.

- [x] **Switched to `gthread`.** Settings moved into `gunicorn.conf.py`, which explains each
      choice, with `WEB_WORKERS` / `WEB_THREADS` / `WEB_TIMEOUT` overrides so the same image suits
      a home server or a cloud VM. Default: 2 workers × 8 threads = 16 concurrent requests, up
      from 2.
- [x] **Not gevent.** It monkey-patches sockets, which conflicts with the `asyncio.run()` Discord
      client. `gthread` patches nothing.
- [x] **The 120-second SSE kill is fixed**, as a side effect rather than by raising the timeout. A
      *sync* worker only reports to the master between requests, so any response longer than
      `timeout` was killed mid-flight; a *gthread* worker reports from its accept loop,
      independently of what its threads are serving. The timeout still does its real job of
      catching a wedged process.
- [x] **`max_requests` with jitter**, so a slow leak in the image pipeline cannot grow unbounded.

### Measured, not assumed

| | result |
|---|---|
| 12s response, `--timeout 5`, **sync** | killed at 5s, `WORKER TIMEOUT`, worker rebooted, output truncated |
| 12s response, `--timeout 5`, **gthread** | completed in full, no timeout |
| 8 concurrent 3s requests, **sync, 2 workers** | **23.3s** (serialised; theoretical worst case 24s) |
| 8 concurrent 3s requests, **gthread, 2×8** | **3.0s** (the theoretical floor) |
| Real app, 16 concurrent reads | all 200 |
| Real app, 12 concurrent writes to one table | all 200, all rows persisted, no "database is locked" |

### This is a mitigation, not the cure

A series import still does minutes of work inside a single web request. Sixteen threads means
sixteen slow imports before the site stalls instead of two — better, but the same shape of problem.
The cure is Phase 8: the request starts a job and returns immediately, a background process does
the work, and the page polls for progress. Nothing then holds a request open for minutes, and the
timeout question disappears entirely rather than being worked around.

---

## Phase 5 — Hosting migration — **CODE COMPLETE, provisioning outstanding**

Everything the repository can do is done. What remains needs your Cloudflare account, a domain and
an origin box, and is written out step by step in `docs/DEPLOYMENT.md`.

### Done in the repository

- [x] **The frontend can live on a different origin.** `frontend/src/config.js` centralises
      `VITE_API_BASE_URL` and `VITE_IMAGE_BASE_URL`; `api.js` and `downloadCustomImages.js` no
      longer assume same-origin. Both were hardcoding `/api/...` and `window.location.origin`.
- [x] **`credentials: 'include'` everywhere**, replacing `'same-origin'`. This is the subtle one:
      once the SPA is on Pages, `'same-origin'` silently stops sending cookies, so the Phase 6
      identity cookie would fail as "everyone is a new person on every request" rather than as an
      error.
- [x] **CORS hardened for credentialed cross-origin.** `CORS_ORIGINS=*` is now **refused at
      startup** — browsers reject credentialed requests against a wildcard, so failing loudly at
      boot beats failing silently in someone's browser. Unset means same-origin only.
      *(This also completes the CORS item listed under Phase 7.)*
- [x] **Deployment artifacts** in `deploy/`: `litestream.yml`, `imgmanager.service` (Litestream
      supervising gunicorn, so replication cannot be running-but-not), `cloudflared-config.yml`,
      and `upload-character-images-to-r2.sh`.
- [x] **`docs/DEPLOYMENT.md`** replaces the DigitalOcean `DEPLOY.md`, which is deleted.
- [x] **13 new tests** pinning the contract: 7 on the frontend config (credentials mode, base-URL
      joining, image URL resolution) and 6 on CORS, including that the app refuses to start on a
      wildcard.

### Outstanding — needs your accounts

- [ ] Create the R2 buckets (assets + backups) and a custom domain for the assets one.
- [ ] Upload `character_images/` to R2 with `deploy/upload-character-images-to-r2.sh`.
- [ ] Choose and provision the origin box: **Oracle Cloud Always Free** or the **home server**.
      Cloudflare Tunnel makes them interchangeable, so this stays a late, reversible decision.
- [ ] Set up the Tunnel, install the systemd unit, and generate a **permanent** `SECRET_KEY`.
- [ ] Create the Pages project and set the two `VITE_*` build variables.
- [ ] Run the migration on the origin, cut DNS over, **verify a Litestream restore actually
      works**, and only then decommission DigitalOcean and Neon.
- [ ] **Remove `flask-compress`** once Cloudflare is in front — the edge does Brotli, which beats
      gzip, and origin-side compression then only burns CPU. Not before.

---

## Phase 6 — Identity and moderation

The design is settled in `DECISIONS.md` §1, §4, §5. This is implementation only — if something
here seems wrong, read the rationale before changing it.

- [ ] **Cookie pseudonym identity.** A signed cookie (via `itsdangerous`, already a Flask
      dependency) carrying a stable id, issued on first visit with a generated
      adjective-plus-animal handle. Attach to `flask.g`; set it in an `after_request` hook. No
      login screen, ever.
- [ ] **`SECRET_KEY` becomes required.** It is currently set and never read. Once it signs identity
      cookies, a changed or missing key silently turns every user into a new person on restart.
      Validate at startup; document as a required secret.
- [ ] **Optional Discord OAuth.** Binds an existing pseudonym to a real Discord account so identity
      survives cookie loss. **Requires registering a new Discord application** —
      `DISCORD_USER_TOKEN` is a self-bot token and cannot be used for OAuth. New vars:
      `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `OWNER_DISCORD_ID`.
- [ ] **Roles.** `user` / `moderator` / `owner` on `identities.role`. Owner bootstrapped by
      matching `OWNER_DISCORD_ID` at login. Moderators can remove any image and restore from the
      drawer; the owner can also promote and demote. **A fallback, not the primary mechanism.**
- [ ] **Ownership rule on delete.** `POST /api/delete-custom-images` removes only rows where
      `added_by` matches the caller (or the caller is moderator/owner). Sets `state='removed'`
      rather than deleting. Returns per-image results so the UI can explain partial refusals.
- [ ] **Hide-for-me.** `POST /api/hide-images` and `/api/unhide-images`, writing `user_hidden`.
      Instant, unlimited, no global effect whatsoever.
- [ ] **Report.** `POST /api/report-image` with a reason from `wrong_character | dead_link | nsfw |
      duplicate`. On the second *distinct* reporter, set `state='removed'`. Objective criteria
      only — never taste.
- [ ] **Removed drawer.** `GET /api/removed/<character>` and `POST /api/restore-image`, restorable
      by anyone. Nothing is ever hard-deleted.
- [ ] **Take logging.** `POST /api/takes` fired by Download and Copy `$ai`. Logged, but **drives
      nothing** except the optional sort. Deliberate — see `DECISIONS.md` §1.
- [ ] **Frontend rework of delete mode.** Your own images get **Remove**; others' get **Hide**.
      Mixed selections show both counts. Owner handle on hover. Hidden images filtered out with a
      "Show N hidden" toggle. Report action in the image modal. **Add a confirmation step to bulk
      removal** — there is none today.
- [ ] **Fix the undo path.** The current 8-second undo calls `reorderCustomImages` to write a stale
      array back wholesale, clobbering anyone else's concurrent edits. Point it at
      restore/unhide instead.

---

## Phase 7 — Security

Independent of the above and worth doing early. A script can currently empty the entire library.

- [x] **Lock down CORS.** _(done in Phase 5)_ `*` is now refused at startup, unset means
      same-origin only, and an explicit allowlist is required. Splitting the frontend onto its own
      origin forced this to be correct rather than merely tightened.
- [ ] **Per-identity rate limits** on add, hide, and report. There is nothing at all today.
- [ ] **Auto-cooldown** for an identity reporting or hiding at an implausible rate.
- [ ] **Re-audit the SSRF guards** (`_safe_import_image_url`, `_host_resolves_only_to_public_ips`)
      after the move — they matter more on a self-hosted box sitting inside a home or cloud
      network than on managed infrastructure.

---

## Phase 8 — Mudae hardening

- [ ] **Move Discord work to a single dedicated process or queue.** The guarding `threading.Lock`
      is process-global while gunicorn runs 2 workers, so two concurrent Mudae requests on
      different workers both connect. One worker, or an external queue, makes the lock mean
      something.
- [ ] **Consider a persistent connection.** The current connect-per-request pattern burns one
      Discord *identify* per lookup against a cap of roughly 1000/day. A long-lived client in the
      dedicated process removes that entirely.
- [ ] **Document the self-bot ToS risk and the fallback.** Automating a user account can get it
      banned, taking out every Mudae feature. Decide in advance what happens then.
- [ ] **Better failure reporting when embed parsing breaks.** Mudae has no API, so ~40 helpers
      reverse-engineer its embed output and will break when Mudae changes. A clear error beats a
      silent wrong answer.

---

## Phase 9 — Performance

- [ ] **Kill the full-map fetch.** `GET /custom_images.json` returns every image URL for every
      character, and `HomePage` downloads all of it to compute two numbers. Replace with an
      `/api/stats` endpoint plus per-character fetches.
- [ ] **Adopt `@tanstack/react-query`.** Retry, backoff, and cache invalidation are currently
      hand-rolled and duplicated across `useStore.js` and `api.js`. Its per-character caching is
      also what makes killing the full-map fetch practical. Keep zustand alongside it — react-query
      owns server state, zustand keeps owning UI state (dark mode, toasts, selection). They are
      complementary, not competing.
- [ ] **Serve character images from the CDN**, not from Flask off local disk (follows from R2).
- [ ] **Reconsider gzip.** `flask-compress` runs on the origin; with Cloudflare in front, the edge
      can handle compression instead.

---

## Phase 10 — Structure and code quality

- [ ] **Split `upload_imgchest.py`** (1386 lines, the entire app) into blueprints: `images`,
      `characters`, `mudae`, `auth`.
- [ ] **Split `CharacterPage.jsx`** (1178 lines) and `AddPage.jsx` (617 lines).
- [ ] **Structured logging** replacing `print(..., flush=True)` throughout, with identity attached
      to mutation logs — the beginnings of a real audit trail.
- [ ] **A health check that touches the database.** The current one returns a static dict and
      reports healthy with a dead database.
- [x] **Delete dead code:** _(done)_ `character_mapping.js` (260 KB, zero references),
      `github_utils.py` (a single never-called function, left over from when data lived in a
      GitHub file instead of Postgres), `frontend/src/hooks/useMediaQuery.js` (exported, never
      imported), and `.cursor/plans/ideal_architecture_v2.plan.md` (916 lines superseded by
      `DECISIONS.md`; it assumed a paid DigitalOcean Droplet and contradicted the free-hosting
      decision).

---

## Testing detail (harness set up in Phase 1)

The harness goes up in Phase 1. These are the rules worth covering, in the order they become
relevant — the concurrency test is written first, before Phase 2:

- [ ] Removing another identity's image is refused; removing your own succeeds and sets
      `state='removed'`.
- [ ] Hiding an image changes nothing for a second identity.
- [ ] The second *distinct* report removes; a second report from the *same* identity does not.
- [ ] Duplicate URL and duplicate content hash are both rejected on add.
- [ ] **Concurrent adds to one character both persist** — this fails on the current architecture
      and is the regression test for the Phase 2 data-layer rewrite. Write it in Phase 1.
- [ ] Moderator and owner can remove others' images; a plain user cannot.

---

## Deferred / future

- **ImgChest mirror.** A second copy of every image in R2 or similar, so the library survives
  ImgChest losing files or shutting down. Explicitly a **backup, not a replacement** — the
  ImgChest URL stays canonical because Mudae accepts nothing else (`DECISIONS.md` §2).
- **Move the 1000 character PNGs to ImgChest** and drop them from the repo entirely.
- **Per-user saved selections and personal ordering.** Deliberately deferred; hide-for-me is the
  minimum that solves the actual problem.
- **Revisit retirement policy with real take data.** Take counts are being logged from Phase 6
  onward precisely so this can eventually be designed against evidence rather than guessed at. Do
  not build a retirement mechanism before there is data — see the rejected approaches in
  `DECISIONS.md` §1.
