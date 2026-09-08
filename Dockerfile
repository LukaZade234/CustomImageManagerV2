# ---- Frontend build ----
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# npm ci installs exactly what the lockfile says; npm install may drift.
RUN npm ci
COPY frontend/ ./
RUN npm run build && test -f dist/index.html

# ---- Python app ----
FROM python:3.13-slim

# uv installs from uv.lock, so the image gets byte-identical dependencies
# to local development. Pinned so the builder itself is reproducible too.
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Dependencies first, as their own layer: they change far less often than app
# code, so edits to the source do not invalidate the dependency install.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN test -f frontend/dist/index.html

ENV PORT=8080
EXPOSE 8080

# Settings live in gunicorn.conf.py, which explains why each is what it is.
# Tunable at runtime via WEB_WORKERS / WEB_THREADS / WEB_TIMEOUT.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
