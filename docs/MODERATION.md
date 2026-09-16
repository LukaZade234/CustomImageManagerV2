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

The surface opens as a **finder** — a centred search and a row of facets (role, Discord account, has
removals, sort) over the bounded contributor list. Picking someone turns the page into their **Info /
Images** tabs: **Info** is the profile (stats, the staff actions that act on the *person*, and the
**moderation history** — every message staff have sent them); **Images** is their work (the images
they added or removed, with the verbs that act on an *image* — restore, permanent delete — and a
character-level view sorted the way Browse Customs sorts).

It lives **inside the profile**, as one more tab beside Saved, History, Hidden and Removed, and not
in the topbar. It is something you go to; a permanent topbar entry for a staff tool is the queue's
chrome by another route. The topbar instead carries **Notifications**, which is the channel the
moderation plan needs (below).

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

`/moderation`, staff-only. It opens as a **finder** — a prominent search with facets (role, Discord
account, has removals, sort) over the bounded contributor list. Pick someone and the page becomes
their **Info / Images** tabs: Info is the profile (stats and staff actions) and the moderation
history; Images is their work, readable as a paged image grid (added or removed, filtered by
character) or as a character-level list sorted by rank, image count, name or recency.

**Phase 1 was the full UI and the `GET` endpoints behind it, with every acting button present and
inert.** All of those verbs are now live: **restore** an image, the **owner-only** promote/demote,
**warn** a person (a message), **suspend / ban** (a state, below), and **permanent delete** (the one
irreversible act, below). The last is staff, and a one-time backfill brings the whole old library
within reach.

### Decisions taken

| Question | Decision |
|---|---|
| Backend scope | The UI **and** the read-only endpoints. The action verbs are rendered but do nothing yet. |
| Who is listed | Every identity with at least one added or removed image — pseudonyms included, `hide_from_leaderboard` and `hide_attribution` ignored. Idle cookie-only identities are excluded. |
| Shape | A **finder** first (centred search + facets over the list), then **Info / Images** tabs once a contributor is picked, on one route. Selection and filters are carried in the URL (`?user=…&tab=…&view=…&state=…&char=…&sort=…&page=…`). |
| Info tab | Stats (total images, removed, account created, last activity, signed-in), person-level actions (warn, suspend, ban), and the moderation history. |
| Images tab | Two views of the same contributor: **Images** (the grid, per-image restore / permanent delete) and **Characters** (rank, image count, name, recency — the Browse Customs vocabulary), with the character filter and added/removed switch. |
| Gating | Non-moderators are redirected home, indistinguishable from the existing `*` catch-all. The backend enforces separately and does not trust the client. |

#### The Cut-over tab, and why it is owner-only

A fourth tab, **Cut-over**, is appended to the staff area but shown only to the owner, and its route
is wrapped in `RequireOwner` (one level stricter than the console around it). It renders the preview
that `scripts/imgchest_cleanup.py` writes — the flat list of ImgChest files that would be permanently
deleted, the flat list that would be recovered into the Removed drawer, and the counts and warnings.
It is **read-only**: the app reads a JSON file and never deletes; the destructive half is the CLI,
run by hand. See `CUTOVER.md` and `DECISIONS.md` §2.

It is owner-only rather than moderator-only because reconciling and deleting from the ImgChest
account is operator work, not moderation, and this page is not a queue either: it holds no work and
changes no chrome. It is the same reasoning that keeps the tab out of the topbar.

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

- **The remaining action logic.** Restore, promote/demote, warn, suspend, ban and permanent delete are
  all wired (see below). The last is staff, and a one-off backfill recovers the post ids the old
  library never had.
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
| `POST /api/moderation/users/<ref>/role` | Owner only: set `role` to `moderator` (promote) or `user` (demote). Refuses `owner`, your own role, and the owner's |

All `@require_moderator` except the role route, which is `@require_owner`. Unknown `ref` → 404.
`state` whitelisted to `active` / `removed`, `sort` to the known keys, `role` to `user` / `moderator`,
anything else 400 — the same shape of validation `sort` already gets in `routes/customs.py`.

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

**`ContributorFinder.jsx`** — the opening state. A prominent centred search with a row of facets
beneath it, then the list. The list is small and fully loaded, which is the case
`profile/useFilteredList.js` exists for: reuse it for query and sort (search by handle; *Most added* /
*Most removed* / *Recent activity* / *Newest accounts* / *Name*) rather than adding server-side
search. The facets are
in-memory too — **Role** (staff only), **Account** (Discord only) and **History** (has removals) — each
a labelled `Select`, because those are the questions worth asking before picking a name: are they
staff, would a ban mean anything, and have they removed anything. Each row is a `Card` carrying the
handle, `Badge`s for role and Discord, and two counts in `.tabular`.

**`ModerationPage.jsx`** — two states on one route. With no `?user`, the finder; with one, a way back
and the **Info / Images** tabs, then the tab's content. The tabs are the profile's own tab bar
(`profile-tabs`: anchors with the accent underline), not a second tab idiom — History, Hidden and
Moderation are the same kind of place — and each is a real link whose `info` default is the absence
of `?tab`. The work queries are gated to the Images tab (`enabled`), so opening someone on Info does
not fetch their gallery; the history is fetched whenever a contributor is selected. Picking a
contributor pushes and resets every filter that belonged to the last person; the tab links replace,
so Back leaves the contributor rather than walking their tabs.

**`UserProfile.jsx`** — the selected contributor. A header with the handle, a role `Badge`, and the
stats: **total images** (active), **removed**, **account created** (`created_at`), **last activity**,
and whether they are Discord-signed-in, all counts in `.tabular`. Below them the person-level actions:
**Warn** is live and opens `WarnDialog`; **Suspend** and **Ban** are rendered but **inert**
(`disabled`, with a title saying so).

For the **owner alone**, a plus/minus `IconButton` sits beside the name: plus for a `user` (promote),
minus for a `moderator` (demote), nothing for the `owner`. Either opens a `ConfirmDialog`, and only
the confirm calls the route. Moderators do not see the control at all — they hold every other power
the owner has, but not this one.

**`UserWork.jsx`** — the contributor's work, in two views behind a `SegmentedControl`:

- **Images** — the Added / Removed switch (counts read back), a character filter, and the grid:
  `profile/CardGrid.jsx` in its justified mode, so these are the same cards as the Hidden and Removed
  profile tabs. Each card carries the image verbs in its top corner as **icons** — **Restore** on a
  removed image (live, reusing `/api/restore-images`), **Delete permanently** on either (inert) — the
  icons rather than words because a narrow portrait has no room for two labels, over the image and
  always visible as a hover reveal would hide the choice the grid exists to offer.
- **Characters** — the same contributor's characters, grouped, each card carrying the name, series
  and image count, sorted with the Browse Customs vocabulary: *Most images* / *Rank* / *Name* /
  *Recent*. This is the "where is their work concentrated" answer the image grid cannot give.
  **Clicking a character does not navigate to the public character page** — it switches to the Images
  view filtered to that character, so the operator stays in context and sees this contributor's
  images on it. The character is a filter here, not a destination.

Both are server-paged, with the same four-arrow control as `customs-pagination`.

The three list states are not optional, and are the reason `profile/ListTab.jsx` exists: a skeleton
grid while loading (never "nothing here" for half a second, which is actively misleading), an
`EmptyState` for a filter that matched nothing with a clear action, and a *different* `EmptyState`
for a genuinely empty list. Failure is an `EmptyState` with a retry button, as on `CustomsPage` — not
a red banner. The same applies to both work views.

Before any user is selected the right-hand pane is an `EmptyState`: *"Pick a contributor to see what
they added and removed."*

#### 9. Wiring

- **`App.jsx`** — the route is a child of `/profile`, behind the guard:
  `<Route path="moderation" element={<RequireModerator><ModerationPage /></RequireModerator>} />`.
  `/moderation` stays as a redirect into it for old links.
- **`ProfileLayout.jsx`** — a **Moderation** tab, added to the tab list only when `me.is_moderator`.
- **`Navbar.jsx`** — no moderation entry. The end rail's fourth link is **Notifications** (see
  below), because that is the thing every visitor has.
- **`pages.css`** — a `/* Moderation */` section in the "Identity and moderation" block. **Its
  responsive rules go in that same section**, not in a separate media-query pile at the end of the
  file; DESIGN.md names that as a bug that already shipped once. Classes: `.moderation-finder`,
  `.moderation-finder__search`, `.moderation-finder__input`, `.moderation-finder__filters`,
  `.moderation-facet`, `.moderation-head`, `.moderation-back`, `.moderation-tabpanel`,
  `.moderation-dialog`, `.restriction-banner`,
  `.moderation-users`, `.moderation-user`, `.moderation-user__counts`, `.moderation-profile`,
  `.moderation-profile__stats`, `.moderation-profile__actions`, `.moderation-work`,
  `.moderation-work__header`. The finder is a centred 720px column; below 768px the contributor list
  caps its height so the search stays in view.

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

## Notifications — the channel moderation needs

The topbar carries **Notifications** (`/notifications`), because moderation needs a way to *tell*
someone something. It is the channel a warn rides: a warning is a message here, and this page is
where the recipient reads it.

**Shape.** A simple, hairline-separated list — a title, a date, and optional body text, newest first.
Two sources:

- **Mechanical** — the system telling you about your own account. The first is a role change:
  promoted to moderator, or demoted. More hook onto the same `db.add_notification` call as the
  actions that need them land (a moderator removing your image, a report threshold clearing it).
- **Owner-authored** — the owner writes a message and sends it. The compose section sits at the top
  of the page and is owner-only: choose an audience (**everyone**, or **moderators only**), a title,
  a body, and whether to **pin** it. Deliberately a small template, not a rich editor.

**Ordinary vs pinned — two different things.** An ordinary broadcast is fanned out to one row per
recipient identity at send time: it is delivered, its `read_at` is per person, and each recipient can
**dismiss** it (a hard delete of their own row). The cost of fan-out is that someone who arrives
after the send does not receive it — which is what "a message sent on a date" means.

A **pin** cannot work that way. It must stay visible *including to an account created later*, and it
cannot be dismissed, so it has no per-identity copy at all: it is one global row, resolved at read
time by audience (`everyone`, or `moderators` for staff). Read state lives in a join table
(`pinned_notification_reads`), so a pin counts as **unread** for an identity until that identity has
opened the list once — which is what makes a message sent before an account existed still arrive
unread for it. A pin still cannot be dismissed: there is no delete path for it, only read state.

**Deleting.** The owner can remove any notification from everyone's inbox. An ordinary broadcast is
deleted as a group (the rows share a `group_id`); a pin is a single row and simply goes; a mechanical
message has no group and is deleted on its own. The owner's delete is confirmed, because it is
irreversible and reaches other people.

**What it is not.** Not a queue, and not a second inbox to tend: nothing is assigned, nothing is
counted as pending *work*, and the unread dot is only ever your own messages. Mechanical
notifications are the app talking to one person about their own account; the owner's are an
announcement. Nothing here is actionable — acting still happens where the thing happened.

### Backend
- Migration `014_notifications.sql`: `notifications(id, identity_id, kind, title, body, created_by,
  created_at, read_at)`, `kind` in `mechanical` / `broadcast`, indexed on `(identity_id, created_at)`.
- Migration `015_notification_pins.sql`: `notifications.group_id` (ties a broadcast together) and the
  global `pinned_notifications(id, audience, title, body, created_by, created_at)`.
- Migration `016_pinned_notification_reads.sql`: `pinned_notification_reads(identity_id, pinned_id,
  read_at)`, so a pin has per-identity read state without a per-identity copy.
- `db.add_notification`, `db.list_notifications(identity_id, is_staff=…)` (own rows merged with the
  pins the identity can see, each pin carrying this identity's read state),
  `db.count_unread_notifications(identity_id, is_staff=…)` (normal unread plus unread pins),
  `db.mark_notifications_read` (marks normal rows and inserts a pin read row per visible pin),
  `db.dismiss_notification`, `db.delete_notification(source, id)`,
  `db.broadcast_notification(…, pinned=…)`.
- `routes/notifications.py`: `GET /api/notifications`, `POST /api/notifications/read`,
  `POST /api/notifications/dismiss` (own row), `POST /api/notifications/delete` (owner only), and
  `POST /api/notifications/broadcast` (owner only, takes `pinned`).
- The role-change route writes a mechanical notification to the target.

### Frontend
- `queries/notifications.js` polls every 60 seconds and refetches on focus — the one query whose change
  comes from elsewhere, so it cannot rely on its own mutation to invalidate it. A Notifications entry
  sits in the navbar's end rail just left of the profile link, so it rides with the links. On a folded
  bar that group is behind the hamburger, so while something is unread an icon-only bell **also**
  appears on the bar itself, left of the menu button, and pulses (a circular accent ring around the
  bell); opening the menu swaps that bar copy for the labelled one. The owner's compose form is the
  first card on the page, owner-only, with a pin checkbox. Ordinary rows carry **Dismiss**; pins carry
  a **Pinned** badge and no dismiss; the owner additionally sees a confirmed **Delete** on every row.
  A moderation message is the one kind with a severity: its title is coloured and it carries a badge
  (`utils/moderationActions.js`).

---

## Warnings, and the moderation history

A **warn** is the first person-level action. It does exactly two things, and they are deliberately
distinct:

- it delivers the recipient a **notification** — an ordinary, dismissible message, badged and
  coloured by severity (warning amber, suspension orange, ban red); and
- it writes a line to the target's **moderation history**, the durable staff record.

The record has to outlive the message: a recipient dismissing their warning must not delete the fact
that staff sent one. So the two are different rows. `moderation_actions` is the log; the delivered
notification points back at it with `moderation_action_id`, and that link is `ON DELETE CASCADE`, so
the owner's delete runs from the record to the message and the two can never disagree about whether a
warning was sent.

All three verbs are wired. Warn is a message only. **Suspend and ban add a state** — and that change
has to outlive the message, because dismissing the notification must not lift the restriction.

### Suspension and ban — the state, not the message

A restricted account may still **read** the site. A restriction cannot hide content that an anonymous
visitor can read anyway, so it does not try; it removes the ability to *change* anything, which is the
only lever a ban has. So the live state is its own row, `moderation_status` (migration 018), keyed by
identity.

- **Suspended** — time-boxed. `until` comes from the composer's duration; reads pass, writes are
  refused, and it expires on its own at read time.
- **Banned** — open-ended, same enforcement, no end. The anchor is the identity, whose `discord_id` is
  unique: signing in on a fresh cookie finds the same row and adopts it, so the ban follows the
  Discord account rather than the cookie.
- **The person is told.** There is no email, so the account can still sign in and read a persistent,
  non-dismissible **banner** on every page, plus the notification in their inbox. Only
  `/api/auth/logout` and the notifications read/dismiss routes are allowed through while restricted;
  everything else is refused, so they can read the notice and leave.
- **Lifting** is owner-only, clears the state, and sends a notification.
- **Limits, accepted deliberately.** A *different* Discord account slips past, and a cookie-only
  identity (no Discord) can be blocked but evaded with a new cookie. A ban is only as durable as the
  Discord binding it hangs on. This is why `DECISIONS.md` §4 says bans became meaningful once
  uploading required Discord.

#### The second Discord account — a signal, not a rule

The one evasion the identity anchor cannot catch is a person making a *new* Discord account. An IP
looked like the tool for it, and was rejected as a restriction: an address is a mobile carrier, a
household or a VPN exit as often as it is one person, it rotates, and it is evaded by a VPN — so an
IP ban is both easy to escape and expensive in innocents. It is the worst shape of lever.

What is kept instead is weaker and safer: every write records a **keyed hash** of the client address
(never the address), tied to the identity and pruned after 90 days. When a contributor has been seen
from a network a *currently restricted other* account used, their profile says so — a label for a
moderator to weigh, not an action the app takes. Nothing is auto-restricted, no backlog accumulates,
and a shared household network is a question rather than a sentence.

The obvious caveats: the hash is only as trustworthy as the header it comes from (Cloudflare's
`CF-Connecting-IP`, else the first `X-Forwarded-For` hop — meaningful only when the origin is reached
through the proxy), and a VPN defeats it. It is a lead, not proof.

### Backend
- Migration `017_moderation_actions.sql`:
  `moderation_actions(id, identity_id, actor_id, action, title, body, created_at)`, `action` in
  `warn` / `suspend` / `ban`, indexed on `(identity_id, created_at DESC)`; and
  `notifications.moderation_action_id` pointing at it with `ON DELETE CASCADE`.
- Migration `018_moderation_status.sql`:
  `moderation_status(identity_id PK, status, until, reason, actor_id, created_at)`, `status` in
  `suspended` / `banned`. `db.get_identity` joins it in and expires an old suspension;
  `db.set_moderation_status` / `db.clear_moderation_status` write it.
- Migration `019_identity_networks.sql`:
  `identity_networks(identity_id, ip_hash, first_seen, last_seen, hits)` keyed on
  `(identity_id, ip_hash)`. `identity.record_network` (a `before_request` ahead of the guard) writes a
  keyed hash of the client address on every non-GET; `db.record_identity_network` upserts it and prunes
  past a 90-day window. `db.list_contributors` carries `linked_restricted`.
- `db.moderate_identity` (log the action, deliver the message, return its id),
  `db.list_moderation_actions(identity_id)` (the log with the sender's handle) and
  `db.delete_moderation_action(id)` (owner-only at the route; the cascade removes the message).
  `db.list_notifications` joins the link to carry `moderation_action` on each item.
- `identity.block_restricted_writes` — a `before_request` after `load_identity` that refuses every
  non-GET for a restricted identity. It allow-lists the POSTs that are reads in disguise:
  `/api/auth/logout`, notifications read/dismiss, `/api/download-image-proxy`, `/api/takes`, and
  recording a page view. `identity.Identity` carries `is_suspended` / `is_banned` / `is_restricted`,
  and `/api/me` returns the status, its end and the reason.
- `routes/moderation.py`: `POST .../warn`, `.../suspend` (takes `days`), `.../ban` — any moderator,
  but the owner is never a target, you cannot target yourself, and a moderator cannot target another
  moderator (staff-on-staff restriction is an owner move) — `.../lift` (owner only), `GET .../history`,
  and `POST /api/moderation/history/<int:action_id>/delete` (owner only).

### Frontend
- `ModerationDialog.jsx`: the one popup behind **Warn / Suspend / Ban** — a title (required), a
  description, and a duration for a suspension. What the moderator writes is exactly what the
  recipient reads, and the lead names the difference a suspend or ban makes.
- `UserProfile.jsx`: the three buttons, the current status as a badge (with a suspension's end date),
  a disabled **Ban** once already banned, an owner-only confirmed **Lift**, and the linked-network
  signal when `linked_restricted`.
- `RestrictionBanner.jsx`: the global notice, tinted from the status colour and rendered above the app
  shell; it disappears the moment the restriction is lifted.
- `ModerationHistory.jsx`: the selected contributor's record, under their header — each line badged
  and titled by severity, naming the sender. The owner gets a confirmed **Delete**; a moderator's is
  view-only. `utils/moderationActions.js` is the one map from action (and status) to label and colour,
  used here and in the inbox so the two never drift. It rides on `--caution`, the orange added to the
  status palette in `tokens.css` for the middle severity.

---

## Permanent delete

The app's one irreversible act, and the exception to "nothing is ever hard-deleted".

**What research settled.** ImgChest does expose deletion, but not the one we wanted: `DELETE
/v1/file/{id}` is refused with *"You can't delete the only image on a post"*, and every upload here is
a single-image post. The reachable lever is `DELETE /v1/post/{id}`. The create-post response carries
the post id as `data.id`; the uploader already had it and threw it away. There is **no file→post
lookup** (`GET /v1/file/{id}` returns an empty `200`). A merge route exists, but only on the website —
session-authenticated, undocumented — and it turned out to be unnecessary: `GET
/v1/user/{username}/posts` (documented API, the token we already hold) lists every post, hidden ones
included, with its `slug` and its first image's file id as `thumbnail.id`. Since every stored URL is
`cdn.imgchest.com/files/{id}.ext`, that maps the whole old library back to its posts with no session
and nothing risky.

**So:** new uploads store `imgchest_post_id` directly; old rows get theirs from
`scripts/backfill_imgchest_post_ids.py` (a one-time pass: ~141 page calls for 14k posts, which matched
**8,579 of 8,581** library rows). A purge then deletes the post. Staff, and behind a second,
explicit confirmation — an `$ai` command already copied into Discord breaks, and only a holding period
could soften that (none is built).

**Image-count aware.** The listing only exposes a post's *first* image, so a post that holds several
(possible only if posts were merged by hand) would lose its siblings if deleted whole — and its
non-first images have no post id at all, since nothing maps them. So a purge reads the post where it
can and decides: one image → `DELETE /v1/post/{id}`; more than one → `DELETE /v1/file/{file_id}` with
the id taken from the stored URL. Where there is **no** post id, it goes straight to the file delete,
which succeeds exactly when the post has siblings; only a single-image post we could not identify is
refused, and it says so.

**The tombstone.** The row is not deleted. It goes to `state='removed'` with `purged_at` set, hidden
from every removed list and refused by restore: the record survives for the audit, but nothing can
bring the image back. The cached thumbnail goes with it. The API's own `state` CHECK predates this, so
`purged` is a column, not a state value.

### Backend
- Migration `020_permanent_delete.sql`: `custom_images.imgchest_post_id` (the purge handle) and
  `custom_images.purged_at` (the tombstone). Every `state='removed'` query gained `purged_at IS NULL`,
  and restore refuses a purged row.
- `imgchest_utils`: `fetch_imgchest_post` (read the image count), `delete_imgchest_post`,
  `delete_imgchest_file`, and `file_id_from_url` — all `DELETE`/`GET` on the documented API, with the
  upload's retry/backoff; a `404` counts as success.
- `db.get_image_for_purge`, `db.purge_custom_image`, and `add_custom_images(..., post_ids=…)`.
- `routes/customs.py`: `POST /api/purge-custom-image` (`character_name`, `url`), staff only: verify,
  pick file vs post from the image count (falling back to a file delete when there is no post id),
  tombstone, drop the thumbnail.
- `scripts/backfill_imgchest_post_ids.py --username NAME [--dry-run]` — the one-off mapping pass.

### Frontend
- `UserWork.jsx`: **Delete permanently** is enabled for the owner, opens a confirmed `ConfirmDialog`
  ("Delete forever"), and is disabled with a reason for anyone else. `queries/moderation.js` adds
  `usePurgeModerationImage`, which refreshes both work views and the contributor counts.

### Later: the multi-image audit
We did not scan how many posts hold more than one image, or how large they are. It would need one
`GET /v1/post/{slug}` per post — 14,072 calls at the API's 60/min, roughly four hours — so it was set
aside. It is informational: the purge is already image-count aware and safe either way. Run it if a
merged post ever looks suspect, or if a future pass wants to know the shape of the account.


---

## Duplicate review

Duplicate detection belongs to uploads, not to this surface: the same file is recognised by a sha256
of its stored bytes, checked before it ever reaches ImgChest, and a same-character match is refused
with a dialog offering **Upload anyway** or, for a removed copy, **Restore it** (see `DECISIONS.md`,
"Uploading the same picture twice"). This section is the moderation half — seeing the duplicates
that are already in the library, from before that gate existed.

### Backend
- `db.find_images_by_content_hash` is the add-time gate; `db.images_missing_content_hash` /
  `db.set_content_hash` are the backfill; `db.list_duplicate_clusters` is the audit — unpurged rows
  a single character holds more than once, biggest cluster first, owner attribution shown as staff.
  Grouped **per character**: the same file on several characters is usually one image showing
  several of them, which is intentional, so only a character's own repeats are flagged.
- `scripts/backfill_content_hashes.py [--dry-run] [--limit N]` downloads each unfingerprinted image
  and records the sha256 of the stored file. Resumable and keyset-paginated; a failure (usually a
  dead link) leaves the row NULL for a later run.
- `GET /api/moderation/duplicates` (`require_moderator`) returns `{clusters, total}`.

### Frontend
- The staff area is one tabbed layout, `ModerationLayout.jsx`, with three sections: **Users**
  (`ModerationPage`, the contributor finder), **Reports** and **Duplicates** — real routes, so a tab
  is linkable and survives a reload, the same reasoning as `ProfileLayout`.
- **Duplicates** (`DuplicatesPage.jsx`) at `/profile/moderation/duplicates`. Each cluster is a Card
  of its copies — thumbnail, state, adder, date — where the thumbnail and the character name both
  open the character page. **Delete** permanently removes an active copy (confirmed first, and the
  ImgChest file goes with it); a copy already removed offers **Restore**. `queries/moderation.js`
  adds `useModerationDuplicates` and reuses `usePurgeModerationImage` / `useRestoreModerationImage`.


---

## Reports

Reporting already exists and already acts: two *distinct* reports remove an image (`DECISIONS.md`
§1). What this tab adds is the read — every reported image, split by whether the threshold has acted
yet.

### Backend
- `db.list_reported_images(status)` — `"reported"` for images still live with at least one report,
  `"removed"` for images the threshold already took down, `None` for both. Each item carries its
  individual reports (reason, reporter handle, time), so the *reasons* are readable, not just a
  count.
- `db.reported_image_counts()` — the two bucket sizes, for the filter labels.
- `GET /api/moderation/reports?status=reported|removed|all` (`require_moderator`) returns
  `{status, counts, items, total}`.

### Frontend
- **Reports** (`ReportsPage.jsx`) at `/profile/moderation/reports`: a segmented filter between **Not
  removed yet** and **Removed by reports** (the counts ride in the labels), then a card per image
  with its thumbnail, character, state and reports. Read-only, like the rest of the surface — the
  verbs to restore or delete an image stay where the image and its context are.
  `queries/moderation.js` adds `useModerationReports`.


---

## Later phases

Sketches only. Each needs its own decision before it is built, and none is committed to by phase 1.
The phase-1 buttons exist precisely so their placement and wording can be settled without their
logic.

**Phase 2 — acting on a person. Done.** Promote/demote, warn, suspend and ban are all wired. A
suspension is time-boxed and self-lifting; a ban is open-ended and anchored to the identity's unique
Discord id, so it survives a new cookie. Both leave the account able to read and to be told why, and
refuse every write. The owner alone lifts them. The one accepted gap is a *different* Discord account,
which nothing in this design can stop.

**Phase 3 — acting on an image, including permanent delete. Done.** ImgChest exposes
`DELETE /v1/post/{id}` (its `file` delete refuses to remove the only image in a post, and every upload
here is a single-image post). The post id is captured from the create response (`data.id`) for new
uploads and recovered for the old library from `GET /v1/user/{username}/posts` — the documented API,
no session and no merge. A purge reads the post and deletes the file when it has siblings, the post
when it does not. It is **staff-only** and the app's one irreversible act: a second, explicit
confirmation, and a tombstone (`purged_at`) so the record does not silently vanish. The known cost
stands — an `$ai` command already copied into Discord breaks — which is the argument a holding period
would answer, and none is built.

**Phase 4 — the reports question. Done — as a read, not a queue.** `image_reports` is now readable
by staff: the **Reports** tab at `/profile/moderation/reports` lists reported images, split into
those still live and those the two-report threshold already removed, with each report's reason,
reporter and time. It is deliberately read-only — nothing is assignable and the removal/restore
verbs stay on the character page — which is the distinction §1 insisted on. The open sub-question
the tab now makes answerable by inspection is whether the threshold of two is right, and which
reasons are actually used.
