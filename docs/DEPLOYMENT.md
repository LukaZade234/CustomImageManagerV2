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

## Order

Do it in this order. An earlier draft put the Tunnel before the origin box, which
cannot work: the Tunnel step tells you to check `/api/health` responds, and
nothing responds until the app is running.

1. R2 buckets and images
2. The origin box, with the app serving on `localhost:8080`
3. The Tunnel in front of it
4. Load the data
5. Pages, and the CORS flip

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

See **[CUTOVER.md](CUTOVER.md)** — it is the only operation here that happens once
and cannot be fully undone, so it has its own runbook with the pre-flight gates, the
rollback boundary, and the three decisions it forces.

In outline: freeze v1 writes, take a final snapshot, re-run the migration, verify,
switch, soak, and only then delete the DigitalOcean app and the Neon database.

---

## Deploying changes

The two halves update differently, and the asymmetry catches people out.

**Frontend — automatic.** Push to `main` and Cloudflare Pages rebuilds and deploys
in roughly one to three minutes. Nothing to do.

**Backend — needs a pull.** Pushing to GitHub does nothing to the origin box on its
own.

If a change spans both halves, **update the backend first** and let Pages catch up.
Otherwise a new frontend briefly talks to an old API, which produces confusing
errors rather than an obvious failure.

### Automatic backend deploys

`deploy/update.sh` plus a systemd timer polls GitHub every two minutes and deploys
new commits on `main`.

**Polling rather than a webhook or GitHub Actions, deliberately.** The VM has no
inbound ports open — the Tunnel only dials out — and that is worth preserving. A
webhook would need an endpoint exposed and a shared secret; Actions would need SSH
reachable. Polling needs neither, stores no credentials on GitHub, and cannot be
triggered by anyone else. The cost is up to two minutes of latency, which roughly
matches the Pages build anyway.

The script is written to be safe unattended:

- **exits silently when there is nothing new**, so the journal stays readable
- **`flock`** prevents two deploys overlapping if a run takes longer than the timer
- **only runs `uv sync` when `uv.lock` actually changed**, so most deploys are a
  pull and a restart
- **`--ff-only`**, so a diverged working tree stops the deploy rather than being
  silently destroyed
- **health-checks after restarting, and rolls back to the previous commit if the
  new one does not serve traffic.** A bad push costs a few seconds of downtime
  instead of leaving the site broken until somebody notices

Install:

```bash
sudo cp /opt/imgmanager/deploy/imgmanager-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now imgmanager-update.timer
systemctl list-timers imgmanager-update --no-pager
```

Watch it work:

```bash
journalctl -u imgmanager-update -f
sudo /opt/imgmanager/deploy/update.sh      # force a check immediately
```

To pause automatic deploys while doing something delicate:

```bash
sudo systemctl stop imgmanager-update.timer
```

---

## Origin hygiene

One command tells you exactly what the internet can talk to:

```bash
sudo ss -tlnp
```

The expected state, and nothing else:

| Port | Process | Exposure |
|---|---|---|
| `127.0.0.1:8080` | gunicorn | loopback only |
| `127.0.0.1:20241` | cloudflared metrics | loopback only |
| `127.0.0.53:53` | systemd-resolved | loopback only |
| `0.0.0.0:22` | sshd | the only thing reachable |

**gunicorn must be on `127.0.0.1`, never `0.0.0.0`.** `cloudflared` connects from
the same machine, so binding wider buys nothing — and traffic arriving directly
would bypass Cloudflare entirely: no edge cache, no DDoS protection, and the
origin address discoverable by a port scan. This was wrong on the first
deployment and only found by running the command above.

**Purge `rpcbind` if present.** Some Ubuntu cloud images ship it listening on
`0.0.0.0:111`. It is NFS plumbing, unused here, and a known amplification vector:

```bash
sudo systemctl disable --now rpcbind rpcbind.socket
sudo apt purge -y rpcbind
```

**Enable unattended security updates**, since the design goal is never needing to
SSH in:

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

Worth re-running `ss -tlnp` after any significant change to the box. It is the
cheapest security check available and the site works identically whether or not
you get this right — the difference only appears the day a firewall rule changes
by accident.

---

## Things that actually went wrong the first time

Collected from doing this for real. None are in Oracle's or Cloudflare's docs.

**Oracle: the ARM shape is hidden two clicks deep.** *Image and shape → Edit →
Change shape → **Ampere** tab*. The default tab is AMD, and the free AMD shape
(`E2.1.Micro`, 1 GB) is not worth having.

**Oracle: "out of host capacity" is normal**, not a mistake you made. Free ARM is
heavily oversubscribed, London especially. Retry, try other availability domains,
and ask for less — 1 OCPU / 6 GB fills far more easily than 4 / 24 and is still
more than this app needs. Upgrading to Pay As You Go improves the odds
substantially; you keep the Always Free allowance.

**Oracle: the instance may get no public IP.** If the details page shows only a
private address, the VNIC was created without one. Fix it on the *instance's*
VNIC — Compute → Instances → your instance → Attached VNICs → the VNIC → IPv4
Addresses → ⋮ → Edit → Public IP Type: Ephemeral.

**Oracle: VCN and VNIC are different things** and the console does nothing to help.
A **VCN** is the network; a **VNIC** is the adapter on your instance. If you name
your VCN something like "…VNIC" you will lose a lot of time. The public IP setting
is only reachable via the instance, never via the network.

**Oracle: the Cloud Shell is the escape hatch.** The `>_` icon in the top bar gives
a browser terminal with the OCI CLI already authenticated, which is often faster
than hunting through menus.

**rclone must be recent.** Ubuntu's packaged version is too old for `key=value`
config syntax and rejects `--s3-no-check-bucket`. Install the current one:
`curl https://rclone.org/install.sh | sudo bash`.

**`rclone lsd r2:` returning 403 is correct.** Listing all buckets is an
account-level operation, and the token is deliberately scoped to two buckets. Test
with `rclone ls r2:imgmanager-assets` instead. This is also why the upload script
passes `--s3-no-check-bucket`.

**Cloudflare now steers you to Workers, not Pages.** If the create flow asks for a
"Deploy command" (`npx wrangler deploy`) you are in the Workers flow, which needs a
`wrangler.jsonc` in the repo. For Pages, look for the **Pages tab** on the create
screen. Both are free and equivalent for a static SPA.

**Pages needs `NODE_VERSION=22`.** Vite 8 requires Node 20.19+/22.12+, and the
default build image is often older. The failure does not obviously point at Node.

**The apex custom domain will hang on "Verifying"** if the imported parking
`A`/`AAAA` records still exist — DNS forbids a CNAME alongside A records on the
same name, and Cloudflare will not delete your records for you. Remove the `@`
parking records, then add `CNAME @ → <project>.pages.dev`, **proxied** (the orange
cloud is what makes an apex CNAME legal, via flattening). Leave the `api` and
`images` records alone.

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
| `DISCORD_USER_TOKEN` / `DISCORD_CHANNEL_ID` | origin | no | Mudae import (a **self-bot user token**) |
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | origin | no | Sign-in (an **OAuth app**, unrelated to the above) |
| `DISCORD_REDIRECT_URI` | origin | with sign-in | Must match Discord exactly. Not derived: behind the Tunnel the app sees `localhost:8080` |
| `OWNER_DISCORD_ID` | origin | no | Grants the owner role at login |
| `FRONTEND_URL` | origin | no | Where to send the browser after sign-in. Defaults to the first `CORS_ORIGINS` entry |
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
