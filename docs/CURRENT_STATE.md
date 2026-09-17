# Current State — ImgManager (v1, retired)

A factual description of the version being retired. No recommendations here; those live in
`ROADMAP.md`, and the reasoning behind them in `DECISIONS.md`.

Line references point at the code as it stands in this repository (v1 behaviour, reformatted
by `ruff` during the Phase 0 toolchain work). The original unformatted history lives on the
v1 repository at commit `93d7c97`.

> **Note:** this describes v1 *as it was*. Some files documented here no longer exist in the
> V2 repository — `character_mapping.js`, `github_utils.py`, `.do/app.yaml`,
> `.github/workflows/build-frontend.yml`, and `.cursor/plans/` were deleted during the initial
> cleanup. They are described below because they were part of the system being replaced, and
> because the reasons they existed explain choices in `ROADMAP.md`.

---

## 1. What the app is

A web tool for managing custom character images for **Mudae**, a Discord gacha bot. Users browse a
library of characters, add custom images to them, and take those images away — either by
downloading them, or by copying a generated `$ai` command that registers the images with Mudae.

The library is a **single shared global collection**. There are no accounts and no ownership.
Anyone who can reach the site can add or delete anything.

---

## 2. Hard constraints

These are external facts that constrain the design. They are not preferences and cannot be
engineered away.

### 2.1 Images MUST be hosted on ImgChest

Mudae's `$ai` custom-image command accepts image URLs **only from ImgChest and Imgur**. Imgur is
blocked in the operator's country. That leaves ImgChest as the single viable host.

This is why the app uploads every image to ImgChest and stores only the returned direct link.
Migrating image storage to Cloudflare R2, S3, or local disk would produce URLs Mudae rejects,
making the images useless for the app's primary purpose. **Do not propose replacing ImgChest.**
A second copy kept elsewhere purely as a *backup mirror* is a different and acceptable idea.

### 2.2 The backend requires a real CPython runtime

`requirements.txt` pins `discord.py-self==2.1.0`, `Pillow`, and `psycopg2-binary` — all native
extensions. Combined with Discord logins that can take up to 30 seconds, this rules out edge and
serverless runtimes (Cloudflare Workers, Vercel/Netlify functions) without a full rewrite.

### 2.3 Nothing is ever deleted from ImgChest

No code path anywhere calls an ImgChest delete. "Deleting" an image only removes its URL from the
database; the file stays live at that URL indefinitely. Every image in this app's history is still
retrievable.

---

## 3. Hosting and deployment

**Platform:** DigitalOcean App Platform. **Database:** Neon PostgreSQL. Both are paid, which is
the trigger for the migration.

**Server:** `gunicorn --worker-tmp-dir /dev/shm --workers 2 --timeout 120 app:app`.
`app.py` is a three-line WSGI shim re-exporting `app` from `upload_imgchest.py`.

### Two conflicting deploy paths

Both exist in the repo and disagree with each other:

| | `Dockerfile` | `.do/app.yaml` |
|---|---|---|
| Build | Multi-stage; `node:20-alpine` builds `frontend/dist`, then `python:3.11-slim` | Buildpack (`environment_slug: python`) |
| Frontend source | Built during the image build | Expects `frontend/dist` **already committed to git** |
| Run | Same gunicorn command | Same gunicorn command |

`.do/app.yaml` is the one actually in use, which is why CI force-commits build output (§7).

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `IMGCHEST_API_KEY` | Yes | ImgChest uploads |
| `DATABASE_URL` | Yes | Neon PostgreSQL |
| `SECRET_KEY` | Yes (since Phase 6) | Signs identity cookies. Was set and never read at the time this document was written. |
| `CORS_ORIGINS` | No | Comma-separated. **Defaults to `*`** |
| `DISCORD_USER_TOKEN` | For Mudae | A real user account token (self-bot) |
| `DISCORD_CHANNEL_ID` | For Mudae | Channel where `$im` / `$ima` are sent |
| `MUDAE_BOT_USER_ID` | No | Defaults to `432610292342587392` |

### 3.1 Worker model

`gunicorn --worker-tmp-dir /dev/shm --workers 2 --timeout 120 app:app`. No `--worker-class` is
set, so gunicorn uses **sync** workers.

A sync worker handles exactly one request at a time, start to finish, and stays blocked for the
whole duration including time spent waiting on the network. **Two workers therefore means two
concurrent requests site-wide**; further requests queue in the socket backlog.

This collides badly with how long requests take here:

| Request | Duration | Cause |
|---|---|---|
| Mudae lookup | up to ~55s | 30s Discord login timeout + 25s `REPLY_TIMEOUT_S` |
| Series import (SSE) | minutes | ~1-2.5s per character across dozens of characters |
| Image upload | up to minutes | Pillow conversion + ImgChest, 4 retries at `(30, 120)` timeouts |

The frontend also uploads one file per request in a serial loop, so a 10-file drop is 10
sequential requests. One series import plus one upload session occupies both workers, and every
other visitor gets nothing — the site appears down rather than slow.

The worker model is also the direct cause of two bugs below: the Discord `threading.Lock` is
process-global, so two workers hold two independent locks; and `db.py`'s single global connection
is one per worker.

### 3.2 Python version disagreement

Four sources disagree about which Python this is:

| Source | Version |
|---|---|
| `.python-version` | 3.13 |
| the committed `.venv` | 3.14.6 |
| `Dockerfile` | `python:3.11-slim` |
| `pyrightconfig.json` | 3.11 |

Development happens on 3.14 and deployment on 3.11. `discord.py-self==2.1.0` does import on 3.14,
so this has been luck rather than design.

### 3.3 Dependency pinning

`requirements.txt` declares 10 packages, **8 of which have no upper bound** (`flask>=2.0` will
accept Flask 4.0), and there is **no lockfile** — builds are not reproducible. Installed versions
have drifted far past the declared floors: Flask 3.1.3, gunicorn 26.0.0, flask-cors 6.0.5.

`protobuf` is declared directly but **never imported by application code** — it is transitive via
`discord.py-self` / `discord-protos`.

The frontend is in better shape: `package-lock.json` is tracked. But every major dependency is one
major version behind (React 18.3.1, react-router-dom 6.30.4, zustand 4.5.7, Vite 5.4.21), and
`npm audit` reports **5 vulnerabilities (2 high)** in `esbuild`, `nanoid`, and `react-router`.
There is no linter, formatter, type checker, or test runner on either side; `pyrightconfig.json`
exists but pyright is not in `requirements.txt`. `@types/react` and `@types/react-dom` are
installed although the project contains no TypeScript.

---

## 4. Database

SQLite, one file, replicated to R2 by Litestream. Eleven tables are created by
the twenty migrations in `migrations/`, plus `schema_migrations`, which `db.py`
creates itself; all are applied on first connect.

The v1 shape was a single Postgres `kv_store` table holding four whole JSON
documents, in which a custom image was a bare URL string in a list — no id, no
timestamp, no uploader, nowhere to attach anything. Everything below exists
because that had to stop being true.

| Table | Rows (prod) | What it holds |
|---|---|---|
| `custom_images` | 8,560 | The library. Id, url, content hash, position, owner, state, dimensions, ImgChest post id (for permanent delete) |
| `characters` | 1,705 | Name, folded name key, series, rank, main image, gender, pools, timestamps |
| `image_takes` | 271 | `copy_command` / `download` events, per image |
| `rate_limit_hits` | — | Fixed-window counters, swept after a day |
| `character_views` | — | One row per person per character per hour |
| `identities` | 7 | Cookie pseudonyms, optional Discord binding, role, display preferences |
| `saved` | — | Bookmarks, per identity |
| `user_hidden` | — | Per-viewer hidden images |
| `image_reports` | — | Two distinct reporters remove an image |
| `character_catalog` | — | The Mudae scrape: name, series, rank, pools, `mudae.net` portrait |
| `catalog_series` | — | Series names seen in the catalog, for autocomplete |
| `notifications` | — | A row per recipient: mechanical, and owner broadcasts (dismissible, grouped by `group_id`) |
| `pinned_notifications` | — | Owner announcements resolved by audience at read time, always visible, never dismissible |
| `pinned_notification_reads` | — | Per-identity read state for a pin, so a new account sees it unread |
| `moderation_actions` | — | Staff record of a warn/suspend/ban sent a contributor; the delivered notification points back at it |
| `moderation_status` | — | The live restriction on an account: `suspended` (with an end) or `banned` (open-ended) |
| `identity_networks` | — | Keyed hashes of the networks each identity has written from, pruned after 90 days — a moderation lead, not a rule |
| `schema_migrations` | 21 | Which migrations have run |

Indexes worth knowing: `idx_characters_name_nocase` (case-insensitive lookup),
`idx_custom_images_hash` (duplicate detection by content, not URL, checked before the ImgChest
upload),
`idx_character_views_identity` and `idx_character_views_recent` (history, and
the popularity window).

### State, not deletion

`custom_images.state` is `active` or `removed`; nothing is ever deleted. That
follows from constraint 2.3 — the image is still live on ImgChest regardless —
and it is what makes removal cheap to undo and the Removed tab possible.

### Identity and ownership

Every visitor gets a row in `identities` lazily, on their first write. The id
lives in an HttpOnly cookie and is never returned by the API; clients get a
handle and a per-image `is_mine`. Signing in with Discord binds an existing
pseudonym to an account, merging the two identities. **Adding an image, or a
brand-new character, requires that upgrade**: browsing, saving, hiding,
reporting, restoring and metadata edits are open to a cookie-only visitor, but
the endpoints that upload to ImgChest (`/api/custom-image`,
`/api/import-custom-images-from-urls`, `/api/set-main-image`, `/upload`, and the
file branch of `/api/add-character`) are behind `identity.require_signed_in` and
answer `403` with `code: discord_required`. `/api/add-character` also refuses a
name the catalog does not know, so a cookie-only visitor can add characters
*from the library* but cannot invent one; `/api/catalog/add-character` stays
open. Uploading is the one action that spends the shared ImgChest key, and tying
this to an account is also what makes a ban meaningful.

`hide_attribution` and `hide_from_leaderboard` are *display* preferences applied
when rendering. Ownership is always recorded, because removal is
ownership-scoped: an uploader who could not be identified could not manage their
own uploads. That is also what makes both switches retroactive and reversible.
`show_nsfw` is recorded but not yet read — nothing carries a rating.

### Connection handling

`db.py` keeps **one module-global psycopg2 connection** (`_db`) per process, created lazily in
`_get_db()` (`db.py:71`) with `conn.autocommit = True` (`db.py:93`). A daemon thread pings
`SELECT 1` every 4 minutes to stop idle timeouts (`db.py:46`). `_with_retry` (`db.py:128`) retries
once on `OperationalError` / `InterfaceError` / `DatabaseError`.

There are **no transactions anywhere in the codebase.**

### The concurrent-write data loss bug

Every mutation is a read-modify-write of an entire JSONB document with no locking and no
isolation. For example, adding an image (`upload_imgchest.py:761`):

```python
data = db.get_custom_images()  # read the whole map
data[char_name].extend(links)  # modify in Python
db.set_custom_images(data)  # write the whole map back
```

With `--workers 2`, two simultaneous requests both read the old document and the second write
silently discards the first. This is a genuine data-loss bug that presents to users as images
disappearing — indistinguishable from someone deleting them, but unrelated.

---

## 5. Backend

8,299 lines of Python, plus 1,241 in `scripts/`.

| File | Lines | Role |
|---|---|---|
| `upload_imgchest.py` | 324 | App construction, CORS, identity hooks, health/stats endpoints |
| `routes/customs.py` | 632 | Custom images: add, order, remove, hide, report; serves the accent seed |
| `routes/mudae.py` | 419 | Mudae lookup, series import, portrait refresh |
| `routes/characters.py` | 369 | Characters, saved list, main image |
| `routes/media.py` | 117 | Thumbnails, static images, the download proxy |
| `routes/catalog.py` | 98 | The Mudae catalog: search, series, add-character |
| `routes/auth.py` | 170 | Discord sign-in and per-identity settings |
| `routes/spa.py` | 58 | Serving the built React app |
| `logs.py` | 135 | Logfmt logging, with identity attached inside a request |
| `validation.py` | 33 | Character field limits and name checks |
| `mudae_discord.py` | 1054 | Discord self-bot automation and Mudae embed parsing |
| `db.py` | 2022 | SQLite data layer |
| `accent_extract.py` | 706 | Measures a character's accent colour from portrait and gallery |
| `catalog_import.py` | 613 | Parses `$wa`/`$ima` extracts into `character_catalog` |
| `remote_images.py` | 343 | SSRF guards, remote fetch, ImgChest naming |
| `identity.py` | 235 | Cookie pseudonyms and the Discord binding |
| `image_utils.py` | 218 | Pillow validation, format detection, WebP conversion |
| `imgchest_utils.py` | 210 | ImgChest upload client with retry/backoff |
| `discord_auth.py` | 169 | OAuth2 flow (`identify` scope only) |
| `ratelimit.py` | 115 | Per-identity fixed-window limits |
| `thumbnails.py` | 96 | On-demand WebP thumbnails |
| `tempfiles.py` | 58 | Scratch files under the service's private temp directory |
| `gunicorn.conf.py` | 85 | Production server config |
| `app.py` | 10 | WSGI shim |
| `scripts/` | 1241 | Migration, backfill, catalog-import and snapshot scripts |

### 5.1 `upload_imgchest.py` and `routes/`

`@app.route` needs the app object to exist when the decorator runs, so every route had to sit below
`app = Flask(__name__)` in one module — that, not neglect, is why the file was 1,700 lines. A
Blueprint records the same declarations without an app, so each subject now lives in its own module
under `routes/` and `upload_imgchest` attaches them at the bottom. The import goes one way only.

Paths are unchanged: a blueprint owns a subject, not a URL prefix. `upload_imgchest.py` keeps what
belongs to the app rather than to any subject — the Flask object and SECRET_KEY, CORS, the identity
hooks, the upload guard, the database-configuration error handler, the deployment path guard, and
`/api/health` and `/api/stats`.

**Note for tests.** A route calls an imported helper as a name in **its own** module's namespace.
So `monkeypatch.setattr("routes.media._get_with_validated_redirects", ...)` patches what the
thumbnail route uses, while patching `remote_images` patches what the helper itself calls. Both are
correct for different targets, and picking the wrong one fails silently — the test passes for the
wrong reason, or makes a real network call. Whenever a route moves module, every monkeypatch aimed
at its old home has to move with it.

App setup (`upload_imgchest.py:59`):
```python
app = Flask(__name__)
_secret_key, _secret_is_ephemeral = identity.resolve_secret_key()
app.config["SECRET_KEY"] = _secret_key
# CORS_ORIGINS="*" is refused outright: this API sends credentials, and browsers
# reject a wildcard origin on credentialed requests.
_origins = os.environ.get("CORS_ORIGINS", "").strip()
cors_origins = [o.strip() for o in _origins.split(",") if o.strip()]
CORS(app, origins=cors_origins, supports_credentials=True)
```

No `Compress(app)`. Responses are compressed at the Cloudflare edge, which does
Brotli; doing it again on the origin would only spend CPU on a box billed for it.
See DECISIONS.md.

Notable helpers:
- `_validate_character_name` (`:321`) — length, no `/` `\` `..`, no control characters
- `_safe_stored_filename` (`:38`), `_canonical_url_key_for_dedup` (`:66`)
- SSRF guards for URL import: `_allowed_image_proxy_url` (`:96`),
  `_host_resolves_only_to_public_ips` (`:108`), `_safe_import_image_url` (`:127`)
- `_run_single_custom_upload_from_temp` (`:236`) — the core upload pipeline
- `_guard_custom_image_upload_preprocess` (`:345`) — a `before_request` hook that rejects
  non-multipart bodies, missing `User-Agent`, and zero-length bodies **using headers only**, to
  avoid blocking on slow request bodies

### 5.2 Full endpoint table

Generated from the app's URL map; `tests/test_url_map.py` pins it, so a route
that silently stops registering is a test failure rather than a 404 somebody
finds later.

Authentication is per-route and mostly absent by design — the app is usable
without an account. What is enforced is *ownership*: removal is scoped to the
uploader unless the caller is a moderator, and the write endpoints are rate
limited per identity (`ratelimit.py`).

**`auth`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/discord/callback` | Where Discord sends the browser back. |
| GET | `/api/auth/discord/start` | Send the browser to Discord's consent screen. |
| POST | `/api/auth/logout` | Forget the current identity in this browser. |
| GET | `/api/me` | Who the caller is, as far as the server is concerned. |
| GET | `/api/me/contributions` | — |
| GET | `/api/me/hidden` | Everything this visitor has hidden, across every character. |
| GET | `/api/me/history` | Characters this visitor has looked at, most recent first. |
| GET | `/api/me/removed` | Everything this visitor removed, across every character. All restorable. |
| PATCH | `/api/me/settings` | Change a display preference. |

**`characters`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/accent-override` | Set, clear, or pixel-pick a character's accent colour (staff only). |
| POST | `/api/add-character` | Add a new character. |
| POST | `/api/characters/<path:name>/view` | Note that the caller looked at this character. |
| POST | `/api/edit-character` | — |
| GET | `/api/saved` | — |
| POST | `/api/saved` | — |
| DELETE | `/api/saved/<path:name>` | — |
| POST | `/api/set-main-image` | — |
| POST | `/upload` | — |

**`customs`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/custom-image` | — |
| GET | `/api/custom-image/<path:char_name>` | Active images for one character, annotated for the caller. Also carries the character's accent seed, and is where a stale seed is noticed and re-measured. |
| GET | `/api/customs` | One page of the browse-customs list, searched and sorted server-side. |
| POST | `/api/delete-custom-image` | Remove a single image. 403 when it is not the caller's to remove. |
| POST | `/api/delete-custom-images` | Remove the caller's own images from a selection. |
| POST | `/api/hide-images` | Hide images for the caller only. |
| POST | `/api/import-custom-images-from-urls` | Fetch image URLs server-side (drag-from-web: Pinterest, etc.) and add as custom images. |
| GET | `/api/removed/<path:char_name>` | The Removed drawer. Nothing is ever hard-deleted, so this is never empty |
| POST | `/api/reorder-custom-images` | — |
| POST | `/api/report-image` | Report an image for an objective problem. |
| POST | `/api/restore-images` | Put removed images back. |
| POST | `/api/takes` | Log that images were downloaded or copied into an $ai command. |
| POST | `/api/unhide-images` | — |

**`media`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/download-image-proxy` | Fetch a remote image server-side so the browser can save it (avoids CORS on ImgChest URLs). |
| GET | `/thumbs/<int:image_id>.webp` | A small WebP of one image, generated on first request and cached. |

**`mudae`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/mudae/lookup-character` | Lookup a character via Mudae $im. |
| GET | `/api/mudae/proxy-image` | Proxy a remote character image for browser preview (Discord CDN often blocks hotlinking). |
| POST | `/api/mudae/refresh-main-image` | Fetch character card image from Mudae $im and set as main image. |
| POST | `/api/mudae/series-extract` | Fetch a whole series via one `$imartsmi-` DM and preview it (new vs. changed) without saving. |
| POST | `/api/mudae/series-extract/apply` | Create and refresh working characters from a reviewed series extract; only fields that differ are written. |
| GET | `/api/mudae/status` | — |

**`catalog`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog/characters` | Name suggestions from the catalog and the working set; `series` and `pool` narrow them. |
| GET | `/api/catalog/search` | One page of a catalog search (name or series, sorted, paginated) plus a total. |
| GET | `/api/catalog/character` | One catalog entry by name. |
| GET | `/api/catalog/series` | Series names for autocomplete. |
| POST | `/api/catalog/add-character` | Promote a catalog entry into the working set. |

**`notifications`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/notifications` | This identity's messages, newest first, plus the unread count. |
| POST | `/api/notifications/read` | Mark everything this identity has as read. |
| POST | `/api/notifications/dismiss` | Remove one normal notification from your own inbox. Pinned ones cannot be dismissed. |
| POST | `/api/notifications/delete` | Owner only: remove a broadcast from every inbox, or delete a pin. |
| POST | `/api/notifications/broadcast` | Owner only: fan a message out to everyone, or to moderators only; `pinned` makes it a permanent global announcement. |

**`spa`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | — |
| GET | `/add` | — |
| GET | `/assets/<path:filename>` | Hashed build output; cached a year |
| GET | `/<filename>` | `favicon.ico`, `favicon-32.png`, `apple-touch-icon.png`, `robots.txt`. An allowlist, not a file lookup |
| GET | `/<any(emoji, fonts):folder>/<path:filename>` | Mudae gender emoji and the self-hosted Geist font |
| GET | `/character/<path:name>` | — |
| GET | `/customs` | — |
| GET | `/search` | — |
| GET | `/profile` | — |
| GET | `/notifications` | — |
| GET | `/moderation` | — |
| GET | `/saved` | — |

**`upload_imgchest`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Is this deployment actually serving? 200 if yes, 503 if not. |
| GET | `/api/stats` | Everything the landing page renders, in one request. |

### 5.3 Image upload pipeline

`_run_single_custom_upload_from_temp` (`upload_imgchest.py:255`):

1. File saved to `./temp_custom_<secure_filename>` in the working directory
2. Size check against `MAX_FILE_SIZE` (30 MB)
3. `validate_image_file` (`image_utils.py:30`) — Pillow `img.verify()`
4. `convert_to_png` (`image_utils.py:40`) unless already `.png` / `.gif`:
   - Reject over 4096px unless the file is under 30 MB
   - `ImageOps.exif_transpose` for orientation
   - Resize longest edge to ≤ 2048px (`MAX_DIMENSION`)
   - Convert to RGBA, save PNG
   - Loop shrinking by ~8–12% until under 30 MB, max 14 iterations
5. `upload_to_imgchest` (`imgchest_utils.py:63`) — `POST /v1/post` with `privacy: hidden`,
   `nsfw: "false"` hardcoded; 4 attempts with exponential backoff on timeouts, connection errors,
   429, and 502/503/504
6. Returns `(post_link, direct_link)`; only `direct_link` is stored
7. `finally` block removes temp and converted files

### 5.4 Mudae integration (`mudae_discord.py`)

A **Discord self-bot**: it logs into the operator's own Discord account using
`DISCORD_USER_TOKEN`, sends `$im` (one character) or `$imartsmi-` (a whole series) in a fixed
channel, and parses Mudae's embed and DM replies. It does not introduce any end-user identity —
every request is attributed to the operator's account; the only identity check is "is this message
from the Mudae bot".

**Connection model.** `_MudaeSession.connect()` brings up a `discord.py-self` client and resolves
the channel; `close()` tears them down; the lookup methods run in between. The session is
**reusable** — the connection is not tied to a single `with` — and each query resets its own wait
state and pins a watermark (the newest Mudae message seen on the channel and in DMs), so a reply
that arrives late, or a DM part left over from a previous fetch, cannot answer the wrong query.

**The connection lives in `mudae_service.py`.** That process is the only thing that signs in; the
web workers forward jobs over a Unix socket (`MUDAE_SOCKET`) and no longer need the token. It
connects lazily on the first job, runs jobs one at a time from a short FIFO queue (4 deep), and
disconnects after `MUDAE_IDLE_SECONDS` (10 minutes) with an empty queue, so an idle site is not a
permanently online account. `deploy/imgmanager-mudae.service` runs it; `deploy/update.sh` restarts
it best-effort. `_service_call`/`status()` in `mudae_discord.py` are the client side, and
`/api/mudae/status` reports the service's real state (connected, busy, queue depth).

The web app has no in-process fallback: `MUDAE_SOCKET` is required for Mudae
features, and without it (or with the service down) those endpoints return a
clean 503. The token is loaded only by the mudae unit, from
`/etc/imgmanager/mudae.env`, so the API process never holds it.

Pacing: `REPLY_TIMEOUT_S = 25.0` bounds a single reply wait, `ACTION_DELAY_S = 1.0` spaces Discord
actions, and a series DM is collected until its header total is reached or the parts stop arriving
(`DM_IDLE_TIMEOUT_S`, `DM_MAX_WAIT_S`).

Parsing is extensive and fragile — roughly 40 helpers reverse-engineering Mudae's formats
(`parse_im_embed`, `parse_im_message`, `parse_ima_names`, plus claim-rank, series and list
handling). It breaks whenever Mudae changes its output, so a failed parse now logs the raw reply
and raises a "format may have changed" error rather than a blank refusal.

**Risk:** automating a user account violates Discord's Terms of Service. The account can be banned,
which would take out every Mudae-backed feature — lookup, portrait refresh, bulk series import,
rank/pool refreshes — but nothing else. Prefer a throwaway alt and keep the connection off rather
than always-on; see `DECISIONS.md` §8, "The self-bot is a liability".

---

## 6. Frontend

React 19 + react-router-dom 7 + zustand 5 + Vite 8. 9,332 lines of source
across 85 files (15,081 including tests).

| Area | Lines | Notes |
|---|---|---|
| `pages/CharacterPage.jsx` | 963 | The gallery and its three modes. Was 1,611 |
| `pages/AddPage.jsx` | 253 | The Add workbench: catalog matching only. Was 806 |
| `components/AddMudaePanel.jsx` | 519 | Mudae lookup and bulk series import, lifted out of AddPage |
| `components/AddManualForm.jsx` | 135 | The hand-typed add form, lifted out of AddPage |
| `pages/HomePage.jsx` | 577 | Totals, just-added ticker, most-visited, popular characters, series ledger, contributor board |
| `pages/CustomsPage.jsx` | 410 | Browse all customs, filtered server-side |
| `hooks/useGalleryReorder.js` | 316 | Pointer-events drag-to-reorder, mouse and touch, plus arrow-key moves |
| `api.js` | 294 | Hand-rolled API client |
| `components/GalleryToolbar.jsx` | 129 | The gallery's mode bar, lifted out of CharacterPage |
| `pages/profile/` | ~1,178 | Five tabs: settings, saved, history, hidden, removed |
| `components/ui/` | 377 | The primitives |

**Pages.** `/`, `/customs`, `/search`, `/add`, `/character/:name`, and `/profile`
with five nested tab routes. `/saved` redirects into the profile, where the list
now lives.

**State:** zustand holds UI state only — theme, toasts, the current character, and the
search/sort preferences remembered across visits. All server state is react-query
(`queries/`): a character's gallery, the catalog lookups (search, suggest, match), and
`saved` / `stats` / `me`, sharing one retry/backoff policy (`queries/queryClient.js`,
`utils/retry.js`). The full roster is not held: search and autocomplete run on the server
(`/api/catalog/search`, `/api/catalog/characters`) and the character page fetches the one
record it shows.

**Styling:** a token layer plus primitives, loaded in order by
`styles/index.css`: tokens → base → layout → ui → components → pages. `ui` must
load before `components` and `pages` so a call site can adjust a primitive;
getting that order wrong has silently broken the search bar twice. `legacy.css`
is gone. See `DEVELOPMENT.md`.

**Identity in the UI.** The navbar carries one profile button showing your
handle. Sign-in, sign-out, theme and the privacy switches all live on
`/profile`. Ownership is shown per image only where it changes what you can do.

### The document shell and its static files

`frontend/index.html` is the only HTML in the project, served unmodified for every client route.
It carries, in order: the `no-referrer` policy that lets `mudae.net` portraits load, a description,
the Google Search Console verification token, the icon links, and the pre-paint theme script.

| File | In `frontend/public/` | Notes |
|---|---|---|
| `favicon.ico` | yes | 16/32/48 in one file |
| `favicon-32.png` | yes | What modern and HiDPI browsers pick |
| `apple-touch-icon.png` | yes | 180×180, opaque — iOS composites alpha on black |
| `robots.txt` | yes | Everything crawlable except `/api/`, `/profile`, `/notifications`, `/moderation` |
| `emoji/`, `fonts/` | yes | Mudae gender marks; the self-hosted Geist variable font |

The icons are **kakera**, Mudae's own gem, in the teal that matches `--accent`. The project already
shipped Mudae emoji for the gender marks, so the precedent was set; the source is
`frontend/favicon-src.webp`, kept deliberately *outside* `public/` because Vite copies that
directory verbatim and would otherwise publish the build input. It is 48×96, so the gem is centred
rather than stretched, and the Apple icon is held to 75% of its tile so the upscale is 1.4× rather
than 1.9×. `docs/DEVELOPMENT.md` has the regeneration command.

**There are no Open Graph or Twitter card tags**, and the shell carries one static title and
description for every route. Discord's crawler does not run JavaScript, so a character link pasted
into Discord — where this product's users are — renders as text with no image. See
`critiques and plans.md` section 12. There is no `sitemap.xml` either — it would need to be
generated from the database rather than committed; see section 9.

### Payload discipline

The home page used to fetch `GET /custom_images.json` — every image URL for
every character, around 475 KB — in order to display two integers. It is now one
`/api/stats` call returning a fixed summary, and `tests/test_customs_listing.py`
asserts the payload does not grow with the library.

The same rule now applies throughout: search and autocomplete are matched, sorted
and paged on the server over the catalog (`/api/catalog/search`,
`/api/catalog/characters`), so the roster is never downloaded and the character
page fetches the one record it shows; the customs list is searched, sorted and
paginated on the server; a character's gallery renders 600px WebP thumbnails
rather than the 1.9 MB PNGs ImgChest holds; and the profile's lists are the only
ones filtered in the browser, because they are bounded by what one person has
done rather than by the size of the library.

**Portraits.** A catalog portrait is a `mudae.net` hotlink. It is mirrored to R2
as WebP by `scripts/mirror_portraits_to_r2.py`, and the object key is stored in
`characters.main_image_thumb` / `character_catalog.mudae_image_thumb` (migration
012). Every character-shaped payload carries `image_thumb`, and the frontend
prefers it via `portraitUrl` — falling back to the original URL, which is also
what a development build does, where the mirror has no host.

One character page went from **488 MB** to **548 KB** across those changes.

**Accent override.** The measured accent can be overruled. A moderator or the
owner arms a picker in the character header and clicks a pixel on the portrait
or a gallery image; the server samples that pixel and stores it in
`characters.accent_override` (migration 013), written through to `accent_seed`
so every read path shows it. The extractor returns it and refuses to recompute
over it, including `scripts/recompute_accents.py`; clearing drops both and the
next visit measures afresh. The picks double as a labelled calibration set.

The full history of the accent logic — every idea tried, every version reverted,
and the numbers behind each — is in **[ACCENT.md](ACCENT.md)**.

---

## 7. CI

**There is none.** No `.github/` directory exists, and none ever has in this repository.

The workflow this section used to describe — `build-frontend.yml`, force-committing
`frontend/dist` back to `main` because `.do/app.yaml` used a Python buildpack that could not build
the frontend — belonged to v1 on DigitalOcean. `.do/app.yaml` is gone, `frontend/dist` is
gitignored and built locally, and Cloudflare Pages serves the SPA in production.

So nothing runs automatically: not the 732 backend tests, not the 566 frontend tests, not `ruff`,
not `biome`, and not `frontend/src/styles/tokenPairs.test.js`, which enforces the `DESIGN.md`
rules as executable invariants. The drift this allows is already visible — `uv run ruff check .`
reports 11 errors, nine of them in `mudae_discord.py`.

Two documents still assume CI exists and are wrong until one does:
`docs/DEVELOPMENT.md` ("Use `uv sync --locked` in CI") describes an intent, not a fact.

Adding checks does not disturb the deployment model. `DEPLOYMENT.md` explains that the origin box
*polls* rather than being pushed to, because it has no inbound access — that reasoning is about
deploys, and a workflow that only runs tests and linters needs no access to the box at all. See
`critiques and plans.md` section 10 for the plan.

---

## 8. Repository weight

The working tree is now small. `character_images/` — 1,000 default portraits, 151 MB — was
**removed from the repo**: the working rows carry catalog `mudae.net` URLs and their R2 WebP
mirrors, so nothing named the committed files, and the origin no longer serves them (the
`/images` and `/character_images` routes are gone).

This was a **forward-only** removal. The blobs are still in history, so `.git` remains ~154 MB and
a fresh clone is unchanged; reclaiming that needs a history rewrite (`git filter-repo`), which was
deliberately not done.

---

## 9. What does not exist

Most of what this section used to list — authentication, ownership, rate
limiting, soft delete, tests, migrations, structured logging — now exists. What
genuinely does not:

- **Any content rating.** `nsfw: "false"` is still hardcoded in the ImgChest
  payload (`imgchest_utils.py`), no image carries a rating, and nothing filters
  on one. The per-person `show_nsfw` preference is recorded against that day
  arriving, and reads as such in the UI.
- **A moderation queue.** Reports remove an image at two distinct reporters and
  that is still the whole mechanism; there is no appeal. The staff surface at
  `/profile/moderation` now *reads* them — the Reports tab lists reported images,
  split into those still live and those the threshold already removed — but it is
  inspection, not a queue: nothing is assignable, and the removal and restore
  verbs stay on the character page.
- **A sitemap, and any per-route metadata.** `robots.txt` exists and invites crawling, but there
  is no `sitemap.xml` to point crawlers at the ~707 characters that actually have images, and the
  SPA shell serves one title and description for every route (no Open Graph or Twitter card tags
  either). A sitemap would have to be **generated**, not committed: the character list changes
  constantly, so it belongs behind a Flask route reading the database, and it needs the production
  domain, which lives in the environment rather than the repo. See `critiques and plans.md`
  section 12.
- **Server-side sessions.** Identity is a signed cookie and nothing else.
- **A second origin.** One box serves everything; Cloudflare caches in front of
  it, and Litestream is the only redundancy.

---

## 10. Known bugs and risks

Still open:

| Issue | Location | Impact |
|---|---|---|
| Discord self-bot ToS | `mudae_service.py` | An account ban would remove every Mudae feature |
| The two databases have forked | v1 Neon vs v2 SQLite | See `CUTOVER.md`; the migration is insert-only and re-running gives the union |
| Uploads are WebP bytes under a `.png` name | `image_utils.py` | Rests on Discord sniffing content rather than trusting the extension. If that changes, every custom image stops rendering at once |
| No CI | — | Nothing runs the 1,298 tests or the linters automatically; `ruff` has already drifted to 11 errors |

The WebP-under-`.png` recovery path, recorded before it is needed: the original bytes are on
ImgChest and each row carries `content_hash` and `imgchest_post_id`, so re-encoding to real PNG and
re-uploading is mechanical — 8,562 uploads against ImgChest's rate limits, with `scripts/backfill_*.py`
as the shape to copy. A single canary image fetched periodically would turn a silent library-wide
failure into a noticed one; that is not built.

Fixed since this document was first written, kept here because the shape of each
is worth remembering:

| Was | Fixed by |
|---|---|
| Concurrent writes lost data (whole-blob read-modify-write) | Real rows and transactions |
| Anyone could delete anything | Ownership-scoped removal, soft delete, reports |
| No rate limiting anywhere | `ratelimit.py`, per identity, per action |
| `CORS: *` by default | Explicit origins; wildcards refused at startup |
| No tests at all | 732 backend, 566 frontend |
| `print()` with no actor | `logs.py`; identity attaches automatically inside a request |
| Health check could not fail | Reads the database; 503 when it cannot |
| Full-map fetch on the home page | `/api/stats`, with a test that it stays bounded |
| Uploads wrote next to the code | `tempfiles.py`; the server's filesystem is read-only |
| `THUMB_DIR`/`DATABASE_PATH` could silently default into the code tree | A startup guard refuses a deployed config whose durable paths land in the checkout |
| Hiding an unknown image id returned 500 | The insert selects from `custom_images`, so it is a no-op |
| Mudae lock was per-process, so two workers could connect at once | One dedicated `mudae_service` owns the connection (Phase 8) |
| Every lookup burned a Discord identify | The service connects on demand, reuses the session, and disconnects after 10 idle minutes (Phase 8) |
