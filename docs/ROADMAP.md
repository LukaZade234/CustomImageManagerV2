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

## Phase 2 — Data layer

Fixes the silent data loss. `db.py` holds one module-global psycopg2 connection with
`autocommit = True` and no transactions anywhere, so concurrent read-modify-writes of the JSONB
blob lose data today.

- [ ] **Move to `psycopg` 3 with `psycopg_pool`.** A direct replacement for `psycopg2-binary` with
      pooling built in — this *is* the connection-pooling task, without dragging in an ORM.
- [ ] **Wrap every read-modify-write in a real transaction.**
- [ ] **Green the Phase 1 concurrency test.** That is the signal the bug is dead.

**Skip SQLAlchemy.** Five small tables and a handful of queries do not justify an ORM; raw SQL
through psycopg3 plus Alembic for migrations stays clearer, and is easier for a future session to
reason about.

---

## Phase 3 — Data model

Everything about ownership and moderation depends on images being addressable records rather than
bare strings. Built directly on the Phase 2 data layer — with pooling and transactions already
correct underneath, this schema change is far less risky.

- [ ] **Replace the JSONB blobs with real tables.** New: `identities`, `custom_images`,
      `user_hidden`, `image_takes`, `image_reports`. Keep `characters`, `saved_characters`, and
      `last_updated` in the KV store for now — they are not causing problems.

      ```sql
      CREATE TABLE identities (
        id TEXT PRIMARY KEY, handle TEXT NOT NULL,
        discord_id TEXT UNIQUE,
        role TEXT NOT NULL DEFAULT 'user',   -- user | moderator | owner
        created_at TIMESTAMPTZ DEFAULT now()
      );
      CREATE TABLE custom_images (
        id BIGSERIAL PRIMARY KEY,
        character_name TEXT NOT NULL, url TEXT NOT NULL,
        content_hash TEXT, position INT,
        added_by TEXT REFERENCES identities(id), added_at TIMESTAMPTZ DEFAULT now(),
        state TEXT NOT NULL DEFAULT 'active',   -- active | removed
        removed_by TEXT, removed_at TIMESTAMPTZ, removed_reason TEXT,
        UNIQUE (character_name, url)
      );
      CREATE TABLE user_hidden   (identity_id TEXT, image_id BIGINT, PRIMARY KEY (identity_id, image_id));
      CREATE TABLE image_takes   (image_id BIGINT, identity_id TEXT, kind TEXT, at TIMESTAMPTZ DEFAULT now());
      CREATE TABLE image_reports (image_id BIGINT, identity_id TEXT, reason TEXT, at TIMESTAMPTZ DEFAULT now(),
                                  PRIMARY KEY (image_id, identity_id));
      CREATE INDEX ON custom_images (character_name, state);
      ```

      `UNIQUE (character_name, url)` gives URL dedupe for free. `content_hash` catches the same
      picture re-uploaded under a different ImgChest URL.

- [ ] **A migration tool.** Alembic or numbered SQL files. Currently there is only
      `CREATE TABLE IF NOT EXISTS` at startup with no versioning.
- [ ] **A settings module.** Environment variables are read ad hoc across several files; centralise
      them with validation at startup so a missing `SECRET_KEY` fails loudly rather than silently
      falling back to `'dev-key-change-in-production'`.
- [ ] **Data migration script.** Read the existing `custom_images` blob out of the old database,
      insert one row per URL preserving array order into `position`, leave `added_by` NULL.
      Idempotent (`ON CONFLICT DO NOTHING`). Legacy images therefore have no owner, which means
      nobody can remove them except through Report — an acceptable and arguably ideal outcome.

---

## Phase 4 — Concurrency and worker model

**Deliberately placed after Phase 2, not before.** Raising concurrency while the read-modify-write
bug is still live would produce *more* collisions and lose *more* data. This is the one place where
doing the cheap fix early makes things actively worse.

Today: `--workers 2` with no `--worker-class`, so gunicorn uses sync workers — one request at a
time each, blocked for the request's full duration including network waits. That is **two
concurrent requests site-wide**, against requests that take up to 55s (Mudae lookup) or minutes
(series import, image upload).

- [ ] **Switch to `--workers 1 --worker-class gthread --threads 8`.** Gives 8 concurrent requests
      instead of 2, one copy of the app in RAM instead of two, and — because there is only one
      process — **makes the Discord `threading.Lock` correct for free.**
- [ ] **Do not use gevent.** It monkey-patches sockets, which conflicts with the `asyncio.run()`
      Discord code in `mudae_discord.py`. `gthread` patches nothing.
- [ ] **Fix the SSE timeout kill.** `--timeout 120` kills any worker silent for 120s, and a sync
      worker only reports to the master *between* requests. Any series import over two minutes is
      SIGKILLed mid-stream. Raise the timeout for the streaming route, or remove the long work from
      the request cycle entirely (see Phase 8) — the second is the real fix.
- [ ] **Reconsider worker count** only once Discord work is out of the request path. At that point
      every request is fast and the number stops mattering much.

---

## Phase 5 — Hosting migration

Goal: get off DigitalOcean and Neon entirely, at zero recurring cost. Rationale in
`DECISIONS.md` §3.

- [ ] **Frontend to Cloudflare Pages.** Free, global edge, custom domain. Split the SPA out of
      Flask; the API becomes a separate origin, so CORS must be configured deliberately rather
      than left at `*`.
- [ ] **`character_images/` to R2.** 1000 PNGs, 151 MB, currently served by Flask off local disk on
      every request. R2 has free egress. Later these should move to ImgChest, but R2 is the
      immediate step.
- [ ] **Stand up the origin box.** Two documented options — decide at build time, since Cloudflare
      Tunnel makes them interchangeable and switching later costs one config change:

      | | Oracle Cloud Always Free | Home server |
      |---|---|---|
      | Cost | Free permanently | Free |
      | Spec | 4 ARM cores / 24 GB RAM | Existing repurposed PC |
      | Uptime | Datacenter | Domestic power and internet |
      | Bandwidth | ~10 TB/mo egress | Home upload speed |
      | Risks | Awkward signup, regional capacity shortages, idle reclamation | Outages, ISP terms |

- [ ] **Cloudflare Tunnel to the origin.** No port forwarding, no static IP, TLS at the edge.
- [ ] **PostgreSQL on the origin box.** Co-located with the app — the app is chatty with the
      database and the user is not (`DECISIONS.md` §3).
- [ ] **Backups.** `pg_dump` to R2 on a cron. This is now self-hosted data with no managed provider
      behind it, so backups are not optional. Verify a restore actually works.
- [ ] **Cut over DNS**, confirm, then decommission DigitalOcean and Neon.
- [x] **Delete `.github/workflows/build-frontend.yml`.** _(done)_ It existed only because the
      DigitalOcean Python buildpack could not build a frontend. Cloudflare Pages builds from
      source, so the force-committed `frontend/dist` is no longer needed.
- [x] **Resolve the `Dockerfile` vs `.do/app.yaml` split.** _(done)_ `.do/` deleted; `Dockerfile`
      kept as the single deployment description, since it suits a self-hosted origin.

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

- [ ] **Lock down CORS.** `CORS(app, origins='*')` lets any webpage drive a visitor's browser into
      the mutating endpoints. With the SPA on Pages this must be an explicit origin allowlist.
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
