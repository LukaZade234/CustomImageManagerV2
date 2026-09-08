# Deploying to DigitalOcean App Platform

## Step 1: Push to GitHub

```bash
git add .
git commit -m "Deploy"
git push origin main
```

(Use your actual branch name if different.)

## Step 2: Create the App

1. Go to [cloud.digitalocean.com/apps](https://cloud.digitalocean.com/apps)
2. Click **Create App**
3. Choose **GitHub** (or GitLab/Bitbucket) and authorize if needed
4. Select this repository and branch
5. DigitalOcean will detect the app from `.do/app.yaml`

## Step 3: Configure Environment Variables

In the app’s **Settings** → **App-Level Environment Variables**, add:

| Variable | Type | Required | Notes |
|----------|------|----------|-------|
| **IMGCHEST_API_KEY** | Secret | Yes | From [imgchest.com](https://imgchest.com) → Account → API |
| **DATABASE_URL** | Secret | For persistence | Neon PostgreSQL connection string |
| **SECRET_KEY** | Secret | No | For future auth; optional |
| **CORS_ORIGINS** | Plain | No | Comma-separated origins; default allows all |
| **DISCORD_USER_TOKEN** | Secret | For Mudae import | Discord account token for the Mudae channel (see setup below). Keep secret. |
| **DISCORD_CHANNEL_ID** | Plain | For Mudae import | Channel where Mudae commands are sent |
| **MUDAE_BOT_USER_ID** | Plain | No | Usually leave unset (defaults to official Mudae) |

### Mudae import (optional)

Enables **Add Character** lookup, bulk series import, and **Update main from Mudae** on character pages. The app runs `$im` / `$ima` in your configured Discord channel.

1. Pick a Discord server where Mudae is installed and you can run commands. Use a dedicated channel (e.g. `#mudae-imports`).
2. Confirm Mudae works there — type `$im Rem` and verify you get a character card.
3. Enable **Developer Mode** in Discord (Settings → Advanced), right‑click the channel → **Copy Channel ID** → set `DISCORD_CHANNEL_ID`.
4. In your browser while logged into Discord, open DevTools → **Network**, reload Discord, pick any `discord.com/api` request, and copy the **Authorization** header value into `DISCORD_USER_TOKEN` (value only — do not add `Bearer`).
5. Keep that value secret; never commit it to git.

For local development, add the same variables to a `.env` file in the project root, then run:

```bash
python upload_imgchest.py --web
```

**Note:** Automating a Discord user account may violate Discord’s Terms of Service. Use at your own risk.

## Step 4: Frontend

The app uses the React SPA. The Dockerfile builds it during deploy. No extra config needed.

**Health check:** `GET /api/health` returns `{"status":"ok","service":"imgmanager"}` — use for uptime probes (not a full DB check).

## Step 5: Database Setup (if using DATABASE_URL)

After the first deploy with `DATABASE_URL` set:

1. Open the app’s **Console** (or run a one-off job)
2. Run:
   ```bash
   python scripts/migrate_to_db.py
   python scripts/import_characters_to_db.py
   ```
3. Or run locally with `DATABASE_URL` set, then redeploy

## Step 6: Launch

Click **Create Resources** or **Deploy** and wait for the build to finish.

## Faster loads for users far from the server (CDN)

The app runs in **one region** (e.g. London). Every API call pays full round-trip time to that region, which is noticeable for friends overseas.

**What the app already does after deploy:**

- **Gzip** on JSON and text responses (`flask-compress`).
- **Long cache** on hashed JS/CSS under `/assets/` (Vite filenames include a content hash).
- **No long cache** on the HTML shell so new deploys are picked up.
- **Parallel fetches** where possible in the client (e.g. saved list + last-updated).

**Biggest win for global users:** put a **CDN** in front of your domain (e.g. [Cloudflare](https://www.cloudflare.com/) free tier): proxy orange cloud, SSL, and cache **static** files. Point DNS at Cloudflare, then to your App Platform URL. That moves JS/CSS (and often the first HTML request) closer to the user. **API calls** (`/api/*`, `/custom_images.json`) still hit your origin unless you configure caching carefully—**do not** cache authenticated or user-specific JSON without understanding the tradeoffs.

**Other options:** deploy the App Platform component in a **region closer to most users** (Settings → region), or accept higher latency for API-heavy pages until you add a lighter API or edge caching for public read-only data.

## Running Locally

**Production build:**
```bash
cd frontend && npm install && npm run build
cd .. && IMGCHEST_API_KEY=your_key python upload_imgchest.py --web
```
Open http://localhost:5000

**Dev (hot reload):**
```bash
# Terminal 1: Flask API
IMGCHEST_API_KEY=your_key python upload_imgchest.py --web

# Terminal 2: React dev server (proxies API to :5000)
cd frontend && npm install && npm run dev
```
Open http://localhost:3000
