# Roadmap — v2 Rework

Everything to be done, grouped by area and roughly ordered by dependency. Rationale for the
larger decisions is in `DECISIONS.md`; the description of what exists today is in
`CURRENT_STATE.md`.

Phase 0 unblocks most of the rest. Within later phases, ordering is mostly free.

---

## Phase 0 — Foundations

Everything about ownership and moderation depends on images being addressable records rather than
bare strings, so this comes first. It also fixes the concurrent-write data loss (`DECISIONS.md`
§6).

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

- [ ] **Connection pooling and real transactions.** Replace the single module-global
      `autocommit=True` connection and its keepalive thread with a pool, and wrap every
      read-modify-write in a transaction. This is the fix for the silent data loss.
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

## Phase 1 — Hosting migration

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

## Phase 2 — Identity and moderation

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

## Phase 3 — Security

Independent of the above and worth doing early. A script can currently empty the entire library.

- [ ] **Lock down CORS.** `CORS(app, origins='*')` lets any webpage drive a visitor's browser into
      the mutating endpoints. With the SPA on Pages this must be an explicit origin allowlist.
- [ ] **Per-identity rate limits** on add, hide, and report. There is nothing at all today.
- [ ] **Auto-cooldown** for an identity reporting or hiding at an implausible rate.
- [ ] **Re-audit the SSRF guards** (`_safe_import_image_url`, `_host_resolves_only_to_public_ips`)
      after the move — they matter more on a self-hosted box sitting inside a home or cloud
      network than on managed infrastructure.

---

## Phase 4 — Mudae hardening

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

## Phase 5 — Performance

- [ ] **Kill the full-map fetch.** `GET /custom_images.json` returns every image URL for every
      character, and `HomePage` downloads all of it to compute two numbers. Replace with an
      `/api/stats` endpoint plus per-character fetches.
- [ ] **Adopt react-query or SWR.** Retry, backoff, and cache invalidation are currently hand-rolled
      in two places (`useStore.js`, `api.js`) and duplicated.
- [ ] **Serve character images from the CDN**, not from Flask off local disk (follows from R2).
- [ ] **Reconsider gzip.** `flask-compress` runs on the origin; with Cloudflare in front, the edge
      can handle compression instead.

---

## Phase 6 — Structure and code quality

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

## Phase 7 — Testing

Zero tests exist today. Start with the rules whose failure is silent and costly:

- [ ] Removing another identity's image is refused; removing your own succeeds and sets
      `state='removed'`.
- [ ] Hiding an image changes nothing for a second identity.
- [ ] The second *distinct* report removes; a second report from the *same* identity does not.
- [ ] Duplicate URL and duplicate content hash are both rejected on add.
- [ ] **Concurrent adds to one character both persist** — this fails on the current architecture
      and is the regression test for the whole Phase 0 rewrite.
- [ ] Moderator and owner can remove others' images; a plain user cannot.

---

## Deferred / future

- **ImgChest mirror.** A second copy of every image in R2 or similar, so the library survives
  ImgChest losing files or shutting down. Explicitly a **backup, not a replacement** — the
  ImgChest URL stays canonical because Mudae accepts nothing else (`DECISIONS.md` §2).
- **Move the 1000 character PNGs to ImgChest** and drop them from the repo entirely.
- **Per-user saved selections and personal ordering.** Deliberately deferred; hide-for-me is the
  minimum that solves the actual problem.
- **Revisit retirement policy with real take data.** Take counts are being logged from Phase 2
  onward precisely so this can eventually be designed against evidence rather than guessed at. Do
  not build a retirement mechanism before there is data — see the rejected approaches in
  `DECISIONS.md` §1.
