# Critiques and Plans

A code review of CustomImageManager v2 carried out on **2026-09-16**, with each finding written up
as an independently executable plan.

**This is a working document, not a decision record.** It does not carry the authority of
`docs/DECISIONS.md` or `docs/CURRENT_STATE.md`, and it should be deleted or folded into those once
its sections are done. Where it disagrees with the curated docs, the curated docs win.

## How to use this document

Each section is written to be handed to someone — or something — with **no other context**. A model
given only section 4 should be able to complete it without reading sections 1–3 and without asking
questions. Every section therefore repeats its own evidence, file paths, current code, target code,
verification commands, and an explicit *Out of scope* list.

Two rules for anyone executing a section:

1. **Verify the evidence before acting on it.** Line numbers drift. Every section gives the command
   that produced its numbers; run it first. If the code no longer matches what is quoted, the finding
   may already be fixed — say so rather than forcing the change.
2. **Do only your section.** The *Out of scope* list exists because these were written to be done by
   different people at different times. Sections 3 and 8 in particular must not be attempted
   together.

## Priority

| # | Finding | Severity | Effort | Risk |
|---|---|---|---|---|
| 1 | `/api/reorder-custom-images` is unauthenticated and unlimited | **High** — griefing vector | Low (a), Medium (b) | Low |
| 2 | No code splitting: 442 KB to every anonymous visitor | **High** — hits every user | Low | Low |
| 3 | `CharacterPage.jsx` is a 1,113-line function | Medium — maintainability | High | **High** |
| 4 | 26 endpoints return raw exception text to the browser | Medium — disclosure + UX | Low | Low |
| 5 | No index on `custom_images.added_by` / `removed_by` | Medium — latent | Very low | Very low |
| 6 | `/api/stats` uncached, 6+ heavy queries per landing-page load | Medium | Low | Low |
| 7 | Three coexisting data-fetching patterns | Low — consistency | Medium | Low |
| 8 | `db.py` and `pages.css` are dumping grounds | Low — optional | High | Medium |
| 9 | Ten of eleven `ui/` primitives are untested | Low | Low | None |

Recommended order: **1, 2, 5, 4, 6** first — they are high value and low risk. Then 9 and 7. Sections
3 and 8 are large refactors that should be scheduled deliberately, not squeezed in.

---

## 1. `/api/reorder-custom-images` is unauthenticated, unlimited, and unlogged

### Finding

[routes/customs.py:597-613](routes/customs.py#L597-L613):

```python
@customs_bp.route("/api/reorder-custom-images", methods=["POST"])
def reorder_custom_images():
    try:
        req_data = request.json
        char_name = req_data.get("character_name")
        new_order = req_data.get("new_order")
        if not char_name or not new_order:
            return jsonify({"error": "Missing required fields"}), 400

        if not db.reorder_custom_images(char_name, new_order):
            return jsonify({"error": "Character not found"}), 404
        db.update_last_modified(char_name)
        return jsonify({"message": "Order updated successfully"})

    except Exception as e:
        log.exception("customs.reorder_failed")
        return jsonify({"error": str(e)}), 500
```

No identity check, no ownership check, no `@rate_limited`, no audit record. Contrast the endpoint
directly below it, `delete_custom_image`, which carries `@rate_limited("remove")` and returns 403
with *"You can only remove images you added. Hide it instead."*

Reproduce:

```bash
sed -n '597,613p' routes/customs.py
grep -n "rate_limited" routes/customs.py   # note the absence around line 597
```

### Why it matters

`docs/DECISIONS.md` §1 is the longest section in the project's documentation and exists to answer one
question: how do you stop people destroying other people's work? It names **"well-meaning
replacement"** as the *more common and more important* failure mode — users who clear a page "to make
room for their own" because they want their preferred images to be the ones on the page.

Position is prominence. Pushing forty images to the bottom achieves substantially what removing them
achieves, with none of the friction, none of the attribution, and no Removed drawer to restore from.

It is in one respect worse than deletion. §1 promises *"Nothing is ever destroyed. Removals are soft;
a Removed drawer restores in one click."* Reordering has no equivalent: `db.reorder_custom_images`
overwrites `position` in place, there is no history table, and the previous arrangement is gone.

### The fix

Two tiers. **(a) is the security fix and should be done on its own if time is short.**

**(a) Rate limit and stop the error leak.**

In [ratelimit.py:49](ratelimit.py#L49), add an entry to `RATE_LIMITS` beside `remove` and `restore`,
following the existing commented style:

```python
    # Reordering is not destructive, but it redistributes prominence, which
    # DECISIONS.md section 1 treats as the same problem as removal. Generous
    # enough for honest drag-and-drop, tight enough that a script cannot churn a
    # gallery.
    "reorder": _limits_from_env("reorder", [(60, 60), (400, 3600)]),
```

Then in [routes/customs.py:597](routes/customs.py#L597):

```python
@customs_bp.route("/api/reorder-custom-images", methods=["POST"])
@rate_limited("reorder")
def reorder_custom_images():
    ...
    except Exception:
        log.exception("customs.reorder_failed")
        return jsonify({"error": "Could not save the new order."}), 500
```

Note `except Exception:` without binding `e` — see section 4 for why.

While here, remove the redundant write. `db.reorder_custom_images` already runs
`UPDATE characters SET updated_at = ? WHERE id = ?` inside its own transaction (confirm with
`sed -n "$(grep -n 'def reorder_custom_images' db.py | cut -d: -f1),+30p" db.py`), so the route's
subsequent `db.update_last_modified(char_name)` is a second write for the same effect. Delete the
call from the route, not the one inside the transaction — the transactional one is correct.

**(b) Make a reorder auditable and reversible.**

This is the part that honours "nothing is ever destroyed". Add a migration `022_reorder_history.sql`
recording the *previous* order before each change:

```sql
-- A reorder redistributes prominence, which DECISIONS.md section 1 treats as
-- the same problem as removal -- but unlike a removal it was unrecoverable.
-- This stores the order that was replaced, so a bulk reshuffle can be undone
-- and, more importantly, can be seen.
CREATE TABLE reorder_history (
    id           INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
    identity_id  TEXT REFERENCES identities (id) ON DELETE SET NULL,
    previous     TEXT NOT NULL,   -- JSON array of image ids, in the replaced order
    at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_reorder_history_char ON reorder_history (character_id, at DESC);
```

Record ids rather than URLs: `custom_images.url` is mutable in principle and ids are not, and the
existing `reorder_custom_images` already works from rows it has in hand.

Store `identity.current_identity().id` as `identity_id`, calling `db.ensure_identity` first — see the
module docstring in [identity.py:16-19](identity.py#L16-L19): the row is created lazily on first
write, so anything storing an `identity_id` must ensure it exists.

**Do not** build a moderation UI for this table in this section. Writing the history is the fix;
reading it is section 1's natural successor and belongs in `docs/MODERATION.md`.

### Files to change

- `ratelimit.py` — one `RATE_LIMITS` entry.
- `routes/customs.py` — decorator, error return, drop the redundant `update_last_modified`.
- `migrations/022_reorder_history.sql` — new (tier b only).
- `db.py` — record the previous order inside `reorder_custom_images`'s existing transaction (tier b).
- `tests/test_customs.py` or a new `tests/test_reorder.py`.

### Verification

```bash
uv run pytest tests/ -q
uv run ruff check .
```

Add tests asserting: the endpoint 429s past the limit; a malformed body still 400s; a server error
returns the fixed sentence and **not** the exception text; and (tier b) a reorder writes exactly one
`reorder_history` row whose `previous` is the order that was replaced, not the new one.

Manually confirm drag-and-drop reorder still works on a character page — `useGalleryReorder.js` is
the client side, including long-press on touch.

### Out of scope

- Any ownership rule on reordering. Making it owner-only would break the shared-gallery model; that
  is a product decision for `DECISIONS.md`, not a bug fix.
- A moderation UI reading `reorder_history`.
- The other 25 `str(e)` sites — that is section 4.

---

## 2. Nothing is code-split: 442 KB of JavaScript to every anonymous visitor

### Finding

[frontend/src/App.jsx](frontend/src/App.jsx) has 23 static imports and zero `React.lazy`.
[frontend/vite.config.js](frontend/vite.config.js) configures output filenames but no `manualChunks`.
The result is one chunk:

```
441984  frontend/dist/assets/index-B_8404Z4.js
 84159  frontend/dist/assets/index-OVRUMrEg.css
```

Reproduce:

```bash
grep -c "^import" frontend/src/App.jsx        # 23
grep -c "lazy(" frontend/src/App.jsx          # 0
ls -la frontend/dist/assets/
```

Every anonymous visitor downloads, and never uses: the moderation console
(`ModerationLayout`, `ModerationPage`, `ReportsPage`, `DuplicatesPage`, `UserProfile`, `UserWork`,
`ModerationHistory`, `ContributorFinder`, `ModerationDialog`), the Mudae bulk series-import panel
(`AddMudaePanel`, 519 lines), the accent extractor (`accentFromImage.js`), and the full profile
subtree.

### Why it matters

`PRODUCT.md` describes the product as serving casual use — grab an image, take it to Mudae, leave.
`docs/DECISIONS.md` rejected mandatory accounts specifically to protect that convenience. The landing
page's job, per the `/api/stats` docstring, is to show a handful of numbers; a previous optimisation
already cut a 475 KB payload down for exactly this reason. Shipping the staff tooling to everyone
undoes a chunk of that work at a different layer.

The moderation subtree alone is nine components behind a role check that almost nobody passes.

### The fix

Convert the route-level imports to `React.lazy` and wrap `<Routes>` in a single `<Suspense>`.

Keep eager: `HomePage` (the landing page — lazy-loading it adds a round trip to the most common
entry), `Navbar`, `Toast`, `RestrictionBanner`, `AppErrorBoundary`, and the `ui` primitives.

Make lazy: `CharacterPage`, `AddPage`, `CustomsPage`, `SearchResultsPage`, `NotificationsPage`, the
whole `profile/` subtree, and the whole `moderation/` subtree.

```jsx
import { lazy, Suspense } from 'react'

const CharacterPage = lazy(() => import('./pages/CharacterPage'))
const ModerationLayout = lazy(() => import('./pages/moderation/ModerationLayout'))
// ...
```

```jsx
<main id="main-content" className="container" tabIndex={-1}>
  <Suspense fallback={<div className="route-fallback" role="status" aria-live="polite">
    <span className="sr-only">Loading…</span>
  </div>}>
    <Routes>{/* unchanged */}</Routes>
  </Suspense>
</main>
```

The fallback must not shift layout or flash — it renders for a few hundred milliseconds at most on a
warm cache. Keep it visually near-empty with an `sr-only` announcement; do not build a skeleton here,
since the pages already own skeletons (`CharacterLoadingState`, `HomeLoadingState`).

`RequireModerator` stays eager and outside the lazy boundary, so a non-moderator is redirected
without downloading the moderation chunk at all. Verify this specifically — it is the largest single
saving and it is easy to lose by nesting the guard inside a lazy layout.

Consider a `manualChunks` entry splitting `react`, `react-dom`, `react-router-dom` and
`@tanstack/react-query` into a `vendor` chunk so they are cached across deploys, since the app chunk
changes far more often than they do.

### Files to change

- `frontend/src/App.jsx` — imports, `Suspense` wrapper.
- `frontend/vite.config.js` — optional `manualChunks`.
- `frontend/src/styles/pages.css` or `layout.css` — a `.route-fallback` rule if one is needed.
- `frontend/src/pages/pages.smoke.test.jsx` — lazy routes resolve asynchronously, so assertions that
  were synchronous will need `findBy*` instead of `getBy*`.

### Verification

```bash
cd frontend && npm run build && ls -la dist/assets/
```

Pass looks like: several chunks instead of one, and `index-*.js` substantially smaller than 441,984
bytes. Record the new figures in the commit message.

```bash
cd frontend && npm test && npx biome check src
```

Then in a browser with the network panel open: load `/` and confirm the moderation chunk is **not**
requested; navigate to `/profile/moderation` as a moderator and confirm it is fetched then. Check
that no route flashes a layout shift on navigation.

### Out of scope

- Splitting or optimising the 84 KB CSS bundle.
- Route-level prefetching on link hover.
- Any change to what the pages themselves render.

---

## 3. `CharacterPage.jsx` is a 1,113-line function with 26 `useState` calls

### Finding

[frontend/src/pages/CharacterPage.jsx](frontend/src/pages/CharacterPage.jsx) is a single
`export default function` of 1,113 lines, holding 26 `useState` calls and 5 `useEffect` calls with no
internal decomposition.

Reproduce:

```bash
wc -l frontend/src/pages/CharacterPage.jsx        # 1113
grep -c "useState(" frontend/src/pages/CharacterPage.jsx   # 26
grep -n "^function \|^export default function" frontend/src/pages/CharacterPage.jsx  # one match
```

It is more than twice the size of the next-largest frontend file (`HomePage.jsx`, 572 lines) and
holds at least six unrelated concerns: the character record and its loading state, an inline edit
form, a five-mode toolbar state machine, image selection, the accent picker, the lightbox, drag
reorder, the removed drawer, the `$ai` command dialog, and drag-and-drop upload.

The clearest evidence that this already costs something: it required **three separate test files** —
`CharacterPage.test.jsx`, `CharacterPage.moderation.test.jsx`, `CharacterPage.reorder.test.jsx` —
because no single file could set the component up coherently for all of its behaviours.

### Why it matters

This is where every new character-page feature lands, and each one makes the next harder. It is also
the one place in the frontend that contradicts the codebase's own demonstrated standard: the profile
section is a clean decomposition of five near-identical pages into `ListTab` (the three list states),
`ListControls` (the filter row), `CardGrid` (the two grid arrangements) and `useFilteredList` (query,
sort, order). That refactor works and should be the model here.

### The fix

**This is a behaviour-preserving refactor. It must change no rendered output and no user-visible
behaviour.** The three existing test files are the safety net — run them continuously, and do not
edit them to accommodate the refactor except where an import path must change.

Work in small, separately committed steps, in roughly this order (each is independently revertible):

1. **Extract the edit form.** `editMode`, `editName`, `editSeries`, `editRank`, `editTraits` and
   their submit handler move into a `useCharacterEdit` hook, or into `CharacterHeader` which already
   renders the form. Five `useState` calls leave the page.
2. **Extract the toolbar-mode machine.** `mode`, `selectedUrls`, `confirmRemove`,
   `confirmDiscardOrder` are one state machine with five modes; a `useReducer` in
   `useGallerySelection` replaces four `useState` calls and makes the illegal combinations
   unrepresentable.
3. **Extract the lightbox.** `modalOpen`, `modalIndex`, `ratios` into `useLightbox`.
4. **Extract the accent controls.** `accentPick`, `accentBusy` into `AccentOverrideControl`, which
   already exists and already owns the UI.
5. **Extract upload drag-and-drop.** `dragOver`, and the `loading` flag it shares, alongside the
   existing `useCustomImageUpload`.

Stop when the page is under roughly 400 lines and reads as composition rather than implementation.
Do not chase a line target beyond that.

Two things to preserve carefully, because they are easy to break and hard to notice:

- **`charVersion`** is a refetch trigger, not data. Keep its semantics exactly.
- **Long-press drag reorder on touch** (`useGalleryReorder.js`) is genuinely intricate and has its
  own test file. Prefer leaving it entirely alone.

### Files to change

- `frontend/src/pages/CharacterPage.jsx` — the subject.
- New hooks under `frontend/src/hooks/` — `useCharacterEdit.js`, `useGallerySelection.js`,
  `useLightbox.js`.
- `frontend/src/components/CharacterHeader.jsx`, `AccentOverrideControl.jsx` — absorb what belongs
  to them.

### Verification

```bash
cd frontend && npm test -- CharacterPage && npm run build && npx biome check src
```

All three `CharacterPage.*.test.jsx` files must pass **unmodified**, apart from import paths.

Then a manual regression pass on the real flows, since these are the parts with existing craft:
upload with progress, all five toolbar modes, drag-and-drop reorder including long-press on touch,
the `$ai` command dialog and its Discord message-limit split, the lightbox's focus trap, arrow keys
and swipe, the removed drawer, and the accent override.

### Out of scope

- **Section 8 (splitting `db.py` / `pages.css`). Do not attempt both — the diffs will be
  unreviewable.**
- Section 7's data-fetching migration, even though `CharacterPage` is one of the files that mixes
  patterns. Structure first, fetching later.
- Any visual or behavioural change. If the refactor reveals a bug, record it; do not fix it in the
  same commit.

---

## 4. Twenty-six endpoints return raw exception text to the browser

### Finding

```bash
grep -n '"error": str(e)' routes/*.py *.py | wc -l   # 26
```

Spread across [routes/customs.py](routes/customs.py) (11), [routes/mudae.py](routes/mudae.py) (7),
[routes/characters.py](routes/characters.py) (6), [routes/media.py:126](routes/media.py#L126) and
[mudae_discord.py:1224](mudae_discord.py#L1224). The pattern:

```python
    except Exception as e:
        log.exception("customs.reorder_failed")
        return jsonify({"error": str(e)}), 500
```

Two go further and ship the exception class name as user-facing copy —
[routes/customs.py:436](routes/customs.py#L436) and
[routes/customs.py:553](routes/customs.py#L553):

```python
        return jsonify({"error": str(e), "details": [f"Server error: {type(e).__name__}"]}), 500
```

### Why it matters

`str(e)` on an uncaught exception is whatever that exception happened to contain: a SQLite error
naming columns and tables, a `requests` error carrying an internal URL, a filesystem path, or an
ImgChest API response body. None of it is intended for a browser.

It is also a UX defect, not only a disclosure one. `UploadErrorDialog.jsx` exists to render these
strings **selectably and copyably**, so a stray `KeyError: 'thumb_key'` is presented to a user with
the same weight as a considered message like *"You can only remove images you added."*

The logging is already right — `log.exception("customs.reorder_failed")` captures the diagnostic
server-side with a stable event name. Nothing is lost by withholding the text from the client.

### The fix

Replace each site with a fixed, human sentence describing what failed in the caller's terms, and drop
the `as e` binding where nothing else uses it:

```python
    except Exception:
        log.exception("customs.reorder_failed")
        return jsonify({"error": "Could not save the new order."}), 500
```

Write the message per endpoint rather than using one shared string — *"Could not save the new
order."* and *"Could not upload that image."* are useful; *"Internal server error"* is not. Match the
voice of the messages already in the codebase (`"You can only remove images you added. Hide it
instead."`): plain, specific, no apology, and where possible naming what the user can do next.

Three cases need individual judgement rather than mechanical replacement:

- **Deliberate 400s.** [routes/mudae.py:252](routes/mudae.py#L252) and
  [routes/mudae.py:472](routes/mudae.py#L472) return `str(e)` with a 400, which suggests the
  exception is a validation error whose message *is* intended for the user. Check what is raised. If
  it is a `ValueError` the code raised itself, keep the text — but raise a dedicated exception type
  and catch that narrowly, so an unexpected error cannot take the same path.
- **503s from Mudae** ([routes/characters.py:117](routes/characters.py#L117),
  [routes/mudae.py:248](routes/mudae.py#L248) and others) may carry a useful "the bot is not
  configured" message. Same treatment: narrow the except, or replace with a fixed sentence.
- **[mudae_discord.py:1224](mudae_discord.py#L1224)** is a status payload, not an error response.
  It may legitimately carry diagnostic text — check whether that field reaches the browser
  (`/api/mudae/status`) before changing it.

### Files to change

- `routes/customs.py`, `routes/mudae.py`, `routes/characters.py`, `routes/media.py`
- `mudae_discord.py` — only after confirming the status payload's audience.
- Any test asserting on an error body.

### Verification

```bash
grep -rn '"error": str(e)' routes/ *.py    # expect only deliberate, narrowly-caught survivors
uv run pytest tests/ -q
uv run ruff check .
```

Add at least one test that forces a 500 (monkeypatch a `db` function to raise with a distinctive
message like `"SECRET-INTERNAL-DETAIL"`) and asserts that string does **not** appear in the response
body.

### Out of scope

- Adding the rate limit to the reorder endpoint (section 1), even though its `str(e)` is on the same
  line you will be editing. Fix the error return; leave the decorator to section 1 — or note in your
  commit that you did both.
- Restructuring error handling generally (a Flask `errorhandler`, a custom exception hierarchy).
  Worth doing eventually; not this change.

---

## 5. No index on `custom_images.added_by` or `removed_by`

### Finding

`custom_images` carries exactly two indexes, from
[migrations/001_initial.sql:62-63](migrations/001_initial.sql#L62-L63):

```sql
CREATE INDEX idx_custom_images_char ON custom_images (character_id, state, position);
CREATE INDEX idx_custom_images_hash ON custom_images (content_hash) WHERE content_hash IS NOT NULL;
```

Neither covers `added_by` or `removed_by`, and ten queries filter on them:

```bash
grep -c "added_by = ?\|removed_by = ?" db.py    # 10
grep -rn "added_by\|removed_by" migrations/*.sql | grep -i index   # no matches
```

Affected functions include `list_contributors`, `list_images_by_identity`,
`get_removed_by_identity`, and `count_images_added_by` — that is, essentially the whole moderation
section plus the profile Removed tab. `list_images_by_identity` issues three such queries per call
(a `COUNT(*)`, the page itself, and a totals aggregate), so one page view is three full scans of
every row in the table.

### Why it matters

It is survivable at today's size — roughly 8,560 images — which is exactly why it will go unnoticed
until it is not survivable. SQLite is fast at scanning small tables and unforgiving once they grow.
The cost is one migration.

### The fix

Add `migrations/022_moderation_indexes.sql` (renumber if 022 is taken — check `ls migrations/`):

```sql
-- The moderation section and the profile Removed tab filter custom_images by
-- actor, but the only indexes on the table are by character and by content
-- hash, so every one of those queries was a full scan. list_images_by_identity
-- alone runs three per page view.
--
-- Partial indexes: added_by and removed_by are both nullable and mostly NULL
-- (the v1-migrated library predates ownership tracking), so indexing only the
-- rows that have a value keeps them small.
CREATE INDEX idx_custom_images_added_by
    ON custom_images (added_by, added_at DESC)
    WHERE added_by IS NOT NULL;

CREATE INDEX idx_custom_images_removed_by
    ON custom_images (removed_by, removed_at DESC)
    WHERE removed_by IS NOT NULL;
```

The trailing timestamp column matches the `ORDER BY` in `list_images_by_identity`
(`i.added_at DESC, i.id DESC` and `COALESCE(i.removed_at, i.added_at) DESC, i.id DESC`), so the index
can serve the sort as well as the filter. Confirm the ordering columns still match before writing the
migration — read the function first.

Migrations are applied at connect time by `db._apply_migrations`; nothing else needs wiring.

### Verification

Before and after, against a copy of the real database:

```bash
sqlite3 "$DATABASE_PATH" "EXPLAIN QUERY PLAN
  SELECT * FROM custom_images i JOIN characters c ON c.id = i.character_id
   WHERE i.added_by = 'someid' AND i.state = 'active'
   ORDER BY i.added_at DESC, i.id DESC LIMIT 24;"
```

Pass: the plan changes from `SCAN custom_images` to `SEARCH custom_images USING INDEX
idx_custom_images_added_by`. Record both plans in the commit message.

```bash
uv run pytest tests/ -q
```

### Out of scope

- Any other index. `user_hidden`, `saved` and `image_reports` have composite primary keys that cover
  their common lookups; do not add speculative indexes.
- Rewriting the queries themselves.
- The three-queries-per-call structure of `list_images_by_identity`. Indexing it is the cheap fix;
  restructuring is a separate judgement.

---

## 6. `/api/stats` is uncached and runs six-plus heavy queries per landing-page load

### Finding

`/api/stats` is defined in [upload_imgchest.py](upload_imgchest.py) (find it with
`grep -n "api/stats" upload_imgchest.py`). It sets no `Cache-Control`, has no memoisation and no TTL.
It runs on every load of `/`, which is the most-requested page on the site.

`db.get_home_highlights` issues six-plus queries, including:

- `top_series` — a three-CTE query with a `ROW_NUMBER() OVER (PARTITION BY series ...)` window.
- `best_covered` — `GROUP BY` across every active image.
- `recent` — another `ROW_NUMBER()` partition over `custom_images`.
- `contributors` — a join and `GROUP BY` over `identities`.
- `series_count` — `COUNT(DISTINCT series)` over the full `characters` table.
- `get_most_viewed` — a further query.

Reproduce:

```bash
grep -n "Cache-Control\|lru_cache\|_cache" upload_imgchest.py    # nothing on this route
sed -n "$(grep -n 'def get_home_highlights' db.py | cut -d: -f1),+200p" db.py | grep -c "conn.execute"
```

### Why it matters

This is the heaviest endpoint in the application and the most frequently hit, against SQLite, served
by `workers × threads` concurrency (see [gunicorn.conf.py](gunicorn.conf.py)). The data it returns —
best-covered characters, top series, the contributor board — changes a handful of times a day.

### The fix

A short in-process TTL cache, plus a matching response header.

**Use a TTL rather than explicit invalidation.** The underlying numbers change on every upload,
removal, restore and character view, so precise invalidation would mean touching a dozen write paths
and would break silently the first time someone adds a thirteenth. A TTL is wrong for at most its own
duration, in a way nobody can perceive on a page of approximate highlights, and it cannot rot.

Sixty seconds is a reasonable default; make it configurable by environment variable in the style
`ratelimit._limits_from_env` already uses, so it can be set to `0` in development and in tests.

```python
_STATS_TTL = float(os.environ.get("STATS_CACHE_TTL", "60"))
_stats_cache: tuple[float, dict] | None = None
_stats_lock = threading.Lock()
```

Three things the implementation must get right:

- **Thread safety.** The worker class is `gthread` with 8 threads, so the cache is shared. Guard it
  with a lock. Recomputing twice under a race is harmless; a torn read is not.
- **Do not cache the per-caller part.** The response includes `you` — the caller's own contributor
  standing, which is looked up per identity. Cache only the shared highlights and totals, and attach
  `you` after. Getting this wrong shows one visitor another visitor's standing, which is a privacy
  bug considerably worse than the performance problem being solved.
- **Do not cache failures.** The route deliberately guards the totals and highlights separately so
  that a failed highlights query still renders the numbers. Only store a successful result.

Then set a header consistent with the TTL:

```python
response.headers["Cache-Control"] = "public, max-age=60"
```

`public` is correct only for the shared part. If `you` is in the same response, it must be
`private, max-age=60` — a shared cache must never serve one visitor's standing to another. Prefer
`private`, or split `you` into its own endpoint and leave that uncached.

### Files to change

- `upload_imgchest.py` — the route and the cache.
- `tests/` — a test that a second call within the TTL does not re-query, and that `you` still differs
  per identity across cached calls.

### Verification

```bash
uv run pytest tests/ -q
```

The per-identity test is the important one: two requests with different identity cookies inside the
TTL window must return the same highlights but different `you`.

Time it against real data:

```bash
time curl -s localhost:5000/api/stats > /dev/null    # cold
time curl -s localhost:5000/api/stats > /dev/null    # warm — expect a clear drop
```

### Out of scope

- Caching any other endpoint.
- Optimising the queries inside `get_home_highlights` — caching makes that unnecessary for now.
- Moving `/api/stats` out of `upload_imgchest.py` into a blueprint. Reasonable, unrelated.

---

## 7. Three coexisting data-fetching patterns

### Finding

The frontend fetches server data three different ways:

1. **react-query**, via `src/queries/*.js` — 13 files.
2. **Raw `useEffect` + `apiClient` + a `cancelled` flag** — `profile/HiddenTab.jsx`,
   `profile/RemovedTab.jsx`, `components/AddMudaePanel.jsx`.
3. **`CustomsPage.jsx`'s bespoke `reloadKey` counter** — a fourth state variable whose only job is to
   re-trigger the effect on retry.

`AddPage.jsx` and `CharacterPage.jsx` use patterns 1 and 2 **simultaneously**.

Reproduce:

```bash
grep -rln "useQuery\|useMutation" frontend/src/pages frontend/src/components | sort
for f in $(grep -rl "apiClient" frontend/src/pages frontend/src/components); do
  grep -q "useEffect" $f && grep -q "apiClient\." $f && echo $f
done
```

### Why it matters

The docblocks in `src/queries/` describe react-query as the direction of travel, and the migration
stalled partway — leaving the most complex files carrying both. The practical cost is that caching,
retry, and refetch-on-invalidate behave differently depending on which page you are on, and the
`queryClient.invalidateQueries()` in `useSignOut` (which exists precisely because "the identity
changed, so every server answer is now about someone else") silently does not reach the data fetched
by pattern 2.

That last point is a real bug, not only an inconsistency: sign out on a page whose data came from a
raw `useEffect` and the previous identity's data stays on screen.

### The fix

Migrate patterns 2 and 3 onto react-query, easiest first.

**Start with `HiddenTab` and `RemovedTab`.** They are semantically identical to `SavedTab`, which is
already migrated — so `SavedTab.jsx` plus `src/queries/saved.js` is a working template for exactly
this shape. Add `src/queries/hidden.js` and `src/queries/removed.js` following the house pattern: a
`xxxKey` array constant, a `useXxx()` query hook, and mutation hooks that
`queryClient.invalidateQueries({ queryKey: xxxKey })` on success.

**Then `CustomsPage`.** Its `reloadKey` disappears entirely — `useQuery`'s `refetch()` replaces it,
and the retry `EmptyState` action calls that instead. Its debounce should move to the shared
`useDebouncedValue` hook, which exists for this and is already used by `useCatalogSearch`.

**Then `AddMudaePanel`**, and the raw fetches inside `AddPage` and `CharacterPage`.

Two behaviours to preserve:

- `queryClient` defaults in `src/queries/queryClient.js` are `retry: retryPolicy` (transient errors
  only, ≤3 attempts), `staleTime: 30_000`, `refetchOnWindowFocus: false`. Migrated calls inherit
  these, which is a behaviour change from pattern 2's no-retry. That is an improvement, but note it.
- The three list states (loading / filtered-to-nothing / genuinely empty) must stay distinguishable.
  `items === null` is the current "not loaded yet" signal in `ListTab`; react-query's `isPending` is
  the replacement. Do not collapse the states.

### Files to change

- New: `frontend/src/queries/hidden.js`, `frontend/src/queries/removed.js`.
- `frontend/src/pages/profile/HiddenTab.jsx`, `RemovedTab.jsx`
- `frontend/src/pages/CustomsPage.jsx`
- `frontend/src/components/AddMudaePanel.jsx`
- `frontend/src/pages/AddPage.jsx`, `CharacterPage.jsx` — last, and only the fetch calls.

### Verification

```bash
cd frontend && npm test && npm run build && npx biome check src
```

`CustomsPage.test.jsx` is the strictest existing guard — it asserts that search, sort and paging
reach the *server* rather than being filtered in the browser, and it must keep passing untouched.

Add a test for the bug this fixes: render a migrated tab with seeded data, trigger `useSignOut`, and
assert the list refetches rather than showing the previous identity's rows.

### Out of scope

- Section 3's decomposition of `CharacterPage`. If both are wanted, do section 3 first.
- Changing the `queryClient` defaults.
- Migrating anything that is not a data fetch.

---

## 8. `db.py` and `pages.css` have become dumping grounds

### Finding

```bash
wc -l db.py                          # 3570
wc -l frontend/src/styles/pages.css  # 3557
```

For contrast, the next-largest backend module is `mudae_discord.py` at 1,248 lines and every other
one is under 1,000; the next-largest stylesheet is `components.css` at 1,089.

`db.py` holds characters, custom images, identity, moderation, notifications, rate limiting, the
Mudae catalog, bookmarks, view history and the home-page statistics.

### Why it matters

It is the file every backend feature has to touch, which makes it the most common source of merge
conflicts and the hardest file to hold in mind. That said — **this is the lowest-priority item here,
and it is legitimate to decide not to do it.** Large mechanical file splits produce enormous diffs,
carry real risk of a lost function or a circular import, and deliver no behaviour change. The
function-level organisation inside `db.py` is good; only its size is bad.

### The fix

If it is done, split `db.py` along the seams `routes/` already uses, since that boundary is proven:

```
db/__init__.py      # re-exports everything, so `import db` keeps working
db/connection.py    # _connect, get_connection, transaction, migrations, pragmas
db/characters.py
db/images.py
db/identity.py
db/moderation.py
db/notifications.py
db/catalog.py
db/stats.py
```

**The `__init__.py` re-export is what makes this safe.** Every call site says `db.something(...)`;
keeping that surface intact means the split is internal and reviewable module by module, rather than
a repo-wide rename. Do one module per commit, `db/connection.py` first, and run the full test suite
between each.

Watch for circular imports — `stats.py` will want things from `images.py` and `characters.py`. Keep
the shared helpers (`_now`, `_character_id`, `thumbnails` usage) in one place, imported downward
only.

For `pages.css`, split per page into `styles/pages/` (`home.css`, `character.css`, `customs.css`,
`profile.css`, `moderation.css`, `add.css`), preserving the documented import order in `index.css`.
**Keep each page's responsive rules in that page's own file** — `DESIGN.md` names a separated
media-query pile as a bug that already shipped once, and this split is the opportunity to guarantee
it cannot recur.

### Verification

```bash
uv run pytest tests/ -q && uv run ruff check .
cd frontend && npm run build && npm test
```

For the CSS split, the strongest check is that the built stylesheet is unchanged in content:

```bash
# before and after; the hash in the filename will differ, the sorted content should not
cd frontend && npm run build && cat dist/assets/index-*.css | sort | md5sum
```

`frontend/src/styles/tokenPairs.test.js` must pass without modification — it reads the stylesheets
from disk, so it will need its glob updated to cover `styles/pages/*.css`, and that glob update is
the only edit it should need.

### Out of scope

- **Section 3. Do not do both.** Two large refactors in one branch produce an unreviewable diff.
- Any behaviour change, any query rewrite, any rule change. Moving code only.
- Splitting `components.css` or `ui.css` — they are within normal size.

---

## 9. Ten of eleven `ui/` primitives are untested

### Finding

```bash
find frontend/src/components/ui -name '*.test.*'    # only Modal.test.jsx
```

`Button`, `Card`, `Badge`, `Input`, `Select`, `Field`, `SegmentedControl`, `ConfirmDialog`,
`EmptyState` and `IconButton` have no tests, despite `DESIGN.md` naming them as the components to
reach for before writing anything new, and despite the project otherwise being well tested (33 Python
test files, 47 frontend).

### Why it matters

These are the most-reused components in the codebase, so a regression in one is a regression
everywhere at once. Several have non-trivial behaviour worth pinning:

- **`Button`** — `loading` sets `aria-busy` and renders a spinner; `iconOnly` and `round` change
  classes; pressed state is `aria-pressed`. A `loading` button that stays clickable is a
  double-submit bug.
- **`Field`** — `children` may be a render function receiving `{ id, describedBy }`, and it wires
  `useId()` to the label and hint. Broken `aria-describedby` is invisible until a screen reader
  hits it.
- **`SegmentedControl`** — real radios in a `<fieldset>` with an `sr-only` legend, where `short`
  changes only the drawn text while the full label stays in the accessible name. That distinction is
  precisely the sort of thing a well-meaning refactor flattens.
- **`ConfirmDialog`** — the codebase contains no `window.confirm` anywhere; this is the only
  confirmation path, and it sits in front of destructive actions.

### The fix

One test file per primitive, beside the component, following house style: a docblock stating the rule
being protected, then role-based queries (`getByRole('button', { name: ... })`), not class names or
test ids.

Order by value: `Button`, `Field`, `SegmentedControl`, `ConfirmDialog` first; `Card`, `Badge`,
`EmptyState` are nearly presentational and can be brief.

Do not test implementation details — that class names match, or that a particular element nests a
particular way. Test the contract: what a user sees, what a screen reader is told, and what happens
on interaction.

`Modal.test.jsx` is the model to follow, including the existing convention that every dialog renders
a visible close button beside its title.

### Files to change

New test files only, under `frontend/src/components/ui/`.

### Verification

```bash
cd frontend && npm test && npm run coverage
```

Coverage of `src/components/ui/` should rise substantially. No source file should need editing — if a
primitive cannot be tested without changing it, that is a finding worth reporting rather than a
licence to change the component.

### Out of scope

- Changing any primitive. Tests describe what exists; if a test reveals a bug, record it separately.
- Visual regression or snapshot testing.
- Tests for `useDialog.js` — it is covered indirectly through `Modal`.

---

## Verified clean

Three suspicions were investigated during this review and **disproved**. They are recorded so nobody
spends time re-checking them.

**The four-breakpoint rule holds.** `DESIGN.md` documents exactly four breakpoints and
`tokenPairs.test.js` enforces them. An initial grep appeared to show a dozen values, but that grep
was matching `min-width` inside `minmax()` and other CSS properties. The real set:

```bash
grep -ho "@media[^{]*" frontend/src/styles/*.css | grep -o "[0-9]*px" | sort -n | uniq -c
#  3 480px   20 768px   1 769px   7 960px   4 1200px
```

`769px` is the documented min-width complement of `768px`. The CSS complies.

**SSRF defence is sound.** [remote_images.py:176-331](remote_images.py#L176-L331) implements a host
allowlist, rejection of loopback / private / link-local resolved addresses, per-hop redirect
validation (rather than letting `requests` follow the chain and inspecting only the final URL), a
redirect cap, and a size cap. The user-facing image proxy and the portrait fetcher have deliberately
separate allowlists. This was probed for a hole and none was found.

**The inert NSFW toggle is honestly labelled.** `identities.show_nsfw` is stored and rendered as a
switch but nothing reads it, because no image carries a rating. This is not a lying control: both
[migrations/006_nsfw_preference.sql](migrations/006_nsfw_preference.sql) and the switch's own hint
text say so outright — *"Nothing is marked yet, so this changes nothing today. It is recorded now so
your choice already applies on the day the filter arrives."* Whether to ship an inert control at all
is a product question, not a defect.

---

## Calibration

Worth stating plainly, since the above is a list of faults: this codebase is in better shape than
most. The SQLite and gunicorn configuration is correctly reasoned and documented (WAL,
`busy_timeout`, `foreign_keys=ON` per connection, thread-local connections, `gthread` with a written
explanation of why sync workers were wrong). The design system's rules are enforced by tests rather
than merely asserted, and the CSS actually complies. The soft-delete and audit design is thorough.
The documentation records rejected options with reasons, which is rare and is the only reason this
review could be specific.

The pattern across all nine findings is the same: **the thinking is consistently better than the
follow-through.** The reorder endpoint, the missing indexes, the stalled react-query migration and
the unsplit bundle are each cases where the right approach was established elsewhere in this same
codebase and simply not applied in one place.
