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

## Phase 5 — Hosting migration — **DEPLOYED**

Live on `lukazade.dev`. The v1 site on DigitalOcean and Neon is still running and is
**still the one users are on** until cut-over.

### Done in the repository

- [x] **The frontend can live on a different origin.** `frontend/src/config.js` centralises
      `VITE_API_BASE_URL` and `VITE_IMAGE_BASE_URL`; `api.js` and `downloadCustomImages.js` were
      both hardcoding `/api/...` and `window.location.origin`.
- [x] **`credentials: 'include'` everywhere**, replacing `'same-origin'`. Without this the Phase 6
      identity cookie would silently stop being sent once the SPA moved to Pages.
- [x] **CORS hardened.** `CORS_ORIGINS=*` is refused at startup; unset means same-origin only.
      *(Also completes the CORS item under Phase 7.)*
- [x] **Deployment artifacts** in `deploy/`, and `docs/DEPLOYMENT.md` replacing `DEPLOY.md`.
- [x] **13 tests** pinning the contract — 7 on frontend config, 6 on CORS.

### Deployed

- [x] **Origin:** Oracle Cloud Always Free, `aarch64`, **4 OCPU / 23 GB / 43 GB free** — the full
      ARM allowance, despite London's capacity shortage. Twenty-three times the RAM v1's image
      pipeline was tuned to survive on.
- [x] **App** as a systemd service under a dedicated `imgmanager` user, gunicorn with gthread.
- [x] **Cloudflare Tunnel** → `api.lukazade.dev`. **No inbound ports are open on the VM at all**;
      `cloudflared` only dials out.
- [x] **R2:** `imgmanager-assets` (1000 character images, custom domain `images.lukazade.dev`,
      `cache-control: immutable`, served from the edge) and `imgmanager-backups` (private).
- [x] **Litestream** replicating the database to R2, supervised by systemd as gunicorn's parent.
- [x] **Cloudflare Pages** → `lukazade.dev`, building from git with the `VITE_*` variables.
- [x] **Data migrated:** 1,705 characters, 8,547 images.
- [x] **`docs/DEPLOYMENT.md` updated** with the dozen things that actually went wrong — the hidden
      Ampere tab, ARM capacity, the missing public IP, VCN-vs-VNIC, rclone's version requirement,
      the expected `ListBuckets` 403, Workers-vs-Pages, `NODE_VERSION`, and the apex CNAME
      conflict. Section ordering corrected: the Tunnel cannot be verified before the app runs.

### Outstanding

- [x] **Verify a Litestream restore before cut-over.** _(done, 2026-09-10)_ Restored from R2 into
      a scratch file on the origin: `integrity_check` ok, `foreign_key_check` clean, schema
      identical, all 11 tables matching (characters 1705, custom_images 8547), and a content hash
      over both tables identical to live. The live database was fingerprinted before and after and
      did not change. Repeatable without downtime via
      `scripts/verify_litestream_restore.sh` — re-run before the cut-over itself, since the data
      keeps moving.
- [ ] **Decide the cut-over.** Both sites are live now and **their data has forked** — anything
      added on v1 from this point does not appear on v2, and because the migration is insert-only,
      anything *deleted* on v1 is not removed from v2 either. The procedure, the rollback boundary
      and the three decisions it forces are in **[CUTOVER.md](CUTOVER.md)**.
- [ ] **Decommission** the DigitalOcean app and the Neon database, only after the above.
- [ ] **Remove `flask-compress`.** Now actionable: Cloudflare is in front and does Brotli, so
      origin-side gzip only burns CPU.

---

## Phase 6 — Identity and moderation — **COMPLETE**

The design is settled in `DECISIONS.md` §1, §4, §5. This is implementation only — if something
here seems wrong, read the rationale before changing it.

- [x] **Cookie pseudonym identity.** `identity.py`. A signed cookie (`itsdangerous`) carrying a
      stable id, issued on first visit; the handle is *derived* from the id with blake2b rather
      than stored, so it can be reconstructed anywhere without putting it in the cookie. Rows in
      `identities` are created lazily on first write — a test asserts that browsing alone leaves
      the table empty. No login screen.
- [x] **`SECRET_KEY` becomes required.** `resolve_secret_key()` refuses to start a deployed
      configuration without one and generates an ephemeral key with a warning locally. The old
      `dev-key-change-in-production` default is gone: shipped to production it would have let
      anyone forge another user's identity cookie. `CORS_ORIGINS` is the signal for "deployed".
- [x] **Optional Discord OAuth.** `discord_auth.py`, `identify` scope only. Signing in binds the
      current cookie pseudonym to a Discord account; if that account is already bound to an older
      identity, the anonymous one is **merged into it** — uploads, bookmarks, hidden set, reports
      and takes all follow — so signing in never orphans what you just added. The `next` path is
      restricted to a path on our own frontend, because accepting a full URL is how an OAuth
      callback becomes an open redirect. Needs `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`,
      `DISCORD_REDIRECT_URI` and `OWNER_DISCORD_ID`; unset means the UI simply does not offer it.
- [x] **Roles.** `identities.role` is read on every request that needs it and surfaced through
      `/api/me`. Moderator and owner both bypass the ownership check. The owner is bootstrapped by
      matching `OWNER_DISCORD_ID` at login, so no admin password exists anywhere. Promotion only
      ever promotes — signing in cannot demote an existing moderator.
- [x] **Ownership rule on delete.** `remove_custom_images` soft-deletes only rows whose `added_by`
      matches the caller, or any row for a moderator. Returns `{removed, denied, missing}` so a
      partial refusal can be explained. Images migrated from v1 have `added_by IS NULL` and so
      cannot be removed by an ordinary user at all — intended.
- [x] **Hide-for-me.** `POST /api/hide-images` / `/api/unhide-images`. Instant, unlimited, and
      invisible to everyone else; a test pins that a hide changes nothing for a second viewer.
- [x] **Report.** `POST /api/report-image`, four objective reasons, removal on the second
      *distinct* reporter. The composite primary key is what makes one determined reporter unable
      to reach the threshold alone.
- [x] **Removed drawer.** `GET /api/removed/<character>` and `POST /api/restore-images`,
      restorable by anyone. Nothing is ever hard-deleted.
- [x] **Take logging.** `POST /api/takes` on Download and Copy `$ai`. Drives nothing.
- [x] **Frontend rework of delete mode.** "Remove or hide": your images get **Remove mine (n)**,
      everyone else's get **Hide theirs (n)**, both counts always shown. Attribution on every
      image, hidden images filtered out behind a "Show N hidden" toggle, Report in the viewer, the
      Removed drawer, and a confirmation step on bulk removal that did not exist before.
- [x] **Fix the undo path.** It called `reorderCustomImages` with a pre-delete array, which could
      not restore a removed image and clobbered concurrent edits. It now calls restore.

Not done, and deliberately: **`saved` is per-identity from here on.** In v1 it was one global
list, so on cut-over the migrated bookmarks stay under the legacy identity and nobody inherits
them. There are no v2 users yet, so this costs nothing now.

---

## Phase 7 — Security

- [x] **Lock down CORS.** _(done in Phase 5)_ `*` is now refused at startup, unset means
      same-origin only.
- [x] **Per-identity rate limits.** There was nothing at all before this. `rate_limit_hits`
      (migration 002) counts *attempts* per identity per action in fixed windows; the increment
      happens before the count is read so two concurrent requests cannot both slip through. The
      limit that matters is on uploads — each one is an ImgChest call against a shared key, so an
      unbounded client can get that key throttled and take the app's purpose with it. Applied to
      15 endpoints; each action has a burst window and an hourly one, overridable with
      `RATE_LIMIT_<ACTION>="30/60,300/3600"`. Moderators get 10x, because a limit sized for a
      visitor would block the person curating the site.
- [x] **Auto-cooldown** for an identity reporting at an implausible rate — the same mechanism,
      with report deliberately the tightest limit (5/min, 20/hour) since reports can remove other
      people's work, while hiding affects nobody else and is generous.
- [x] **Re-audit the SSRF guards.** Three real gaps found and closed:
      - **IPv4-mapped IPv6** (`::ffff:169.254.169.254`) carried none of the stdlib flags and went
        straight through. Now unwrapped and judged as the IPv4 address it carries.
      - **Ranges `ipaddress` does not flag at all**: IPv6 site-local (`fec0::/10`) and RFC 6598
        carrier NAT (`100.64.0.0/10`), the latter used by cloud providers for internal networks.
      - **Only the final redirect was validated.** `allow_redirects=True` followed the chain
        itself, so public → `192.168.1.1` → public passed the check *after* the private host had
        already been fetched. Redirects are now stepped by hand with every hop validated first,
        bounded at 5.

      Residual risk, documented in the code rather than fixed: DNS rebinding. The name is resolved
      for validation and then again by `requests` when it connects, so a hostile resolver can
      answer differently each time. Closing it needs connecting to a pinned address with the Host
      header set by hand.

---

### Upload format

- [x] **Store uploads as WebP under a `.png` name.** Verified against a real Mudae card: `$ai`
      refuses a URL that does not end in `.png`, but renders whatever bytes arrive. WebP q90 is
      **121 KB against 958 KB and 39ms to encode against 76ms** — smaller *and* faster, so there is
      no trade-off between the two. It also protects resolution: the shrink loop existed because a
      PNG often would not fit ImgChest's 30 MB limit, and at an eighth of the size it now almost
      never runs.
- [x] **Decide format by magic bytes, not by filename.** The old fast path skipped conversion for
      anything named `.png`, which is how WebP files came to be stored under `.png` names and how
      858 images (10%) got past the 2048px cap — the largest is **11,036px**. Skipping conversion
      also skipped EXIF stripping, so a phone photo would have published its GPS coordinates on a
      public library.
- [x] **Name uploads meaningfully on ImgChest.** They arrived as
      `temp_custom_web_import_a1b2c3d4.png`. Now `lucy-013-20260910.png`: character, position in
      that character's gallery, and date. Main images are `lucy-main-...`.
- [ ] **Consider re-encoding the existing library.** Not viable as things stand — re-uploading
      mints new ImgChest URLs and breaks every `$ai` command anyone has already saved.

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

- [x] **Kill the full-map fetch.** `GET /custom_images.json` returned every image URL for every
      character — **486 KB raw, 81 KB gzipped** against the real library — and the home page
      downloaded all of it to display two integers. Replaced by:
      - `GET /api/stats` — **62 bytes**, the two counts.
      - `GET /api/customs?page=&per_page=&q=&by=&sort=` — one page of the browse list with counts
        and three previews per row, **7.2 KB** instead of 486 KB. Search, all seven sorts, and
        pagination now happen in SQL. The sort key is whitelisted rather than interpolated, and
        LIKE wildcards in the search term are escaped so `%` does not match everything.
      - `GET /api/saved` now returns `updated_at` per row, which retired the separate
        `/api/last-updated` fetch (**33 KB**) whose only remaining consumer was the client-side
        sort. `lastUpdated` and the library-wide `customImages` map are gone from the store.

      The old endpoint is left in place, commented as superseded, in case something outside the
      app calls it. It should be deleted once that is ruled out.

      This also unblocks growth: the plan is to seed tens of thousands of characters, at which
      point filtering the whole library in the browser stops being possible at all.
- [x] **Gallery thumbnails.** The remaining half of the payload problem. `convert_to_png()` makes
      every upload a lossless RGBA PNG averaging **1.9 MB**, and ImgChest serves no smaller
      variants (`?w=`, `?width=`, `.webp`, `_thumb` were all tested and return the identical
      full-size PNG), so smaller versions have to come from us. `thumbnails.py` renders a 600px
      WebP at ~46 KB, generated on first request and cached to disk with `immutable` headers so
      Cloudflare serves it from the edge thereafter. A first screenful of a 256-image character
      went **488 MB → 22.9 MB** (dimensions plus lazy loading) **→ 548 KB**.

      The ImgChest URL stays canonical throughout: it is what the database stores and what every
      `$ai` command, download and lightbox uses, because Mudae accepts nothing else. Only the grid
      renders WebP. Two tests pin that. GIFs are not thumbnailed — the animation is usually why the
      image was chosen.
- [ ] **Adopt `@tanstack/react-query`.** Retry, backoff, and cache invalidation are currently
      hand-rolled in the store. Less pressing now that the two heavy fetches are gone.
- [ ] **Serve character images from the CDN**, not from Flask off local disk (follows from R2).
      Generated thumbnails could move to R2 by the same route, which would also make them a
      backup rather than derived data the origin has to hold.
- [ ] **Reconsider gzip.** `flask-compress` runs on the origin; with Cloudflare in front, the edge
      can handle compression instead.

---

## Phase 10 — Structure and code quality

- [x] **Split `upload_imgchest.py`** _(done)_ — 1,717 lines down to 248. Six blueprints under
      `routes/` (`auth`, `characters`, `customs`, `media`, `mudae`, `spa`) plus `remote_images.py`,
      `ratelimit.py` and `validation.py`. Paths are unchanged; `tests/test_url_map.py` pins every
      registered route so one going missing is a test failure rather than a production surprise.
- [x] **Split `CharacterPage.jsx`** _(done)_ — 1,611 lines down to 671. The four mutually exclusive
      mode booleans became one `mode` value, and `GalleryToolbar` and `CharacterHeader` moved out
      with tests of their own. `AddPage.jsx` (617 lines) is still to do.
- [x] **Structured logging** _(done)_ — `logs.py`, logfmt to stdout, replacing all 99
      `print(..., flush=True)` calls except the four in the `__main__` CLI block, which are
      genuine terminal output. Identity and request path attach automatically via a logging
      filter, so no route has to remember; `LOG_LEVEL` controls verbosity.
- [x] **A health check that touches the database.** _(done)_ `/api/health` now reads from
      `characters` and answers 503 when that fails. It also reports the row count, because
      migrations run on connect — so an unmounted volume comes back as a valid *empty* schema,
      which any "does the table exist" check would call healthy. The count is reported rather
      than judged, since a fresh install before seeding looks identical.
- [x] **Delete dead code:** _(done)_ `character_mapping.js` (260 KB, zero references),
      `github_utils.py` (a single never-called function, left over from when data lived in a
      GitHub file instead of Postgres), `frontend/src/hooks/useMediaQuery.js` (exported, never
      imported), and `.cursor/plans/ideal_architecture_v2.plan.md` (916 lines superseded by
      `DECISIONS.md`; it assumed a paid DigitalOcean Droplet and contradicted the free-hosting
      decision).

---

## Phase 11 — Design system — **FOUNDATION COMPLETE**

The frontend had no design system, which is why it read as cheap: 387 hex literals across 85
distinct colours (the unmodified Bootstrap 4 defaults), the Windows default font stack, four
page-shell recipes with different padding/radius/shadow for the same job, eight button styles
sharing no base, three independent modal implementations, and dark mode as 144 hand-written
override selectors. Every decision had been made locally, so nothing compounded.

Register: a dense, restrained tool. Hairline borders over drop shadows, colour reserved for state
and meaning, chrome receding so the character art carries the colour. Light and dark are equal,
both derived from one token set, following `prefers-color-scheme` by default.

- [x] **Token layer** — `styles/tokens.css`. Semantic colour, 4px spacing scale, four radii, two
      elevations, weights and tracking, motion, layers. Neutrals tinted, never pure grey. Accent
      moved off `#007bff`.
- [x] **Three-state theming** — `system` / `light` / `dark` as a `data-theme` attribute on `<html>`,
      absent for the system case. All 107 dark-mode rule blocks and all 33 `!important`s gone.
      `noImportantStyles` re-enabled to keep them gone.
- [x] **Typeface** — Geist, self-hosted as a 69 KB variable woff2 (SIL OFL), replacing
      `'Segoe UI', Tahoma, Geneva, Verdana`.
- [x] **Primitives** — `components/ui/`: Button, IconButton, Card, Badge, Input, Select, Field,
      SegmentedControl, Modal, EmptyState, and the `useDialog` hook that all three dialogs had been
      duplicating. Two of them gained a working Tab trap they had been missing while setting
      `aria-modal`.
- [x] **All six pages on one Card.** Inline style objects: 76 → 3, and the three are
      `display: none` on hidden file inputs.
- [x] **Search is a route.** `/search?q=&by=` replaces swapping the page content out from under the
      router with no URL change. Results are linkable and the back button works.
- [x] **Saved page is a real CSS grid**, replacing `width: calc(12.5% - 18px)` hardcoded to eight
      columns plus four breakpoint overrides.
- [x] **One `<h1>` per page.** The only `<h1>` in the app had been inside the error boundary.
- [x] **Focus is visible again** — one `:focus-visible` ring replaces four `outline: none` rules
      and five `!important` resets. Plus a `prefers-reduced-motion` guard.
- [x] **Breakpoints** consolidated from nine unnamed values to four documented ones.
- [x] **`pages.smoke.test.jsx`** renders every route, because the build does not type-check and a
      missing import fails only in the browser.

Still open, and deliberately after Phase 6 — ownership, hide-for-me and report controls change what
each gallery item must show, so building this now means building it twice:

- [x] **The CharacterPage gallery.** _(done)_ Justified rows: each item's `flex-basis` and
      `flex-grow` are both proportional to its aspect ratio, so a row ends flush at one height
      with nothing cropped. Dimensions come from the database where known and are measured in the
      browser where not, which also removed the reflow cascade on image-heavy characters.
- [x] **Home page information architecture.** _(done)_ The feature bullet list is gone. The page is
      now three totals plus four sections drawn from the library itself: just-added artwork, most
      visited this week, most popular characters, most popular series. Every section hides itself
      when it has nothing to show. A contributor ranking exists and appears once more than one
      signed-in person has uploaded.
- [x] **Retire `legacy.css`** _(done)_ — gone, from 2,874 lines originally. Its 239 rules moved
      into `layout.css` (the frame), a new `components.css` (toasts, dialogs, the autocomplete,
      skeletons, empty states) and `pages.css`, in their original relative order so the cascade did
      not change. Verified rule-by-rule: the built stylesheet came out 30 bytes smaller, all of it
      the one `#toast-container .toast` rule folded into `.toast`.
- [x] **The remaining Biome findings** _(done)_ — `biome check src` is clean. Most were real: the
      gallery's two overlapping mouse-only handlers became one button per image, the series
      autocomplete had `role="option"` on items no keyboard could select and now implements the
      ARIA combobox pattern, the toast was a `role="button"` containing a button, and search
      results became links so middle-click works. The four remaining suppressions are file drop
      zones and backdrop dismissal, each with no keyboard equivalent to withhold.
- [x] **Re-enable `noDescendingSpecificity`** _(done)_ — on, and clean. Six real orderings were
      fixed by moving base rules above the modifiers that had been written before them.

Impeccable (`impeccable.style`, a design skill pack for AI coding agents) was evaluated and
deliberately **skipped for now**. Its leverage is highest when there is a system to align to;
there was none. Worth revisiting for `critique` / `audit` / `polish` against what now exists.

---

## Phase 12 — Identity, content and the profile _(done)_

Not planned as a phase; it grew out of "the home page should look like a real site".

- [x] **Character view tracking.** One row per person per character per hour, so a refresh cannot
      inflate it, and popularity ranked by distinct people rather than by hits. Swept after 90
      days. This is what made both "most visited" and a history tab possible — `image_takes`
      counts copy and download actions, which measure something else.
- [x] **A profile area** at `/profile`, five tabs: settings, saved, history, hidden, removed. Saved
      moved out of its own page; `/saved` redirects. Hidden and removed images were previously
      reachable only from the character page holding them, so anyone who did not recall which
      character that was had no way back to them.
- [x] **Display preferences.** `hide_attribution` and `hide_from_leaderboard`, separately, because
      somebody may be happy to be ranked while not wanting individual images traced to them. Both
      applied at render time — ownership is always stored, or an uploader could not remove their
      own images — which is what makes them retroactive and reversible. `show_nsfw` is recorded
      against a filter that does not exist yet.
- [x] **Uploads work on the server.** They wrote scratch files next to the code, which is
      read-only under `ProtectSystem=strict`, so every upload on the v2 origin failed with
      `[Errno 30]`. `tempfiles.py` uses the temp directory, which `PrivateTmp=true` makes private
      to the service. Two uploads of the same filename no longer collide either.

---

## Testing detail (harness set up in Phase 1)

The harness goes up in Phase 1. These are the rules worth covering, in the order they become
relevant — the concurrency test is written first, before Phase 2:

- [x] Removing another identity's image is refused; removing your own succeeds and sets
      `state='removed'`.
- [x] Hiding an image changes nothing for a second identity.
- [x] The second *distinct* report removes; a second report from the *same* identity does not.
- [x] Duplicate URL and duplicate content hash are both rejected on add.
- [x] **Concurrent adds to one character both persist** — the regression test for the Phase 2
      data-layer rewrite, and it passes: `tests/test_db_concurrency.py` covers two concurrent
      adds, many concurrent adds, and writes across tables not deadlocking.
- [x] Moderator and owner can remove others' images; a plain user cannot.

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
