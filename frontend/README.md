# ImgManager Frontend (React)

## Setup

```bash
cd frontend
npm install
```

## Development

```bash
npm run dev
```

Runs at http://localhost:3000 with API proxy to http://localhost:5000.

## Build

```bash
npm run build
```

Outputs to `frontend/dist/`. Flask serves the SPA from here.

## Deploy

Before deploying, run `npm run build` in the frontend directory. Commit the `dist/` folder, or configure your platform to build the frontend (e.g. add a build step that runs `cd frontend && npm ci && npm run build`).
