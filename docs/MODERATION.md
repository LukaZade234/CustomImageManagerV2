# Moderation

The plan for the moderation surface, phase by phase. Phase 1 — the UI and the reads behind it — is
specified here in full; later phases are sketched only far enough to say what they are and why they
are not phase 1.

Read `DECISIONS.md` §1 and §5 first. They argue against routine human moderation, and this document
has to answer to that argument rather than quietly ignore it.

---

## Why this exists

Moderator and owner roles have existed since Phase 6, and they are real: the role is a checked column
on `identities`, `Identity.is_moderator` / `is_owner` are consulted in six places, and a moderator
already bypasses the ownership check when removing an image. What does not exist is any screen for
them.

So the escape hatch is there, and it has no handle. To answer *"what has this person been doing?"* —
the one question worth asking when something looks wrong — the operator has to guess which character
page holds the evidence and read its Removed drawer, or open SQLite. There is no view of a
contributor's work as a contributor.

### This is not the queue that DECISIONS argues against

`DECISIONS.md` §1 lists "routine human moderation" as a non-goal, in these terms: *"If the design
requires the operator to check the site regularly, it has failed."* §5 calls roles *"a fallback, not
the design."* Both still hold, and phase 1 is built so that they keep holding.

The distinction is between **inspection** and a **queue**. A queue pushes: it accumulates pending
items, it counts them, it puts a badge in the chrome, and it is only discharged by someone showing
up regularly to work it. This page pulls: it holds nothing, counts nothing pending, and asks for
nothing. It is opened deliberately, when the operator already has a reason, and it answers a question
rather than assigning work.

Three consequences are load-bearing and should survive later phases:

- **No pending count anywhere**, and nothing in the navbar that changes appearance based on site
  state. The link is present for staff and inert.
- **The acting verbs stay on the character page.** Removal and restore already live where the image
  and its context are. Duplicating them onto a list view is what turns a list into a worklist.
- **`image_reports` stays unread** in phase 1. Surfacing reports *is* the queue — that is precisely
  the mechanism §1 designed to work without a human, auto-removing at two distinct reporters. A
  review screen for it is a real decision with real arguments on both sides, and it deserves its own
  entry rather than arriving as a side effect of building a user list.

If a later phase finds itself adding a pending count, that is the signal to re-read §1 and fix the
thing generating the backlog instead.

---

## Phase 1 — the review surface

`/moderation`, staff-only. Search contributors, pick one, read what they added and what they removed,
filtered by character. Read-only: the UI plus the `GET` endpoints that feed it, no new mutations.

### Decisions taken

| Question | Decision |
|---|---|
| Backend scope | The UI **and** the read-only endpoints. Removal, restore and promote/demote are later. |
| Who is listed | Every identity with at least one added or removed image — pseudonyms included, `hide_from_leaderboard` and `hide_attribution` ignored. Idle cookie-only identities are excluded. |
| Shape | Master–detail on one route, selection carried in the URL (`?user=…&state=…&char=…`). |
| Gating | Non-moderators are redirected home, indistinguishable from the existing `*` catch-all. The backend enforces separately and does not trust the client. |

#### On ignoring the privacy flags

This is the decision most likely to be questioned later, so the reasoning is recorded rather than
assumed.

`get_stats` is deliberate about the contributor board: it counts *only* people who signed in with
Discord and have not set `hide_from_leaderboard`, because — in the comment's words — that *"keeps
anonymity genuinely anonymous rather than merely unlabelled, and it means the list can never expose
someone who did not choose to be named."*

That promise is about **public** surfaces, and it stays intact. A staff-only view is a different
audience with a different purpose, and the alternative is self-defeating: a moderation tool that
respects `hide_from_leaderboard` is blind to exactly the anonymous, unattributed contributor it
exists to investigate. Anonymity here means *the public does not learn who you are*, not *the
operator of the site cannot see what was added to it*.

What it is **not** licence to do: pseudonymous handles are derived, not chosen, and they must not
leak back onto a public surface from here.

#### Named out of scope

- **Acting from this page.** `db.set_role` is written and has no caller anywhere but a test; the
  promote/demote route is phase 2, and owner-only.
- **Reading `image_reports`** — see above.
- **The ~8,547 unattributed images** (`added_by IS NULL`, migrated from v1). They have no actor, so
  they cannot appear under a contributor, and they are not a moderation concern — they are the
  library's history. A synthetic "Unattributed" bucket is a later call if it is ever wanted.

---

### Backend

#### 1. A real `require_moderator` decorator

The only true role gate in the app is written inline, once, in `routes/characters.py` on
`accent-override`. Phase 1 adds a second and third gate, so lift it into a decorator in `identity.py`
— which already owns `current_identity()` and the `Identity` dataclass — beside the existing
`@rate_limited` in `ratelimit.py`:

```python
def require_moderator(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_identity().is_moderator:
            return jsonify({"error": "Not permitted"}), 403
        return fn(*args, **kwargs)
    return wrapper
```

Rewrite the `accent-override` gate to use it, so there is one implementation rather than three.

#### 2. A public reference for an identity, not its id

`/api/me` deliberately omits the identity id, and the id is what the signed `imid` cookie carries.
The URL needs a stable per-user key, so derive one instead of shipping ids to the browser:

```python
def public_ref(identity_id: str) -> str:
    return hashlib.blake2b(identity_id.encode(), digest_size=8, person=b"modref").hexdigest()
```

Resolve a ref back with a `db.identity_by_ref(ref)` helper that scans `identities` and matches. The
scan is bounded by the number of identities, which is small, and the alternative — an indexed column
— costs a migration for a lookup that happens once per page view. If the table ever grows past a few
thousand rows, add the column then.

*Alternative considered:* return the raw `id`. It is not a forgeable credential, since the cookie is
signed with `SECRET_KEY` and the id alone buys nothing. It was rejected anyway: the codebase has a
deliberate rule that the id never reaches the client, and quietly breaking it in one place teaches
the next reader that the rule is decorative.

#### 3. Two queries in `db.py`

Hand-written SQL in the existing style; there is no ORM.

**`list_contributors()`** — one pass over `custom_images` grouped by actor, unioning additions and
removals so that someone who has only ever *removed* something still appears:

```
SELECT i.id, i.handle, i.role, i.discord_id IS NOT NULL AS signed_in,
       SUM(added) AS added, SUM(removed) AS removed, MAX(at) AS last_at
```

over a subselect of `(added_by AS actor, 1, 0, added_at)` `UNION ALL`
`(removed_by AS actor, 0, 1, removed_at)` where the actor is not NULL, joined to `identities`.
Unpaged — the list is bounded by contributors, not visitors.

Note the lazy-row caveat from `identity.py`: an identity row is written on first write, so the join
should tolerate a missing row and fall back to `handle_for(id)` rather than dropping the actor.

**`list_images_by_identity(identity_id, *, state, character=None, page, per_page)`** — the gallery
rows for one actor. `state='active'` filters `added_by = ? AND state = 'active'`; `state='removed'`
filters `removed_by = ? AND state = 'removed'`. Shape the rows exactly as `get_removed_by_identity`
already does — `id`, `url`, `thumb` via `thumbnails.thumb_url`, `width`, `height`, `character`,
timestamps, reason — so the frontend can render them with the card grid that already exists. Returns
`{items, total, total_pages}` like `list_characters_with_customs`.

#### 4. `routes/moderation.py`

A new blueprint, registered in `upload_imgchest.py` beside the other seven.

| Route | Returns |
|---|---|
| `GET /api/moderation/users` | `{items: [{ref, handle, role, signed_in, added, removed, last_at}], total}` |
| `GET /api/moderation/users/<ref>/images?state=&character=&page=&per_page=` | Paged gallery rows for one actor, plus `{added, removed}` totals so the detail header is right before either list loads |

Both `@require_moderator`. Unknown `ref` → 404. `state` whitelisted to `active` / `removed`, anything
else 400 — the same shape of validation `sort` already gets in `routes/customs.py`.

#### 5. `routes/spa.py`

It enumerates client routes explicitly rather than using a catch-all, deliberately, so that an
unknown `/api` path 404s instead of returning HTML. `/moderation` has to be added to that list.

While in the file: **`/profile` and `/search` are already missing**, so a deep link to either 404s
when Flask serves the SPA. It only hides because production serves the frontend from Cloudflare
Pages. Add all three.

---

### Frontend

#### 6. The guard — `src/components/RequireModerator.jsx`

Nothing role-gates today, so this is new. It must not flash: `useMe()` is a fetch, and rendering the
redirect while `me` is still undefined would bounce a legitimate moderator home on every cold load.

```jsx
export default function RequireModerator({ children }) {
  const { data: me, isPending } = useMe()
  if (isPending) return null          // not "denied" — "not known yet"
  if (!me?.is_moderator) return <Navigate to="/" replace />
  return children
}
```

Redirecting rather than showing "not permitted" keeps the route indistinguishable from the `*`
catch-all, so its existence is not advertised to anyone probing. This is a convenience, not a
security boundary — the endpoints enforce the role themselves.

#### 7. Data — `src/queries/moderation.js`

react-query, following `src/queries/me.js`: a `moderationUsersKey` constant plus
`useModerationUsers()` and `useModerationUserImages({ ref, state, character, page })` with the key
spread across those inputs. `queries/` is the newer direction; `CustomsPage`'s raw
`useEffect` + `cancelled` flag is the older pattern and does not need copying here.

Two `apiClient` methods in `src/api.js`, built like `listCustoms` — a destructured options object
with defaults, and `URLSearchParams`.

#### 8. The page — `src/pages/moderation/`

`ModerationPage.jsx` owns the URL state and composes two children. Copy the `useSearchParams`
discipline from `CustomsPage.jsx` exactly: functional `setParams`, the default value is the *absence*
of the param, and a filter change resets `page` with `{ replace: true }` while a first selection
pushes.

```
/moderation?user=<ref>&state=removed&char=Rem&page=2
```

**`UserList.jsx`** — the master. The list is small and fully loaded, which is the case
`profile/useFilteredList.js` exists for: reuse it for query, sort and order rather than adding
server-side search. Render through the existing `FilterBar` with `mode` omitted — there is no
Name/Series choice here — and sort options *Most added* / *Most removed* / *Recent activity* /
*Name*. Each row is a `Card` carrying the handle, a `Badge tone="neutral"` when the role is not
`user`, and two counts in `.tabular`. The selected row carries `is-selected`.

**`UserDetail.jsx`** — the detail. A header line with handle and totals; a `SegmentedControl` for
Added / Removed that reads its counts back (`Added 12` / `Removed 3`); a character filter; then the
grid. Reuse `profile/CardGrid.jsx` in its justified image mode so these look identical to the Hidden
and Removed profile tabs — same cards, same thumbnails, same `portraitUrl`. Each card links to
`/character/<name>`, which is where the acting verbs live. Server-paged, with the same four-arrow
control as `customs-pagination`.

The three list states are not optional, and are the reason `profile/ListTab.jsx` exists: a skeleton
grid while loading (never "nothing here" for half a second, which is actively misleading), an
`EmptyState` for a filter that matched nothing with a clear action, and a *different* `EmptyState`
for a genuinely empty list. Failure is an `EmptyState` with a retry button, as on `CustomsPage` — not
a red banner.

Before any user is selected the detail pane is an `EmptyState`: *"Pick a contributor to see what they
added and removed."*

#### 9. Wiring

- **`App.jsx`** — one route above the `*` catch-all:
  `<Route path="/moderation" element={<RequireModerator><ModerationPage /></RequireModerator>} />`
- **`Navbar.jsx`** — a fourth inline link in the end rail, wrapped in `{me?.is_moderator && …}`, as
  `Button as={Link} variant="ghost" className="btn-nav"`. Ghost, not primary: Add Character already
  owns the one solid button per screen, and this is a correction tool, not something every visitor
  uses. The existing `navbar-role` badge is the precedent for role-conditional chrome. It must fold
  into the hamburger below 960px like its siblings.
- **`pages.css`** — a new `/* Moderation */` section after the existing "Identity and moderation"
  block. **Its responsive rules go in that same section**, not in a separate media-query pile at the
  end of the file; DESIGN.md names that as a bug that already shipped once. Classes: `.moderation`,
  `.moderation-user`, `.moderation-user__counts`, `.moderation-detail`,
  `.moderation-detail__header`, with `is-selected` for state. Below 768px the master collapses above
  the detail in one column.

Design constraints that apply, from DESIGN.md: this is off a character page, so the Art Carries the
Colour Rule is absolute — no tinted cards, no coloured headers, accent marks state only. Counts are
figures that update in place, so `tabular-nums`. Four breakpoints, four radii, no hex outside
`tokens.css`.

#### 10. Docs to update alongside

Two files will state the opposite of what is true, and DESIGN.md's own meta-rule is that a document
whose claims are already false teaches the next reader that the rules are decorative.

- **`DECISIONS.md` §5** — record that an inspection surface was added, and why it does not contradict
  the non-goal: no queue, no pending count, no action verbs.
- **`CURRENT_STATE.md` §9** — *"A moderation queue… there is no review screen"* narrows to the part
  that stays true: no queue, no appeal, reports still unread.
- **`ROADMAP.md`** — a Phase 7 entry.

---

### Verification

1. `cd frontend && npm run build`, `npx biome check src`, `npm test` — clean.
   `frontend/src/styles/tokenPairs.test.js` enforces the token rules and must pass **without being
   edited**.
2. Add the route to `pages.smoke.test.jsx`, which renders every route.
3. New `frontend/src/pages/moderation/moderation.test.jsx`, in house style — a docblock naming the
   rule being protected, `vi.hoisted` + `vi.mock('../../api')`, role-based queries, a `LocationProbe`
   inside `MemoryRouter`. Cover: a non-moderator is redirected and the page never renders; a
   moderator sees the list; selecting a user puts `?user=` in the URL and back clears it; switching
   to Removed refetches **on the server** with `state=removed` rather than filtering in the browser;
   the character filter resets the page to 1; the three list states are distinguishable.
4. New `tests/test_moderation.py`: a plain user gets 403 from both endpoints; a moderator gets the
   list; someone who has only *removed* something still appears; an unknown `ref` is 404; an invalid
   `state` is 400; `public_ref` round-trips through `identity_by_ref`; and **the raw identity id
   appears nowhere in either response body**, asserted against the serialized JSON.
5. Manual pass against real data (`vite` proxying to :5000, 1,706 characters and 8,547 images), as
   both a moderator and a plain user. Check that unattributed images surface no actor, and that a
   contributor with hundreds of images pages rather than loading all of them.
6. Keyboard and theme: tab from the master into the detail with a visible ring on every stop; light,
   dark, and system with no stored preference; 480 / 768 / 960 / 1200.

---

## Later phases

Sketches only. Each needs its own decision before it is built, and none is committed to by phase 1.

**Phase 2 — acting as staff.** Promote and demote, wrapping the already-written `db.set_role`, on an
owner-only route. This is the piece with no fallback today: the only way to make a moderator is a
manual `UPDATE` or the `OWNER_DISCORD_ID` bootstrap at Discord login, which cannot promote anyone but
the owner. Also the question of whether removal and restore belong on the moderation page at all, or
stay on the character page where the context is — phase 1 assumes the latter.

**Phase 3 — the reports question.** Whether `image_reports` should ever be readable, given that §1
designed it to work *without* a human. The honest case for reading it is diagnostic rather than
operational: knowing which reasons are actually used, and whether the threshold of two is right,
cannot be learned from a table nobody queries. That is an argument for a statistic, not a queue, and
the distinction should be settled before anything is built.
