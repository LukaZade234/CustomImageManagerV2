# Deployment

Replaces the DigitalOcean instructions. Rationale for this shape is in
`DECISIONS.md` §3 and §8; what is still outstanding is in `ROADMAP.md` Phase 5.

## What runs where

```
  browser
    |
    +-- SPA .................. Cloudflare Pages        (free, global edge)
    +-- character images ..... Cloudflare R2           (free egress)
    +-- custom images ........ ImgChest                (mandatory, see DECISIONS §2)
    |
    +-- /api/* ............... Cloudflare Tunnel --> origin box
                                                          |
                                                   gunicorn (gthread)
                                                          |
                                                   SQLite file
                                                          |
                                                   litestream --> R2
```

Only small JSON crosses the ocean. The SPA and every image come from Cloudflare's
edge, which is what makes a single self-hosted origin acceptable for users
overseas.

**Nothing here costs money.** Cloudflare Pages, R2 (10 GB, free egress), and
Tunnel are all free tiers, and the origin is either a free Oracle Cloud VM or a
machine you already own.

## Before you start

- A domain on Cloudflare (nameservers pointed at them).
- An origin box. Either works, and the Tunnel makes them interchangeable later:
  - **Oracle Cloud Always Free** — 4 ARM cores / 24 GB, always on, free
    permanently. Pick a region central to your users.
  - **A home server** — free and fully yours; uptime is your power and internet.
- The v1 database exported (`kv_store.sql`), and the v1 site still running until
  cut-over.

---

## 1. Cloudflare: R2

1. **R2 → Create bucket**, e.g. `imgmanager-assets`.
2. Settings → **Connect custom domain** → `images.<yourdomain>`. This is what
   makes objects publicly readable over HTTPS from the edge.
3. **Manage R2 API Tokens** → create a token with **Object Read & Write**. Keep
   the access key id and secret; Litestream needs them too.
4. Upload the default character images:

   ```bash
   R2_BUCKET=imgmanager-assets ./deploy/upload-character-images-to-r2.sh
   curl -I https://images.<yourdomain>/character_images/Zero_Two.png   # expect 200
   ```

5. **Create a second bucket for backups**, e.g. `imgmanager-backups`. Keep it
   private — it holds your whole database.

## 2. Cloudflare: Tunnel to the origin

On the origin box:

```bash
cloudflared tunnel login
cloudflared tunnel create imgmanager
cloudflared tunnel route dns imgmanager api.<yourdomain>
```

Copy `deploy/cloudflared-config.yml` to `/etc/cloudflared/config.yml`, fill in the
tunnel UUID and hostname, then `sudo cloudflared service install`.

Check `https://api.<yourdomain>/api/health` returns `{"status":"ok"}` before going
further.

## 3. The origin box

```bash
sudo useradd --system --home /opt/imgmanager imgmanager
sudo mkdir -p /opt/imgmanager /var/lib/imgmanager /etc/imgmanager
sudo chown imgmanager:imgmanager /var/lib/imgmanager

# Code and dependencies
sudo -u imgmanager git clone <your-repo> /opt/imgmanager
cd /opt/imgmanager && sudo -u imgmanager uv sync --locked --no-dev
```

Install Litestream, then copy `deploy/litestream.yml` to `/etc/litestream.yml` and
fill in the R2 credentials and **backup** bucket.

Secrets go in `/etc/imgmanager/secrets.env` (mode `600`, owned by `imgmanager`):

```env
SECRET_KEY=<long random string, see below>
IMGCHEST_API_KEY=<from imgchest.com>
DISCORD_USER_TOKEN=<optional, see Mudae below>
DISCORD_CHANNEL_ID=<optional>
```

> **`SECRET_KEY` must be stable and must never change.** It signs the identity
> cookies. Rotating it silently turns every visitor into a new person, losing
> their hidden-image lists and their ability to remove their own uploads.
> Generate once with `python -c "import secrets; print(secrets.token_urlsafe(64))"`
> and back it up somewhere other than this machine.

Then install the service:

```bash
sudo cp deploy/imgmanager.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now imgmanager
sudo systemctl status imgmanager
```

## 4. Load the data

```bash
# On a machine with access to the v1 database (read-only, safe):
uv run python scripts/export_neon_snapshot.py

# On the origin box:
sudo -u imgmanager DATABASE_PATH=/var/lib/imgmanager/imgmanager.db \
  uv run python scripts/migrate_v1_to_sqlite.py --dump kv_store.sql
```

The script reports what it did and verifies its own image count. It is idempotent,
so re-running to pick up late changes before cut-over is safe.

## 5. Cloudflare: Pages

1. **Workers & Pages → Create → Pages → Connect to Git**, choose this repository.
2. Build settings:
   - Build command: `npm ci && npm run build`
   - Output directory: `frontend/dist`
   - Root directory: `frontend`
3. Environment variables (**Production**):

   ```
   VITE_API_BASE_URL   = https://api.<yourdomain>
   VITE_IMAGE_BASE_URL = https://images.<yourdomain>
   ```

   These are inlined into the bundle at build time, so changing them needs a
   rebuild, and nothing secret may go here.
4. Add your custom domain to the Pages project.
5. Set `CORS_ORIGINS` on the origin to that exact domain and restart:

   ```
   CORS_ORIGINS=https://<yourdomain>
   ```

   The API **refuses to start** with `CORS_ORIGINS=*`, because it sends
   credentials and browsers reject credentialed requests against a wildcard.

## 6. Cut over, then decommission

1. Point DNS at Pages, confirm the site works end to end — add an image, reorder,
   download, copy an `$ai` command.
2. Re-run the migration to catch anything added to v1 in the meantime.
3. **Verify a restore works before trusting it** (see below).
4. Only then delete the DigitalOcean app and the Neon database.

---

## Restoring from backup

Test this *before* you need it. An untested backup is not a backup.

```bash
sudo systemctl stop imgmanager
sudo -u imgmanager litestream restore -config /etc/litestream.yml \
     -o /var/lib/imgmanager/restored.db /var/lib/imgmanager/imgmanager.db
sqlite3 /var/lib/imgmanager/restored.db "SELECT COUNT(*) FROM custom_images;"
# looks right? swap it in and start again
```

## Environment variables

| Variable | Where | Required | Notes |
|---|---|---|---|
| `SECRET_KEY` | origin | **yes** | Signs identity cookies. Stable forever. |
| `IMGCHEST_API_KEY` | origin | yes | Uploads |
| `DATABASE_PATH` | origin | yes | `/var/lib/imgmanager/imgmanager.db` |
| `CORS_ORIGINS` | origin | yes | Exact Pages origin. `*` is refused. |
| `PORT` | origin | no | Default 8080 |
| `WEB_WORKERS` / `WEB_THREADS` / `WEB_TIMEOUT` | origin | no | See `gunicorn.conf.py` |
| `DISCORD_USER_TOKEN` / `DISCORD_CHANNEL_ID` | origin | no | Mudae import |
| `VITE_API_BASE_URL` | Pages | yes | Build-time |
| `VITE_IMAGE_BASE_URL` | Pages | yes | Build-time |

## Mudae import (optional)

Enables **Add Character** lookup, bulk series import, and **Update main from
Mudae**. The app runs `$im` / `$ima` in a Discord channel you configure.

1. Pick a Discord server where Mudae is installed and you can run commands. Use a
   dedicated channel, e.g. `#mudae-imports`.
2. Confirm Mudae works there — type `$im Rem` and check you get a character card.
3. Enable **Developer Mode** in Discord (Settings → Advanced), right-click the
   channel → **Copy Channel ID** → set `DISCORD_CHANNEL_ID`.
4. While logged into Discord in a browser, open DevTools → **Network**, reload,
   pick any `discord.com/api` request, and copy the **Authorization** header value
   into `DISCORD_USER_TOKEN` (the value only — no `Bearer` prefix).
5. Keep it secret; never commit it.

> Automating a user account may violate Discord's Terms of Service, and the
> account can be banned. This is an authoring convenience, not part of the serving
> path — see `DECISIONS.md` §8.

## Local development

Unchanged, and unaffected by any of the above: leave `VITE_API_BASE_URL` and
`VITE_IMAGE_BASE_URL` unset and the Vite dev server proxies to Flask, so
everything stays same-origin. See `DEVELOPMENT.md`.
