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

The surface is a **master list of contributors** on the left, and, for the selected one, a **profile
pane** on the right: their stats and the staff actions that act on the *person* (warn, suspend, ban),
above their work — the images they added or removed, with the verbs that act on an *image* (restore,
permanent delete), and a character-level view of the same work sorted the way Browse Customs sorts
characters.

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
- **The acting verbs live where the evidence is.** Removal and restore stay on the character page,
  and the moderation page now also carries them (restore, and the permanent delete that did not
  exist before). What it still must not become is a worklist: nothing is queued, nothing is
  assigned, and a verb is only reachable after deliberately opening one contributor.
- **`image_reports` stays unread** in phase 1. Surfacing reports *is* the queue — that is precisely
  the mechanism §1 designed to work without a human, auto-removing at two distinct reporters. A
  review screen for it is a real decision with real arguments on both sides, and it deserves its own
  entry rather than arriving as a side effect of building a user list.

If a later phase finds itself adding a pending count, that is the signal to re-read §1 and fix the
thing generating the backlog instead.

---

## Phase 1 — the review surface

`/moderation`, staff-only. A master list of contributors; pick one and the right pane becomes their
profile — stats and staff actions — above their work, which can be read as a paged image grid
(added or removed, filtered by character) or as a character-level list sorted by rank, image count,
name or recency.

**Phase 1 is the full UI and the `GET` endpoints behind it. Every acting button is present and
inert** — warn, suspend, ban, restore, permanent delete. Wiring them is later (§ Later phases), and
deliberately so: the layout is worth settling before any of it does something irreversible.

### Decisions taken

| Question | Decision |
|---|---|
| Backend scope | The UI **and** the read-only endpoints. The action verbs are rendered but do nothing yet. |
| Who is listed | Every identity with at least one added or removed image — pseudonyms included, `hide_from_leaderboard` and `hide_attribution` ignored. Idle cookie-only identities are excluded. |
| Shape | Master–detail on one route, selection and filters carried in the URL (`?user=…&view=…&state=…&char=…&sort=…&page=…`). |
| Profile pane | Stats (total images, removed, account created, last activity, signed-in) and person-level actions (warn, suspend, ban). |
| Work pane | Two views of the same contributor: **Images** (the grid, per-image restore / permanent delete) and **Characters** (rank, image count, name, recency — the Browse Customs vocabulary). |
| Gating | Non-moderators are redirected home, indistinguishable from the existing `*` catch-all. The backend enforces separately and does not trust the client. |

#### On putting the verbs on this page

The first draft of this document said the acting verbs would stay on the character page, because a
list of verbs is what turns a list into a worklist. That rule is now relaxed for **image** verbs —
restore, and the permanent delete that had no home before — for a specific reason: the moderation
page is the only place where the *pattern* is visible. Removing one image from a character page is a
local decision; seeing that the same contributor removed forty images across twenty characters is the
thing that needs a restore/deep-delete verb next to it, and it cannot be seen anywhere else.

What still holds is the thing the rule was protecting: this page is never *worked*. There is no
queue, no pending count, no assignment. Seeing the pattern still requires opening one contributor on
purpose. If a later phase adds a badge or a "needs review" list, that is the signal to re-read §1.

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

- **The action logic.** Every acting button exists and is inert. Warn/suspend/ban are a later phase
  with a real design question (what does "suspended" mean for a cookie identity?), and permanent
  delete — which removes the image from ImgChest too, not just the row — is its own decision because
  it is the first irreversible action in the app. `db.set_role` likewise stays a test-only function
  until the owner-only promote/demote route is built.
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

Each item also carries `created_at` from the identity row — the account's age, which the profile
pane shows. It is `NULL` for an actor whose identity row does not exist yet.

**`list_images_by_identity(identity_id, *, state, character=None, page, per_page)`** — the gallery
rows for one actor. `state='active'` filters `added_by = ? AND state = 'active'`; `state='removed'`
filters `removed_by = ? AND state = 'removed'`. Shape the rows exactly as `get_removed_by_identity`
already does — `id`, `url`, `thumb` via `thumbnails.thumb_url`, `width`, `height`, `character`,
timestamps, reason — so the frontend can render them with the card grid that already exists. Returns
`{items, total, total_pages, added, removed}`, the totals matching `list_contributors` so the header
is right before either list loads.

**`list_characters_by_identity(identity_id, *, state, query=None, sort, order, page, per_page)`** —
the character-level view: the characters this actor added to (or removed from), grouped, each with
its image count, series, rank and portrait. The sort vocabulary is Browse Customs' — rank, image
count, name, recency — reusing `_CUSTOMS_SORTS` where it fits, and recency is `MAX(added_at)` /
`MAX(removed_at)` for this actor rather than `characters.updated_at`. Same paged return shape.

#### 4. `routes/moderation.py`

A new blueprint, registered in `upload_imgchest.py` beside the other seven.

| Route | Returns |
|---|---|
| `GET /api/moderation/users` | `{items: [{ref, handle, role, signed_in, added, removed, last_at, created_at}], total}` |
| `GET /api/moderation/users/<ref>/images?state=&character=&page=&per_page=` | Paged gallery rows for one actor, plus `{added, removed}` totals so the profile header is right before either list loads |
| `GET /api/moderation/users/<ref>/characters?state=&character=&sort=&order=&page=&per_page=` | Paged character rows (count, series, rank, portrait) for the character view |

All `@require_moderator`. Unknown `ref` → 404. `state` whitelisted to `active` / `removed`, `sort` to
the known keys, anything else 400 — the same shape of validation `sort` already gets in
`routes/customs.py`.

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

react-query, following `src/queries/me.js`: `moderationUsersKey` plus `useModerationUsers()`,
`useModerationUserImages({ ref, state, character, page })` and
`useModerationUserCharacters({ ref, state, query, sort, order, page })`, each key spread across
exactly the inputs the request uses. `queries/` is the newer direction; `CustomsPage`'s raw
`useEffect` + `cancelled` flag is the older pattern and does not need copying here.

Three `apiClient` methods in `src/api.js`, built like `listCustoms` — a destructured options object
with defaults, and `URLSearchParams`.

#### 8. The page — `src/pages/moderation/`

`ModerationPage.jsx` owns the URL state and composes the master with the selected contributor's
profile and work. Copy the `useSearchParams` discipline from `CustomsPage.jsx` exactly: functional
`setParams`, the default value is the *absence* of the param, and a filter change resets `page` with
`{ replace: true }` while a first selection pushes.

```
/moderation?user=<ref>&view=characters&state=removed&char=Rem&sort=rank&order=asc&page=2
```

**`UserList.jsx`** — the master. The list is small and fully loaded, which is the case
`profile/useFilteredList.js` exists for: reuse it for query, sort and order rather than adding
server-side search. Render through the existing `FilterBar` with `mode` omitted — there is no
Name/Series choice here — and sort options *Most added* / *Most removed* / *Recent activity* /
*Name*. Each row is a `Card` carrying the handle, a `Badge tone="neutral"` when the role is not
`user`, and two counts in `.tabular`. The selected row carries `is-selected`.

**`UserProfile.jsx`** — the selected contributor. A header with the handle, a role `Badge`, and the
stats: **total images** (active), **removed**, **account created** (`created_at`), **last activity**,
and whether they are Discord-signed-in, all counts in `.tabular`. Below them the person-level
actions — **Warn**, **Suspend**, **Ban** — rendered as buttons and **inert in phase 1** (`disabled`,
with a title saying so); owner-only promote/demote joins them in a later phase.

**`UserWork.jsx`** — the contributor's work, in two views behind a `SegmentedControl`:

- **Images** — the Added / Removed switch (counts read back), a character filter, and the grid:
  `profile/CardGrid.jsx` in its justified mode, so these are the same cards as the Hidden and Removed
  profile tabs. Each card carries the image verbs as `action`s — **Restore** on a removed image,
  **Permanently delete** on either — rendered and inert. Cards still link to `/character/<name>`.
- **Characters** — the same contributor's characters, grouped, each card carrying the name, series
  and image count, sorted with the Browse Customs vocabulary: *Most images* / *Rank* / *Name* /
  *Recent*. This is the "where is their work concentrated" answer the image grid cannot give.

Both are server-paged, with the same four-arrow control as `customs-pagination`.

The three list states are not optional, and are the reason `profile/ListTab.jsx` exists: a skeleton
grid while loading (never "nothing here" for half a second, which is actively misleading), an
`EmptyState` for a filter that matched nothing with a clear action, and a *different* `EmptyState`
for a genuinely empty list. Failure is an `EmptyState` with a retry button, as on `CustomsPage` — not
a red banner. The same applies to both work views.

Before any user is selected the right-hand pane is an `EmptyState`: *"Pick a contributor to see what
they added and removed."*

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
  `.moderation-users`, `.moderation-user`, `.moderation-user__counts`, `.moderation-profile`,
  `.moderation-profile__stats`, `.moderation-profile__actions`, `.moderation-work`,
  `.moderation-work__header`, with `is-selected` for state. Below 768px the master collapses above
  the profile in one column.

Design constraints that apply, from DESIGN.md: this is off a character page, so the Art Carries the
Colour Rule is absolute — no tinted cards, no coloured headers, accent marks state only. Counts are
figures that update in place, so `tabular-nums`. Four breakpoints, four radii, no hex outside
`tokens.css`.

#### 10. Docs to update alongside

Two files will state the opposite of what is true, and DESIGN.md's own meta-rule is that a document
whose claims are already false teaches the next reader that the rules are decorative.

- **`DECISIONS.md` §5** — record that an inspection surface was added, and why it does not contradict
  the non-goal: no queue, no pending count, no acting *logic* (the buttons are inert), reports still
  unread.
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
   Plus, for the profile: the stats render from the contributor row; the person and image verbs are
   present and **disabled** (nothing fires); and switching the work view to Characters asks the
   server with the chosen `sort`/`order`.
4. New `tests/test_moderation.py`: a plain user gets 403 from every endpoint; a moderator gets the
   list; someone who has only *removed* something still appears; an unknown `ref` is 404; an invalid
   `state` or `sort` is 400; `created_at` is carried; the character list groups and orders; the paged
   shapes carry totals; `public_ref` round-trips through `identity_by_ref`; and **the raw identity id
   appears nowhere in any response body**, asserted against the serialized JSON.
5. Manual pass against real data (`vite` proxying to :5000, 1,706 characters and 8,547 images), as
   both a moderator and a plain user. Check that unattributed images surface no actor, that a
   contributor with hundreds of images pages rather than loading all of them, and that the character
   view sorts by rank and by image count the way Browse Customs does.
6. Keyboard and theme: tab from the master through the profile stats and actions into the work panes
   with a visible ring on every stop (except the disabled buttons, which are correctly skipped);
   light, dark, and system with no stored preference; 480 / 768 / 960 / 1200.

---

## Later phases

Sketches only. Each needs its own decision before it is built, and none is committed to by phase 1.
The phase-1 buttons exist precisely so their placement and wording can be settled without their
logic.

**Phase 2 — acting on a person.** Warn, suspend, ban, and (owner-only) promote/demote wrapping the
already-written `db.set_role`. The hard question is what these mean for a *cookie* identity: a ban
that deletes the cookie is walked around by clearing it, and one that blocks an id is walked around
by clearing it too. So the design has to decide whether these act on the identity, the Discord
account, or the IP, and say plainly what each buys. Promote/demote is the piece with no fallback
today — the only moderator is the `OWNER_DISCORD_ID` bootstrap.

**Phase 3 — acting on an image, including permanent delete.** Restore already exists server-side.
Permanent delete does not, and it is the first irreversible action in the app: it would remove the
row *and* the file from ImgChest. That needs a decision on its own — whether ImgChest even exposes a
delete, what happens to `$ai` commands already copied out, and whether a two-step confirm (or a
"recently destroyed" holding period) is warranted. The button is inert until then.

**Phase 4 — the reports question.** Whether `image_reports` should ever be readable, given that §1
designed it to work *without* a human. The honest case for reading it is diagnostic rather than
operational: knowing which reasons are actually used, and whether the threshold of two is right,
cannot be learned from a table nobody queries. That is an argument for a statistic, not a queue, and
the distinction should be settled before anything is built.
