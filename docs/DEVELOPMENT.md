# Development

Commands and conventions for working on this repository. What the code currently
*is* lives in `CURRENT_STATE.md`, what to do next in `ROADMAP.md`, and why in
`DECISIONS.md`.

## Setup

Python is managed by [`uv`](https://docs.astral.sh/uv/); the interpreter version is pinned in
`.python-version` and enforced by `pyproject.toml`.

```bash
uv sync                       # create .venv and install from uv.lock, exactly
cd frontend && npm ci         # install from package-lock.json, exactly
```

The database is a single SQLite file at `data/imgmanager.db` (override with
`DATABASE_PATH`). It is created and migrated automatically on first connection;
`migrations/*.sql` are applied in filename order and recorded in
`schema_migrations`. To load the v1 data:

```bash
uv run python scripts/export_neon_snapshot.py            # read-only, from the live v1 DB
uv run python scripts/migrate_v1_to_sqlite.py --dump kv_store.sql
```

Use `uv sync --locked` in CI: it fails if `uv.lock` has drifted from `pyproject.toml`
rather than silently resolving something new.

## Running

```bash
# Backend (needs DATABASE_URL and IMGCHEST_API_KEY in .env)
uv run python upload_imgchest.py --web        # http://localhost:5000

# Frontend dev server, proxies /api to :5000
cd frontend && npm run dev                    # http://localhost:3000
```

## Tests

### Backend

```bash
uv run pytest                 # everything
uv run pytest -v              # per-test names
```

No setup: `tests/conftest.py` creates a temporary SQLite file per run and deletes
it afterwards. To point the suite at your own database instead:

```bash
TEST_DATABASE_PATH=/tmp/mine.db uv run pytest
```

> **Safety.** `DATABASE_PATH` is overwritten at collection time, before any
> application module is imported, so a value inherited from the environment or
> `.env` cannot reach the app. The harness also refuses to run against the working
> database at `data/imgmanager.db`, or against any path outside a temp directory.
> Do not weaken those guards — the hazard is quieter than it was when the database
> was remote, not smaller.

### Frontend

```bash
cd frontend
npm test                      # vitest, single run
npm run test:watch
npm run test:coverage
```

## Frontend deployment configuration

`frontend/src/config.js` is the single place that knows where things live:

| Variable | Unset (local dev) | Production |
|---|---|---|
| `VITE_API_BASE_URL` | empty — Vite proxies to Flask | `https://api.<domain>` |
| `VITE_IMAGE_BASE_URL` | empty — Flask serves from disk | `https://images.<domain>` |

Both are **inlined at build time**, so changing either needs a rebuild, and nothing
secret may go in them. Copy `frontend/.env.example` to `.env.production` for a
local production-shaped build.

Requests always use `credentials: 'include'`, never `'same-origin'`. Once the SPA
is on Pages, `'same-origin'` silently stops sending cookies — which would break
identity in a way that reads as "everyone is a new person" rather than as an
error. That obliges the API to send `Access-Control-Allow-Credentials` and to name
an exact origin, which is why `CORS_ORIGINS=*` is refused at startup rather than
tolerated.

## Quality gates

```bash
uv run ruff check .           # lint
uv run ruff format .          # format
uv run pyright                # types

cd frontend
npm run lint                  # biome
npm run format                # biome, writes
npm run typecheck             # tsc --noEmit
npm run build
```

TypeScript is adopted **incrementally**: `allowJs: true`, `checkJs: false`. Existing
`.js`/`.jsx` are not type-checked; convert a file to `.ts`/`.tsx` and it is. Shared API
shapes live in `frontend/src/types.ts`.

## Frontend styling

There is no CSS framework and no CSS-in-JS. Styling is a token layer plus a small set of
primitives, loaded in this order by `frontend/src/styles/index.css`:

| File | What belongs in it |
|---|---|
| `tokens.css` | Every custom property. Colour, spacing, radius, elevation, type, motion, layers. |
| `base.css` | Reset, element defaults, shared typography classes, the focus ring, `@font-face`. |
| `layout.css` | The page frame, including the navbar and the search cluster in it. |
| `ui.css` | The primitives: the default appearance of a button, input, card, modal. |
| `components.css` | Shared things built from the primitives — toasts, dialogs, the autocomplete, skeletons, empty states. |
| `pages.css` | Rules belonging to one page. New page CSS goes here. |

`ui.css` loads before `components.css` and `pages.css` so a call site can adjust
a primitive — position a save button, pill-shape a search field. Putting it last
inverted that and silently broke both search layouts.

`legacy.css` is gone. Its 239 rules moved into `layout`, `components` and
`pages` without being reordered, so the cascade is unchanged; the built
stylesheet came out 30 bytes smaller, all of it one merged toast rule.

Four rules, all of which the codebase previously broke:

**No colour literal outside `tokens.css`.** Not a hex value, not `white`, not an `rgba()`. If a
colour is needed that no token expresses, add the token — in all three theme blocks. The old
`App.css` had 387 hex literals across 85 distinct colours and no way to change any of them once.

**No raw spacing, radius or shadow values.** Use `--space-*`, `--radius-*`, `--shadow-*`. A
one-off positioning offset that is genuinely not spacing (`--search-toggle-width`) can be a local
custom property on the rule that needs it, named and commented.

**No inline `style` objects for appearance.** They cannot respond to the theme and they cannot be
overridden. `style={{ display: 'none' }}` on a hidden file input is the only accepted use; anything
else gets a class. There were 76 of these, four of which hardcoded colours with no dark-mode
counterpart.

**Reach for a primitive before writing a button, input, card or dialog.** `frontend/src/components/ui`
exports `Button`, `IconButton`, `Card`, `Badge`, `Input`, `Select`, `Field`, `SegmentedControl`,
`Modal`, `EmptyState` and the `useDialog` hook. If a caller needs a size or variant that does not
exist, add it to the primitive rather than passing an inline override — the previous stylesheet had
eight button styles sharing no base and the same size override repeated fifteen times in one file.

### Theming

Three states: `system` (the default), `light`, `dark`. The DOM contract is a `data-theme`
attribute on `<html>`, **present only for an explicit choice** — its absence is what lets
`prefers-color-scheme` decide. Never write `data-theme="system"`.

`tokens.css` therefore defines every colour three times, and the order matters:

```css
:root { ... }                                              /* complete light palette */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { ... }                  /* system dark */
}
:root[data-theme="dark"] { ... }                           /* explicit dark wins */
```

A colour whose only definition lives inside a media query or a `[data-theme]` block will be
missing in browsers that match neither. `frontend/src/theme.js` owns the storage key, the
migration from the old `darkMode` boolean, and the cycle order; `index.html` repeats the read
inline in `<head>` so an explicit choice never flashes the other theme.

Dark mode used to be 144 hand-written `body.dark-mode` override selectors and 33 `!important`
declarations. Do not add another. Biome's `noImportantStyles` is on to enforce it.

### Breakpoints

Four, and only four: **480, 768** (`769` for the `min-width` complement), **960, 1200**. They are
documented in `tokens.css` rather than declared, because media queries cannot read custom
properties. The sheet previously mixed nine unnamed values in both directions.

## Identity and ownership

Every request has a caller. `identity.py` issues a signed cookie on first visit and
`identity.current_identity()` resolves it; there is no login and never a login wall.

Three rules that are easy to break:

**Create the identity row before storing a reference to it.** Rows in `identities` are
created lazily, on first write, so a cookie can exist with no row behind it. Any
insert carrying an `identity_id` must call `db.ensure_identity` first or the foreign
key rejects it. Code reading a role must tolerate a missing row and default to `user`.

**Never return the identity id to the client.** The cookie is HttpOnly precisely so
script cannot read it; handing the same value back in JSON gives that away for
nothing. Ownership is reported as a handle plus an `is_mine` boolean, and `/api/me`
returns no id at all. There is a test asserting exactly this.

**Removal is always soft, and always scoped.** `db.remove_custom_images` sets
`state='removed'`; nothing hard-deletes an image, because ImgChest keeps the file
regardless and the moderation design depends on every removal being restorable. It
removes only rows the caller owns unless they are a moderator, and returns
`{removed, denied, missing}` rather than a bare success — a mixed selection is the
normal case and the UI has to be able to explain a partial refusal.

**Privacy settings hide a name; they never drop the link.** `hide_attribution` and
`hide_from_leaderboard` are applied when rendering — `db.get_custom_image_rows`
decides what owner to report, and the contributor query filters on the flag.
Ownership itself is always stored, because removal is ownership-scoped: an
uploader who could not be identified could not manage their own uploads, and the
image would join the 8,547 permanently-unowned ones migrated from v1. Storing it
regardless is also what makes both switches retroactive and reversible. You can
always see your own name, and so can staff, who need it to moderate.

`SECRET_KEY` signs the cookies. It has no default: a deployed configuration (one with
`CORS_ORIGINS` set) refuses to start without it, and local development gets a random
per-process key with a warning. If it ever changes in production, every visitor
silently becomes a new person and loses ownership of their uploads.

## Rate limiting and URL fetching

Every costly endpoint is wrapped in `@rate_limited("<action>")`. Limits live in
`RATE_LIMITS` in `ratelimit.py`, one or more `(limit, window seconds)` pairs per
action, each overridable with `RATE_LIMIT_<ACTION>="30/60,300/3600"`. A new endpoint
that uploads, calls Discord, or writes in a loop needs one; the decorator raises
`KeyError` on a name with no entry, which a test catches.

The counter is `db.check_rate_limit`, which **increments before it reads**. Reading
first and then incrementing lets two concurrent requests both see "one under the
limit" — the same check-then-act race the database rules warn about. It counts
attempts rather than successes on purpose: an upload that fails still cost an ImgChest
call, and a client hammering failures is what needs stopping.

**Two endpoints fetch a URL the caller supplies** — the drag-from-web import and the
Mudae image proxy. Both run on the origin, inside a private network with a metadata
service on it, so both go through `_safe_import_image_url` and
`_get_with_validated_redirects`. Never call `requests.get` on a caller-supplied URL
directly, and never pass `allow_redirects=True` with one: that follows the chain
itself and hands back only the final URL, so a hop through a private host is fetched
before anything can object. `_ip_is_blocked` covers the ranges `ipaddress` has no flag
for, including IPv4-mapped IPv6 and RFC 6598 carrier NAT.

Known residual risk, documented in the code: DNS rebinding. The hostname is resolved
for validation and again by `requests` when it connects, so a hostile resolver can
answer differently each time.

## Logging

Never `print()`. Use the logger:

```python
import logs

log = logs.get(__name__)

log.info("customs.added", character=char_name, count=len(links))
log.warning("upload.rejected", filename=fn, reason="too_large", size_mb=31.4)
log.exception("customs.remove_failed")          # inside an `except`, keeps the traceback
```

Output is logfmt on stdout, which systemd sends to the journal:

```
2026-09-10T14:24:25Z ERROR customs.hide_failed path=/api/hide-images actor="Candid Whooper"
```

Three conventions, and only the first is arbitrary:

- **The message is an event name**, `subject.verb_past_tense`, not a sentence. It is what you grep
  for, so it has to survive rewording — `log.info("upload.succeeded")`, never
  `log.info(f"upload of {fn} succeeded")`. Anything variable is a field.
- **`log.exception` inside an `except`**, never `log.error(f"...: {e}")`. It keeps the traceback,
  which the f-string throws away precisely when you need it.
- **Do not pass identity or the request path.** A logging filter attaches `actor` and `path`
  automatically inside a request, so every mutation is attributable whether or not the author
  remembered. Outside a request — scripts, the self-bot — those fields are simply absent.

`LOG_LEVEL` (default `INFO`) controls verbosity; the noisy per-file upload steps are `debug`.

Reading them in production: `journalctl -u imgmanager -f`, and
`journalctl -u imgmanager | grep 'actor="Some Name"'` for one person's trail.

## Writing files

**Never write next to the code.** The unit sets `ProtectSystem=strict` with
`ReadWritePaths=/var/lib/imgmanager`, so the working directory `/opt/imgmanager`
is read-only in production. Uploads used to land in `./temp_custom_<name>`, which
works from a checkout and failed on the server for every upload ever attempted
there — the tests did not catch it because they, too, run somewhere writable.

Use `tempfiles.reserve(prefix, original_filename)` for anything short-lived and
`tempfiles.discard(path)` in a `finally`. It writes to the temp directory, which
`PrivateTmp=true` makes private to the service and empties on restart, and it
gives every file a unique name — the old scheme named the file after the upload,
so two people adding `image.png` at once overwrote each other.

Anything durable belongs under `DATABASE_PATH` or `THUMB_DIR`. Both currently
*default* to directories inside the code tree, which production overrides; if you
add a third such path, give it the same treatment and set it in `secrets.env`.

`tests/test_tempfiles.py` makes the working directory read-only and uploads
anyway, which is the shape any test of this needs.

## Writing to the database

`db.py` wraps SQLite (`sqlite3`, standard library). There is no ORM and no query
builder — read the SQL.

```python
db.get_custom_images_for(name)  # one character's active images
db.add_custom_images(name, urls)  # returns how many landed
db.delete_custom_images(name, urls)  # 'no_character' | 'no_match' | 'deleted'
db.reorder_custom_images(name, new_order)  # False if the character is unknown
```

Two rules that are easy to break and expensive to debug:

**Never check-then-insert.** This is a race — two callers both see the row missing,
both insert, one dies on the UNIQUE constraint:

```python
if not exists(name):  # WRONG
    conn.execute("INSERT ...")
```

Let the constraint decide instead, and read the outcome:

```python
cur = conn.execute("INSERT ... ON CONFLICT (name) DO NOTHING", ...)
if cur.rowcount:
    ...
```

This bug was written and caught by `test_many_concurrent_adds_all_persist` during
Phase 3. It is the same read-modify-write hazard Phase 2 removed, wearing a
different hat.

**Foreign keys need turning on.** SQLite ignores `REFERENCES` unless
`PRAGMA foreign_keys = ON` is set on **every** connection. `db.py` does this in
`_configure`; any new connection path must too, or the constraints are decoration.

## Conventions

- **Lint findings that need judgement are left unfixed on purpose.** Ruff and Biome
  auto-fixes are applied only where the tool classifies them as safe. Anything that
  alters logic waits until there is a test covering it.
- **`app.py`'s import is a re-export**, not dead code — gunicorn runs `app:app`. It has an
  explicit `__all__` so linters leave it alone. Removing it breaks every deployment.
- **A `strict` xfail marks a known bug**, not a flaky test. When the bug is fixed the test
  XPASSes and fails the suite, forcing the marker to be removed. Do not convert one to a
  skip.
- **The frontend build does not type-check JSX.** A component referencing an identifier it never
  imported builds cleanly and fails only in the browser. `pages.smoke.test.jsx` renders every
  route for exactly this reason — it caught precisely that bug during the design-system work.
  Add a page there when you add a route.
- **Gunicorn settings live in `gunicorn.conf.py`,** not in the command line, and each is
  commented with why. Override at runtime with `WEB_WORKERS`, `WEB_THREADS`, `WEB_TIMEOUT`.
  The worker class is `gthread` on purpose: gevent monkey-patches sockets and conflicts with
  the `asyncio` Discord client. See `DECISIONS.md` section 7.
