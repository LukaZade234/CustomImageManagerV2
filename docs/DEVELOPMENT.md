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

The suite needs PostgreSQL. If `TEST_DATABASE_URL` is unset, `tests/conftest.py`
starts a throwaway `postgres:16-alpine` container via podman on port 55432 and
reuses it across runs. To use your own instead:

```bash
TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/imgmgr_test uv run pytest
```

> **Safety.** `upload_imgchest.py` calls `load_dotenv()` at import time, and `.env`
> holds the **production** `DATABASE_URL`. `conftest.py` therefore overwrites
> `DATABASE_URL` before any application module is imported, and refuses to run at
> all against a non-local host or a known managed-database hostname. Do not weaken
> those guards — without them, running the suite would write to live user data.

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

`db.py` deliberately exposes **no setter**. Reads are `get_*`; every write goes through
`mutate_*`, which opens a transaction, takes an advisory lock on the key, reads the
document, hands it to your function to edit **in place**, and writes it back:

```python
# Correct: atomic.
db.mutate_custom_images(lambda data: data.setdefault(name, []).extend(urls))

# Correct: the mutator's return value comes back to you, so a route can still
# choose its status code.
def _delete(data: dict) -> str:
    urls = data.get(name)
    if urls is None:
        return "no_character"
    urls.remove(image_url)
    return "deleted"

outcome = db.mutate_custom_images(_delete)
```

The two-call pattern — `data = get_x()`, mutate, `set_x(data)` — is what caused the
original data loss: two overlapping requests both read the same document and the second
write discarded the first. Do not add a setter back to make that possible again.

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
