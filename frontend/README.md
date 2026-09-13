# ImgManager Frontend (React + Vite)

## Setup

```bash
cd frontend
npm ci                       # install from package-lock.json, exactly
```

## Development

```bash
npm run dev
```

Runs at http://localhost:3000 with the API proxied to Flask on
http://localhost:5000. Leave `VITE_API_BASE_URL` and `VITE_IMAGE_BASE_URL`
unset so everything stays same-origin; see `docs/DEVELOPMENT.md`.

## Tests

```bash
npm test                     # vitest, single run
npm run test:watch
npm run test:coverage
```

## Quality gates

```bash
npm run lint                 # biome
npm run format               # biome, writes
npm run typecheck            # tsc --noEmit
npm run build
```

## Build

```bash
npm run build
```

Outputs to `frontend/dist/`. **`dist/` is not committed** — the old
DigitalOcean buildpack needed it checked in, and that constraint is gone.

## Deploy

The frontend is a static SPA on **Cloudflare Pages**, which builds from git.
`docs/DEPLOYMENT.md` is the authority; in short:

- Build command `npm ci && npm run build`, output `frontend/dist`, root
  directory `frontend`.
- Set `VITE_API_BASE_URL` and `VITE_IMAGE_BASE_URL` as Pages environment
  variables. Both are inlined at build time, so changing one needs a rebuild,
  and nothing secret may go in them.
- Push to `main` and Pages redeploys in a minute or two. Also set
  `NODE_VERSION=22`, which Vite 8 requires.
