# Cut-over runbook

Moving users from v1 (DigitalOcean + Neon) to v2 (Oracle origin + Cloudflare).

`DEPLOYMENT.md` covers standing up v2 and deploying to it. This covers the one
operation that only happens once and cannot be fully undone.

---

## Read this first

**The two databases have forked.** v2's data came from a snapshot taken on the day
of the first migration. Everything added to v1 since then exists only on v1.

**The migration is insert-only.** It never deletes. So:

- Anything added on v1 since the snapshot **is picked up** by re-running it.
- Anything *deleted* on v1 since the snapshot **is not removed from v2** — it was
copied across on the first run and nothing takes it away.

That second point is the one that surprises people. Re-running the migration gives
you the **union** of both databases, not a copy of v1. If v1 has had a clean-up you
want reflected, an incremental re-run will not do it — see **Decision 2**.

**The point of no return is the first write to v2 by a real user.** Before that,
rollback costs a DNS change and nothing is lost. After it, going back to v1 strands
every upload, hide and report made on v2 in the meantime. Nothing in the system
marks this line; you have to hold it.

---

## Decisions to make before you start

These are not technical unknowns — they are choices, and they change the procedure.
Answer them now rather than at the keyboard.

### Decision 1 — is this a DNS repoint or a new address?

If v1 runs on its own custom domain, cut-over means repointing that domain and users
notice nothing. If v1 runs on a DigitalOcean-provided address, there is no DNS step:
cut-over means telling people the new URL, and ideally leaving a redirect behind.

- [ ] **Repoint an existing domain** — follow step 5a.
- [x] **New address, redirect the old one** — follow step 5b.

### Decision 2 — union, or exact copy?

- [ ] **Union (default).** Re-run the migration over the existing v2 database. Picks
  up everything added to v1; keeps anything deleted on v1 since the snapshot.
  Preserves everything already created on v2. Lowest risk.
- [x] **Exact copy of v1.** Take a final snapshot, delete the v2 database, migrate
  once into an empty schema. Reflects v1 exactly, deletions included — and
  **discards anything created directly on v2**, including test uploads and any
  identity that has already been issued.

**Chosen: exact copy.** Two consequences to hold on to. Everything created directly
on v2 goes — test uploads, and every identity issued so far, so anyone who has
already visited v2 gets a fresh pseudonym. And because it lands in an empty schema,
every image is `added_by NULL` again, which is what the note below is about.

### Decision 3 — saved bookmarks

v1's saved list was **global**: one list everyone saw. v2's is per person. Migrated
bookmarks land under a single legacy identity, so **every user's Saved page will be
empty on their first visit.**

- [x] **Accept it.** Simplest. Tell people their bookmarks reset; they re-save.
- [ ] **Seed new identities from the legacy list.** A one-time behaviour: a first
  visit copies the legacy saved list into the new identity. Needs writing, and
  means everyone starts with someone else's bookmarks — which may be wrong for a
  list that was never really "theirs".

### Also worth telling people, whichever you choose

**Nobody can remove any of the migrated images.** Every image copied from v1 has no
owner (`added_by IS NULL`), and v2's rule is that you can only remove images you
added. This is deliberate — the alternative is letting any visitor wipe the inherited
library — but it will generate questions on day one. Moderators can still remove
them, and reports still work.

### Decision 4 — the ImgChest cleanup

The cut-over is the one moment to reconcile the ImgChest account against what is
actually used and delete the rest — including griefed or otherwise inappropriate
uploads made before moderation existed. It needs a Discord export of the images in
use, a preview before anything is removed, and an explicit go-ahead. It is **built**:
`scripts/imgchest_cleanup.py` plus an owner-only Cut-over tab — see
**[ImgChest cleanup](#imgchest-cleanup-planned)**.

- [ ] **Run the cleanup with the cut-over.**
- [ ] **Skip it, and leave ImgChest as it is.**

Note the interaction with Decision 2: the cleanup's "on the site" set is the
*database after the import*, so an **exact copy** makes v2-only uploads deletable
(unless they are in use), while a **union** keeps them.

---

## Pre-flight

Every one of these is a gate. Do not proceed past a failure.

```bash
ssh <origin-box>
```

**1.** `SECRET_KEY` **is set and backed up.**

```bash
sudo grep -c '^SECRET_KEY=' /etc/imgmanager/secrets.env    # must print 1
```

The backend now refuses to start without it. It signs identity cookies, so if it
ever changes, every user silently becomes a new person and loses their uploads.
Confirm you have a copy somewhere other than this machine.

**2. The service is healthy and on the expected revision.**

```bash
systemctl is-active imgmanager
curl -s https://api.<domain>/api/health
```

**3. Migrations are applied.**

```bash
sudo -u imgmanager sqlite3 /var/lib/imgmanager/imgmanager.db \
  "SELECT name FROM schema_migrations ORDER BY name;"
```

Expect all twenty, `001_initial.sql` through `020_permanent_delete.sql`.

**4. A Litestream restore actually works.**

This is the important one. After decommissioning, this box holds the only copy of
the data, and an untested backup is not a backup.

```bash
sudo systemctl stop imgmanager
sudo -u imgmanager litestream restore -config /etc/litestream.yml \
     -o /var/lib/imgmanager/restored.db /var/lib/imgmanager/imgmanager.db
sqlite3 /var/lib/imgmanager/restored.db "SELECT COUNT(*) FROM custom_images;"
sudo rm /var/lib/imgmanager/restored.db
sudo systemctl start imgmanager
```

The count must match the live database. If the restore is empty or errors, **stop** —
Litestream is not replicating and cut-over would leave you with no backup at all.

**5. Pause auto-deploys for the duration.**

A deploy landing mid-cut-over is an unnecessary variable.

```bash
sudo systemctl stop imgmanager-update.timer
```

---

## Procedure

### 1. Freeze writes on v1

Whatever form this takes for you — a maintenance notice, or simply doing this at a
quiet hour and accepting a few minutes of divergence. The window between the final
snapshot and DNS switching is the only period where v1 writes are lost.

Record the time you froze. Anything added to v1 after this is not coming across.

### 2. Take the final snapshot

Read-only; the script opens the connection in read-only mode so the server itself
rejects writes.

```bash
# On a machine with DATABASE_URL for Neon in .env
uv run python scripts/export_neon_snapshot.py --out snapshot-final
```

### 3. Migrate — exact copy (Decision 2)

Keep a copy of the current database first. This is the step that discards v2-only
data, so it is the one you might want to walk back.

```bash
sudo systemctl stop imgmanager
sudo -u imgmanager cp /var/lib/imgmanager/imgmanager.db \
  /var/lib/imgmanager/pre-cutover-$(date +%F).db
sudo -u imgmanager rm /var/lib/imgmanager/imgmanager.db*
sudo -u imgmanager DATABASE_PATH=/var/lib/imgmanager/imgmanager.db \
  uv run python scripts/migrate_v1_to_sqlite.py --snapshot snapshot-final/
```

The script reports what it did and verifies its own image count. The schema is
recreated from the migrations on first connection, so all twenty — `001_initial.sql`
through `020_permanent_delete.sql` — are applied automatically.

> **The dump is only the v1 half.** It carries names, image URLs and bookmarks; every
> other column and table is either *derived* or a v2-era feature with no v1 source.
> Migrations build the schema in full, so the imported database is structurally
> complete and semantically thin. The rebuild is its own section below — see
> **[After the import](#after-the-import-the-derived-layers)** — and it is where the
> thumbnail cache, in particular, must be dealt with.

```bash
sudo systemctl start imgmanager
```

> Had you chosen **union** instead, this whole step would have been a single
> `migrate_v1_to_sqlite.py --snapshot snapshot-final/` against the existing
> database, with no deletion.

### 4. Verify before anyone sees it

```bash
curl -s https://api.<domain>/api/stats
```

Characters and image counts must **match** the snapshot exactly — an exact copy
means exactly, so a mismatch here is a failed migration, not a rounding difference.
Then, in a browser:

- [ ] Home page loads and shows sensible counts.
- [ ] Browse Customs paginates, searches by name and by series, and sorts.
- [ ] A character page loads its gallery; images render from ImgChest.
- [ ] Upload an image. It appears, and is attributed to you.
- [ ] Remove that image. It goes, and appears in the Removed drawer.
- [ ] Restore it from the drawer.
- [ ] Hide someone else's image; confirm it disappears and "Show 1 hidden" appears.
- [ ] Copy an `$ai` command and paste it into Discord. **This is the one that
  matters** — it is the entire purpose of the app.
- [ ] Reload. Your handle in the navbar is unchanged (proves `SECRET_KEY` is stable).

### 5. Announce the new address (Decision 1)

There is no DNS step: v2 already lives on its own domain. Cut-over here means
telling people the new URL and leaving a redirect behind on the v1 app so old links
and bookmarks still land somewhere useful.

Do not delete the v1 app when you do this — the redirect needs it, and so does
rollback.

Check the new address from a device that has never visited it — a phone on mobile
data is the easiest clean cache.

> Had v1 been on its own custom domain, this would instead have been a DNS repoint
> in Cloudflare with a low TTL for the day, and users would have noticed nothing.

### 6. Watch

```bash
sudo journalctl -u imgmanager -f
```

Look for 500s, and for `[RATELIMIT]` lines — a burst of those on day one means a
limit is set too low for real use, not that someone is attacking you. Limits are
overridable per action in `/etc/imgmanager/secrets.env`, e.g.
`RATE_LIMIT_UPLOAD="60/60,600/3600"`, then `sudo systemctl restart imgmanager`.

### 7. Re-enable auto-deploys

```bash
sudo systemctl start imgmanager-update.timer
```

---

## After the import: the derived layers

The v1 snapshot holds only names, the flat list of image URLs per name, the global
bookmarks and the timestamps. Everything else v2 stores was either *derived* from
those or is a v2-era feature with no v1 source. Migrations build the schema in full,
so the imported database is structurally complete and semantically thin; the steps
below refill it. None is needed for the site to *serve*, but several are what keep it
pleasant.

**The one that must happen, not can: the thumbnail cache.** Thumbnails are keyed by
`custom_images.id` and live on the box (`THUMB_DIR`) — not in the database. A fresh
import reassigns ids, so any file that survives is keyed to the *wrong* row and would
show the wrong image, which is worse than a miss. **Clear `THUMB_DIR`.** They
regenerate lazily on first view, by design (a batch would pull ~16 GB out of ImgChest
in one go); expect a fetch spike as people browse, cached at the edge after the first
hit. There is no pre-generation step, and none should be added. Each one is mirrored
to R2 as it is generated (`thumb_key`, migration 021), so the import also resets that
column; the bucket objects left over from before are keyed by the old ids and content
hash, so nothing points at them and they can be swept whenever convenient.

Then, roughly in this order. Steps 3 and 4 are the ones that re-read the image bytes
from ImgChest, so they must come **before** the cleanup in step 5:

1. **Catalog — re-import the Mudae extracts.** `character_catalog` is a v2 table and
   is empty. It restores search and autocomplete, and it is the source for traits and
   portrait mirroring.
2. **Portraits — repoint or re-mirror.** The dump has no `main_image_thumb`, so every
   row would hotlink `mudae.net`. If R2's portraits survived the wipe, run the mirror
   script in resync mode: no fetch, just re-point rows at objects that already exist.
   If R2 was emptied too, run the full mirror (fetch, encode WebP, upload under
   `portraits/`, record the key). The API process also needs its own rclone config, for
   the in-request "update main from Mudae" flow.
3. **Content fingerprints — run the backfill.** `content_hash` is the duplicate
   fingerprint; a fresh import leaves it NULL, so the add-time gate cannot see any of the
   imported images and the moderator Duplicates review is empty. The script downloads
   each image once and hashes it — the library is thousands of images, so expect it to be
   slow and to move real bandwidth. **Before the cleanup: deleted files cannot be
   hashed.**
4. **Image dimensions — run the backfill.** Headers only, ~8.5k images, resumable.
   Without it the gallery reflows on load (the browser falls back to measuring), so it
   is visible rather than breaking. **Before the cleanup, for the same reason.**
5. **ImgChest cleanup — preview, review, then execute.** One rate-limited listing pass,
   and it stores `imgchest_post_id` for everything that survives, which is what permanent
   delete needs. This replaces the separate post-id backfill: the two compute the same
   file-to-post map, so there is no reason to walk the account twice. The order here is
   the whole point — see [ImgChest cleanup](#imgchest-cleanup-planned).
6. **Accents — rebuild.** Lost with the column. Recomputed on visit, but the backfill
   script walks the library once — and it measures *only from thumbnails already on
   disk*, so run it after the thumbnail cache has warmed, or accept partial accents
   that upgrade on the first visit. Overrides made on v2 before the wipe are gone with
   everything else v2-only. Independent of the cleanup.
7. **Traits — run after the catalog.** Gender and pool badges. Cosmetic.

Config that must match rather than data: `CORS_ORIGINS` on the origin and
`VITE_API_BASE_URL` / `VITE_IMAGE_BASE_URL` in the Pages build. Portrait keys are
host-relative, so nothing in the database changes if the domains stay the same.

Naturally empty, and correct that way: takes, views, hidden, reports, notifications,
moderation actions/status/networks, rate-limit counters, and per-identity saved. These
are v2-era features with no v1 source, so the moderation surface starts on a clean
slate.

---

## ImgChest cleanup (planned)

Every image this app ever uploaded is still live on ImgChest — nothing was ever
deleted (that was v1's constraint, kept in v2). That includes images no longer in any
database, and griefed or otherwise inappropriate uploads made before moderation
existed. The cut-over is the one moment to reconcile the account against what is
actually used, and to remove the rest.

**This is planned, not built.** `scripts/` will gain a one-off cleanup, and it is
deliberately gated.

**The input is ground truth from Discord.** The operator will export the list of every
image currently used in the servers — the URLs actually named in Mudae's `$ai` lists.
The cleanup then treats two sets as keepers:

- **In use** — present in that Discord export.
- **On the site** — present in the imported `custom_images`, in any state.

Every ImgChest object in **neither** set is a candidate for permanent deletion. That is
what clears the griefed uploads: they are not in use and (if the exact-copy import is
chosen) not in the database, so nothing keeps them.

**The preview is the gate.** Before anything is deleted the script prints two lists for
review:

- **Will stay, but is not on the app** — in-use images the database does not have.
  This is where the *wrongfully removed* surface: images a user, a report or a moderator
  removed, but that are still in play in Discord. The operator confirms the list is real
  user content and nothing surprising.
- **Will be permanently deleted** — everything in neither set.

Nothing is deleted until the operator has seen both lists and given an explicit
go-ahead. The preview is also the pause point: if either list looks wrong, stop and
change the keep set — rescue an image by adding it — before running again. The script
must be rate-limit aware (60/min), resumable, and safe to re-run.

**Repointing what was wrongfully removed.** Deleting is only half of it. The in-use
images the site does not have are re-added to `custom_images`, in the `removed` state,
so they appear in the Removed drawer and can be restored — the point being that people
who want an image removed in error get it back at migration time rather than losing it.
They land as ordinary migrated rows, which means `added_by IS NULL` like everything
else from v1: **staff restore them, not the original uploader.** If that is not good
enough, the alternative is to seed ownership from the Discord export — possible only
where the export names who ran the command.

**Two constraints to design around.** Mudae accepts only ImgChest and Imgur URLs, so
only images on our own ImgChest account can be re-added; an in-use URL from anywhere
else can be kept but not represented as ours. And ImgChest deletes by *post*, while a
post's listing exposes only its *first* image's file id — so the cleanup plans per post
(keep a post if any of its images is a keeper, delete the rest file-by-file) and must
surface any hand-merged multi-image post the preview cannot fully resolve.

### The decisions this is built on

- **Preview in the app, destructive half in the script.** `scripts/imgchest_cleanup.py`
  writes a preview JSON; a new **owner-only** Cut-over tab in the staff area renders it.
  The app is read-only — it never deletes. Deletion and re-add need `--execute`.
- **Owner-only, not staff.** The preview is appended to the moderation surface but
  guarded by `require_owner` rather than `require_moderator`; plain moderators do not
  see the tab or the endpoint. This is operator work, not routine moderation.
- **Flat lists with counts.** The preview shows two flat lists — *will be permanently
  deleted*, and *will be recovered into Removed* — each with a count, plus totals and a
  warnings section. Per-character grouping was considered and dropped: the operator is
  scanning for surprises, not navigating by character.
- **The export is `Name - URL`, one per line, and it repeats.** Pulling from several
  servers means the same URL appears under different names. The cleanup **dedups by URL**
  (first name wins) and reports malformed lines instead of dropping them silently.
- **A limit first.** Before the real run, do a `--limit N` execute against a small slice
  to confirm deletion and re-add behave, then run the whole thing. `--limit` caps
  deletions, not the preview.
- **Ordering is load-bearing.** Content fingerprints and image dimensions re-read the
  bytes from ImgChest and must run **before** the cleanup. See
  [After the import](#after-the-import-the-derived-layers) step order below.

The step order changes to the following, and the reason is that the cleanup deletes
files the earlier backfills still need to read:

1. Import, warm thumbnails.
2. Catalog, portraits, traits (Mudae-side; independent of ImgChest files).
3. **Content fingerprints** — downloads each image; must see the files before they go.
4. **Image dimensions** — headers only; same reason.
5. **ImgChest cleanup** — preview, review, `--limit` trial, then execute. This also
   fills `imgchest_post_id` for what survives, so `backfill_imgchest_post_ids.py` is no
   longer a separate step.
6. **Accents** — from local thumbnails, after the cache has warmed.

---

## Rollback

**Before the first real user write to v2:** revert the DNS change (5a) or the
announcement (5b). Nothing is lost. v1 is untouched and still holds everything.

**After the first real user write:** you are now choosing between two divergent
datasets, and there is no merge tool. Going back to v1 discards everything done on
v2 since cut-over. Prefer fixing forward.

The practical consequence: **do not decommission anything until you are past the
point where rollback is plausible.**

---

## Decommission

Only after a soak period during which people have actually used v2 — a week is a
reasonable default, and it is the last moment the v1 data exists anywhere.

1. Take a final `pg_dump` of Neon and keep it somewhere off both platforms.
2. Confirm Litestream has been replicating throughout the soak (check the R2 bucket's
  most recent object).
3. Delete the DigitalOcean app.
4. Delete the Neon database.
5. Cancel anything still billing.

After step 4, the origin box plus its Litestream replica are the only copies of the
data that has ever existed. That is the reason pre-flight step 4 is a gate.

---

## Afterwards

- [ ] **Rebuild the derived layers** — catalog, portrait mirrors, thumbnail cache,
  content fingerprints, dimensions, accents, traits, and (for what survives) ImgChest
  post ids. See [After the import](#after-the-import-the-derived-layers) for the order,
  which puts fingerprints and dimensions before the cleanup.
- [ ] **Reconcile ImgChest** — generate the preview, review it in the owner-only
  Cut-over tab, run a `--limit` trial, then execute, if Decision 4 was to proceed. See
  [ImgChest cleanup](#imgchest-cleanup-planned).
- [ ] Update `CURRENT_STATE.md` — it describes v1 in the present tense throughout.
- [ ] Close out the Phase 5 "Outstanding" items in `ROADMAP.md`.
- [x] Remove `flask-compress` — done ahead of the cut-over in `5c62b9c`, once
  Cloudflare was in front and confirmed to be compressing. The edge does Brotli,
  which beats gzip.
- [x] Remove `/custom_images.json` — done. Nothing in the SPA called it any more,
  and the ~486 KB endpoint has been deleted rather than left as a superseded stub.

