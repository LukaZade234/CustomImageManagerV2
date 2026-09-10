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

### Schema — the entire thing

`db.py:104` creates one table and there are no others:

```sql
CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value JSONB NOT NULL)
```

Four rows, each holding one whole JSON document read and written atomically:

| Key | Shape | Accessors |
|---|---|---|
| `custom_images` | `{"Char Name": ["https://cdn.imgchest.com/...", ...]}` | `db.py:141` / `db.py:151` |
| `characters` | `[{name, series, rank, main_image_url}]` | `db.py:236` / `db.py:247` |
| `saved_characters` | `[{...character objects...}]` (bookmarks) | `db.py:161` / `db.py:171` |
| `last_updated` | `{"Char Name": 1712345678.9}` | `db.py:181` / `db.py:192` |

**A custom image is a bare URL string in a list.** No id, no timestamp, no uploader, no metadata.
Ordering is array position. There is nowhere to attach anything to an image without changing the
value type.

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

**No endpoint has any authentication or authorization.**

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/health` | — | Reads the DB; 503 if unreachable. Reports revision and character count |
| GET | `/api/last-updated` | 415 | `{char: timestamp}` |
| GET | `/`, `/saved`, `/add`, `/customs`, `/character/<name>` | 432–436 | SPA shell, `Cache-Control: no-cache` |
| GET | `/images/<filename>` | 451 | Serves `character_images/` off local disk |
| GET | `/character_images/<path>` | 456 | Same |
| GET | `/custom_images.json` | 462 | **Dumps every image URL for every character** |
| POST | `/api/download-image-proxy` | 473 | Server-side fetch for browser downloads |
| GET | `/assets/<path>` | 506 | Hashed SPA assets, `max_age=31536000` |
| GET | `/characters`, `/api/characters` | 515 | Character list |
| POST | `/upload` | 532 | Bare ImgChest upload; does not persist |
| GET | `/api/saved` | 592 | Bookmarks |
| POST | `/api/saved` | 592 | Add bookmark |
| POST | `/api/add-character` | 627 | Create a character |
| DELETE | `/api/saved/<name>` | 689 | Remove bookmark |
| POST | `/api/custom-image` | 703 | **Add images** (multipart) |
| POST | `/api/import-custom-images-from-urls` | 785 | Add by URL, max 20, SSRF-guarded |
| GET | `/api/custom-image/<char_name>` | 852 | One character's URL list |
| POST | `/api/reorder-custom-images` | 862 | Replaces the whole array |
| POST | `/api/delete-custom-image` | 885 | **Delete one** — `list.remove(url)` |
| POST | `/api/delete-custom-images` | 908 | **Delete many** — list-comprehension filter |
| POST | `/api/edit-character` | 936 | Rename; cascades across three KV keys |
| POST | `/api/set-main-image` | 1000 | Upload and set `main_image_url` |
| GET | `/api/mudae/status` | 1124 | `{configured: bool}` |
| GET | `/api/mudae/proxy-image` | 1129 | Proxy a Mudae CDN image |
| POST | `/api/mudae/lookup-character` | 1169 | `$im` lookup; `add:true` persists |
| POST | `/api/mudae/lookup-series` | 1218 | `$ima` series resolution |
| POST | `/api/mudae/add-series` | 1244 | Bulk import; SSE when `?stream=1` |
| POST | `/api/mudae/cancel-series` | 1326 | Cancels an in-flight bulk import |
| POST | `/api/mudae/refresh-main-image` | 1424 | Re-pull main image from Mudae |

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

React 18 + react-router-dom 6 + zustand + Vite 5. 4,035 lines.

| File | Lines | Notes |
|---|---|---|
| `pages/CharacterPage.jsx` | 1178 | Add / reorder / delete / select / download / `$ai`; the bulk of the app |
| `pages/AddPage.jsx` | 617 | Add character + Mudae series import |
| `pages/CustomsPage.jsx` | 295 | Browse all customs |
| `components/AiCommandLimitDialog.jsx` | 203 | `$ai` command length limits |
| `api.js` | 244 | Hand-rolled API client |
| `store/useStore.js` | 181 | One flat zustand store |
| `utils/dragImageUrls.js` | 165 | Drag-and-drop from other browser tabs |
| `components/ImageModal.jsx` | 146 | Lightbox |
| others | — | `HomePage` 68, `SavedPage` 62, `SearchResultsPage` 89, `Navbar` 71, `Toast` 74, etc. |

**State:** a single flat zustand store — `characters`, `savedCharacters`, `customImages` (the
entire map), `lastUpdated`, `darkMode`, `toasts`. No react-query/SWR, no normalized cache. Retry
and backoff are hand-written in both `useStore.js:61` and `api.js:59`.

**Only browser-persisted state is the theme choice** — `localStorage['darkMode']` at the time this
document was written, since replaced by `localStorage['theme']` with a three-state value
(`system` / `light` / `dark`) and a migration from the old boolean. See `DEVELOPMENT.md`.

**API client:** a plain object of functions in `api.js:51`, using a generic `api()` helper for
JSON plus bespoke `fetch` calls for multipart and SSE. `mudaeAddSeriesStream` (`api.js:169`)
hand-parses the SSE byte stream. All calls send `credentials: 'same-origin'`, but nothing is sent
because nothing is stored.

**Serving:** Flask serves the SPA shell for the five client routes with `Cache-Control: no-cache`
(`upload_imgchest.py:432`) and hashed assets from `/assets/` with a one-year max-age (`:459`).

### The obvious performance problem

`GET /custom_images.json` returns **every image URL for every character**. `HomePage` fetches the
whole thing (`useStore.js:61`) purely to compute two summary numbers
(`HomePage.jsx:16`):

```js
const totalImages = Object.values(customImages).reduce((sum, arr) => sum + (arr?.length || 0), 0)
const charsWithCustoms = Object.keys(customImages).filter((k) => (customImages[k]?.length || 0) > 0).length
```

This grows without bound as the library grows and is paid on every home-page visit.

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

- **Authentication** — no sessions, cookies, API keys, or `Authorization` parsing on any route
- **Authorization** — no ownership, roles, or permissions of any kind
- **Rate limiting** — nothing on the HTTP API. The only throttles are a client-side upload mutex
  in `CharacterPage.jsx`, the per-process Mudae lock, and ImgChest retry backoff
- **Audit log** — only `print()` to stdout with `[UPLOAD]` / `[IMPORT]` / `[MUDAE]` prefixes, none
  of which record an actor. `db.update_last_modified` is the only persisted trace of a mutation:
  a timestamp with no who and no what
- **Soft delete or trash** — server-side deletes are immediate and destructive. The only undo is
  client-side and optimistic (`CharacterPage.jsx:635`): it snapshots the array, and an 8-second
  toast calls `reorderCustomImages` to write the old array back. It works only because the files
  are still on ImgChest, only within that tab's lifetime, and it **silently clobbers concurrent
  edits by other visitors**
- **Moderation** — none. `nsfw: "false"` is hardcoded in the ImgChest payload
  (`imgchest_utils.py:82`) and that is the entire extent of it
- **Tests** — zero. No pytest, vitest, or jest anywhere
- **Migrations** — `CREATE TABLE IF NOT EXISTS` at startup; no versioning
- **Structured logging** — `print(..., flush=True)` throughout

---

## 10. Known bugs and risks

| Issue | Location | Impact |
|---|---|---|
| Concurrent writes lose data | `db.py` — no transactions, whole-blob RMW | Images silently vanish; looks like griefing |
| Anyone can delete anything | `upload_imgchest.py:885`, `:826` | The griefing problem that motivated this rework |
| No delete confirmation | `CharacterPage.jsx:635` | Accidental bulk deletion |
| `CORS: *` by default | `upload_imgchest.py:380` | Any webpage can drive a visitor's browser into mutating endpoints |
| No rate limiting | Everywhere | A trivial script can empty the library |
| Mudae lock is per-process | `mudae_discord.py:131` + 2 workers | Concurrent Discord connections |
| Only 2 concurrent requests site-wide | `--workers 2`, sync class | Two slow requests make the site appear down |
| SSE imports over 120s are SIGKILLed | `--timeout 120` + sync worker | Large series imports stop dead mid-stream |
| Four-way Python version mismatch | `.python-version` / venv / Dockerfile / pyright | Dev on 3.14, deploy on 3.11 |
| No lockfile, 8/10 deps unbounded | `requirements.txt` | Builds are not reproducible |
| 5 npm vulnerabilities (2 high) | `esbuild`, `nanoid`, `react-router` | Fixed by the pending major upgrades |
| Discord identify quota burn | `mudae_discord.py:1348` | Connect/disconnect per request, ~1000/day cap |
| Discord self-bot ToS | `mudae_discord.py` | Account ban would remove all Mudae features |
| ~~`SECRET_KEY` unused~~ | — | Fixed in Phase 6: required in production, no hardcoded default. |
| Full-map fetch on Home | `HomePage.jsx:16` | Unbounded payload growth |
| Undo clobbers concurrent edits | `CharacterPage.jsx:635` | Restores a stale array wholesale |
| Dead code | `character_mapping.js`, `github_utils.py` | 260 KB and confusion |
| Two conflicting deploy paths | `Dockerfile` vs `.do/app.yaml` | Unclear which is authoritative |
