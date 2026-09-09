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

Expect `001_initial.sql` and `002_rate_limits.sql`.

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
recreated from the migrations on first connection, so both `001_initial.sql` and
`002_rate_limits.sql` are applied automatically.

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

- [ ] Update `CURRENT_STATE.md` — it describes v1 in the present tense throughout.
- [ ] Close out the Phase 5 "Outstanding" items in `ROADMAP.md`.
- [ ] Remove `flask-compress` — Cloudflare does Brotli at the edge, so origin gzip
  only burns CPU. Deliberately left until after cut-over to keep one variable
  out of it.
- [ ] Decide whether `/custom_images.json` can go. Nothing in the SPA calls it any
  more; it is a ~486 KB response left in place only in case something external
  does.

