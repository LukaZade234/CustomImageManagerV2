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
- **The gunicorn worker configuration is deliberately unchanged** until the Phase 2 data
  layer is transactional. Raising concurrency first would lose more data, not less. See
  `DECISIONS.md` section 7.
