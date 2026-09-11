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

SQLite, one file, replicated to R2 by Litestream. Ten tables, created by the
migrations in `migrations/` and applied on first connect.

The v1 shape was a single Postgres `kv_store` table holding four whole JSON
documents, in which a custom image was a bare URL string in a list — no id, no
timestamp, no uploader, nowhere to attach anything. Everything below exists
because that had to stop being true.

| Table | Rows (prod) | What it holds |
|---|---|---|
| `custom_images` | 8,560 | The library. Id, url, content hash, position, owner, state, dimensions |
| `characters` | 1,705 | Name, series, rank, main image, timestamps |
| `image_takes` | 271 | `copy_command` / `download` events, per image |
| `rate_limit_hits` | — | Fixed-window counters, swept after a day |
| `character_views` | — | One row per person per character per hour |
| `identities` | 7 | Cookie pseudonyms, optional Discord binding, role, display preferences |
| `saved` | — | Bookmarks, per identity |
| `user_hidden` | — | Per-viewer hidden images |
| `image_reports` | — | Two distinct reporters remove an image |
| `schema_migrations` | 6 | Which migrations have run |

Indexes worth knowing: `idx_characters_name_nocase` (case-insensitive lookup),
`idx_custom_images_hash` (duplicate detection by content, not URL),
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
pseudonym to an account, merging the two identities.

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

6,361 lines of Python.

| File | Lines | Role |
|---|---|---|
| `upload_imgchest.py` | 248 | App construction, CORS, identity hooks, status endpoints |
| `routes/customs.py` | 601 | Custom images: add, order, remove, hide, report |
| `routes/mudae.py` | 454 | Mudae lookup, series import, portrait refresh |
| `routes/characters.py` | 323 | Characters, saved list, main image |
| `routes/media.py` | 117 | Thumbnails, static images, the download proxy |
| `routes/auth.py` | 117 | Discord sign-in |
| `routes/spa.py` | 56 | Serving the built React app |
| `logs.py` | 140 | Logfmt logging, with identity attached inside a request |
| `validation.py` | 33 | Character field limits and name checks |
| `mudae_discord.py` | 1552 | Discord self-bot automation and Mudae embed parsing |
| `db.py` | 1061 | SQLite/Postgres data layer |
| `remote_images.py` | 330 | SSRF guards, remote fetch, ImgChest naming |
| `identity.py` | 235 | Cookie pseudonyms and the Discord binding |
| `image_utils.py` | 206 | Pillow validation, format detection, WebP conversion |
| `imgchest_utils.py` | 198 | ImgChest upload client with retry/backoff |
| `discord_auth.py` | 169 | OAuth2 flow (`identify` scope only) |
| `ratelimit.py` | 100 | Per-identity fixed-window limits |
| `thumbnails.py` | 96 | On-demand WebP thumbnails |
| `gunicorn.conf.py` | 85 | Production server config |
| `app.py` | 10 | WSGI shim |
| `scripts/` | 601 | Migration, backfill and snapshot scripts |

### 5.1 `upload_imgchest.py` and `routes/`

`@app.route` needs the app object to exist when the decorator runs, so every route had to sit below
`app = Flask(__name__)` in one module — that, not neglect, is why the file was 1,700 lines. A
Blueprint records the same declarations without an app, so each subject now lives in its own module
under `routes/` and `upload_imgchest` attaches them at the bottom. The import goes one way only.

Paths are unchanged: a blueprint owns a subject, not a URL prefix. `upload_imgchest.py` keeps what
belongs to the app rather than to any subject — the Flask object and SECRET_KEY, CORS, the identity
hooks, the upload guard, the database-configuration error handler, and `/api/health`, `/api/stats`
and `/api/last-updated`.

**Note for tests.** A route calls an imported helper as a name in **its own** module's namespace.
So `monkeypatch.setattr("routes.media._get_with_validated_redirects", ...)` patches what the
thumbnail route uses, while patching `remote_images` patches what the helper itself calls. Both are
correct for different targets, and picking the wrong one fails silently — the test passes for the
wrong reason, or makes a real network call. Whenever a route moves module, every monkeypatch aimed
at its old home has to move with it.

App setup (`upload_imgchest.py:377`):
```python
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
_origins = os.environ.get("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in _origins.split(",")] if _origins != "*" else "*"
CORS(app, origins=cors_origins)
Compress(app)
```

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
| POST | `/api/add-character` | Add a new character. |
| GET | `/api/characters` | — |
| POST | `/api/characters/<path:name>/view` | Note that the caller looked at this character. |
| POST | `/api/edit-character` | — |
| GET | `/api/saved` | — |
| POST | `/api/saved` | — |
| DELETE | `/api/saved/<path:name>` | — |
| POST | `/api/set-main-image` | — |
| GET | `/characters` | — |
| POST | `/upload` | — |

**`customs`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/custom-image` | — |
| GET | `/api/custom-image/<path:char_name>` | Active images for one character, annotated for the caller. |
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
| GET | `/character_images/<path:filename>` | — |
| GET | `/images/<filename>` | — |
| GET | `/thumbs/<int:image_id>.webp` | A small WebP of one image, generated on first request and cached. |

**`mudae`**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/mudae/add-series` | Bulk-add characters from a series via $ima then $im each. |
| POST | `/api/mudae/cancel-series` | Request stop of an in-progress bulk series import (checked between characters). |
| POST | `/api/mudae/lookup-character` | Lookup a character via Mudae $im. |
| POST | `/api/mudae/lookup-series` | Resolve a series name via Mudae $ima. |
| GET | `/api/mudae/proxy-image` | Proxy a remote character image for browser preview (Discord CDN often blocks hotlinking). |
| POST | `/api/mudae/refresh-main-image` | Fetch character card image from Mudae $im and set as main image. |
| GET | `/api/mudae/status` | — |

**`spa`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | — |
| GET | `/add` | — |
| GET | `/assets/<path:filename>` | — |
| GET | `/character/<path:name>` | — |
| GET | `/customs` | — |
| GET | `/saved` | — |

**`upload_imgchest`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Is this deployment actually serving? 200 if yes, 503 if not. |
| GET | `/api/last-updated` | — |
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

A **Discord self-bot**: it logs into the operator's own personal Discord account using
`DISCORD_USER_TOKEN`, posts `$im` / `$ima` in a fixed channel, and parses Mudae's embed replies.
It does not introduce any end-user identity — every request is attributed to the operator's
account. Identity checks are only "is this message from the Mudae bot"
(`mudae_discord.py:897`, `:1142`).

**Architecture: connect per request, not persistent.** `mudae_discord.py:1348` is
`asyncio.run(coro)` — each request creates a fresh event loop, calls `client.start()`
(`:1097`), waits up to 30s for ready (`:1099`), does its work, then tears the client down
(`:1127`). Two consequences:

- The guarding `threading.Lock` (`mudae_discord.py:131`) is **process-global, and gunicorn runs
  2 workers** — two concurrent Mudae requests landing on different workers will both connect
  simultaneously, defeating the lock entirely.
- Every lookup consumes one Discord *identify*, which is rate-limited to roughly 1000/day per
  account.

Pacing constants (`:24`–`:32`): `REPLY_TIMEOUT_S = 25.0`, `IM_INTERVAL_S = 1.0`,
`IMA_PAGE_DELAY_S = 2.2`, `MAX_IMA_PAGES = 40`, `CHARACTER_LOOKUP_RETRIES = 2`. An `_ImPacer`
class (`:157`) enforces minimum spacing between `$im` sends.

Parsing is extensive and fragile — roughly 40 helpers reverse-engineering Mudae's embed format
(`parse_im_embed` `:421`, `parse_ima_series_reply` `:528`, plus claim-rank, series, and
nav-button/reaction handling). It breaks whenever Mudae changes its output.

Bulk series import streams progress to the browser over **SSE**, with cancellation via a
`threading.Event` (`:128`).

**Risk:** automating a user account violates Discord's Terms of Service. v1's `DEPLOY.md` (since
replaced by `DEPLOYMENT.md`) already
notes this. The account can be banned, which would take out all Mudae features.

---

## 6. Frontend

React 18 + react-router-dom 6 + zustand + Vite. 6,663 lines across 60-odd files,
none of them over 700.

| Area | Lines | Notes |
|---|---|---|
| `pages/CharacterPage.jsx` | 684 | The gallery and its five modes. Was 1,611 |
| `pages/AddPage.jsx` | 645 | Add character + Mudae series import. Not yet split |
| `api.js` | 356 | Hand-rolled API client |
| `pages/CustomsPage.jsx` | 320 | Browse all customs, filtered server-side |
| `pages/HomePage.jsx` | 302 | Totals, just-added, most-visited, popular characters and series |
| `components/GalleryToolbar.jsx` | 281 | The gallery's mode bar, lifted out of CharacterPage |
| `hooks/useGalleryReorder.js` | 266 | Pointer-events drag-to-reorder, mouse and touch |
| `pages/profile/` | ~700 | Five tabs: settings, saved, history, hidden, removed |
| `components/ui/` | ~370 | The primitives |

**Pages.** `/`, `/customs`, `/search`, `/add`, `/character/:name`, and `/profile`
with five nested tab routes. `/saved` redirects into the profile, where the list
now lives.

**State:** one flat zustand store — characters, saved, the current character's
customs, `me`, theme, toasts. No react-query yet (Phase 9). Retry and backoff are
hand-written in `useStore.js` and `api.js`.

**Styling:** a token layer plus primitives, loaded in order by
`styles/index.css`: tokens → base → layout → ui → components → pages. `ui` must
load before `components` and `pages` so a call site can adjust a primitive;
getting that order wrong has silently broken the search bar twice. `legacy.css`
is gone. See `DEVELOPMENT.md`.

**Identity in the UI.** The navbar carries one profile button showing your
handle. Sign-in, sign-out, theme and the privacy switches all live on
`/profile`. Ownership is shown per image only where it changes what you can do.

### Payload discipline

The home page used to fetch `GET /custom_images.json` — every image URL for
every character, around 475 KB — in order to display two integers. It is now one
`/api/stats` call returning a fixed summary, and `tests/test_customs_listing.py`
asserts the payload does not grow with the library.

The same rule now applies throughout: the customs list is searched, sorted and
paginated on the server; a character's gallery renders 600px WebP thumbnails
rather than the 1.9 MB PNGs ImgChest holds; and the profile's lists are the only
ones filtered in the browser, because they are bounded by what one person has
done rather than by the size of the library.

One character page went from **488 MB** to **548 KB** across those changes.

---

## 7. CI

`.github/workflows/build-frontend.yml` — on push to `main` touching `frontend/**`, runs
`npm run build` and **force-commits `frontend/dist` back to `main`** with `[skip ci]`:

```
git add -f frontend/dist
git diff --staged --quiet || git commit -m "Build frontend [skip ci]"
git push
```

`frontend/dist` is in `.gitignore`, hence the `-f`. This exists only because `.do/app.yaml` uses a
Python buildpack that cannot build the frontend. It is the source of the many "Build frontend
[skip ci]" commits in history. There is **no test or lint job** — the only static checking is
`pyrightconfig.json`, run manually.

---

## 8. Repository weight

| Item | Size |
|---|---|
| `.git` | 154 MB |
| `character_images/` (1000 PNGs) | 151 MB |
| `character_mapping.js` | 260 KB |
| `frontend/dist` (committed) | 300 KB |

`character_images/` holds default main images for the top 1000 characters by rank. They are not
custom images and not what users take away — low value, and slated to move to ImgChest.

`character_mapping.js` is **dead code**: it sets `window.CHARACTER_MAPPING` with Windows-style
backslash paths from a pre-React era and has **zero references** anywhere in the repository.

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
  that is the whole mechanism; there is no review screen and no appeal.
- **Server-side sessions.** Identity is a signed cookie and nothing else.
- **react-query or any normalised cache** (Phase 9). Retry and backoff are
  hand-written in two places.
- **A second origin.** One box serves everything; Cloudflare caches in front of
  it, and Litestream is the only redundancy.

---

## 10. Known bugs and risks

Still open:

| Issue | Location | Impact |
|---|---|---|
| Mudae lock is per-process | `mudae_discord.py` + 2 workers | Two concurrent lookups can connect at once and capture each other's replies |
| Discord identify quota burn | `mudae_discord.py` | Connect/disconnect per request against a ~1000/day cap |
| Discord self-bot ToS | `mudae_discord.py` | An account ban would remove every Mudae feature |
| `THUMB_DIR` / `DATABASE_PATH` default inside the code tree | `thumbnails.py`, `db.py` | Production sets both; unset, they would fail the way uploads did under `ProtectSystem=strict` |
| SSE imports over the worker timeout | `gunicorn.conf.py` | A very large series import can still be cut off mid-stream |
| The two databases have forked | v1 Neon vs v2 SQLite | See `CUTOVER.md`; the migration is insert-only and re-running gives the union |

Fixed since this document was first written, kept here because the shape of each
is worth remembering:

| Was | Fixed by |
|---|---|
| Concurrent writes lost data (whole-blob read-modify-write) | Real rows and transactions |
| Anyone could delete anything | Ownership-scoped removal, soft delete, reports |
| No rate limiting anywhere | `ratelimit.py`, per identity, per action |
| `CORS: *` by default | Explicit origins; wildcards refused at startup |
| No tests at all | 316 backend, 249 frontend |
| `print()` with no actor | `logs.py`; identity attaches automatically inside a request |
| Health check could not fail | Reads the database; 503 when it cannot |
| Full-map fetch on the home page | `/api/stats`, with a test that it stays bounded |
| Uploads wrote next to the code | `tempfiles.py`; the server's filesystem is read-only |
| Hiding an unknown image id returned 500 | The insert selects from `custom_images`, so it is a no-op |
