"""Serving the built React app.

The SPA lives in frontend/dist, built by a GitHub Action and committed to the
repo. Every client-side route has to be listed here rather than caught by a
wildcard: a catch-all would swallow unknown /api paths and answer them with
HTML, which turns a typo in an endpoint into a confusing JSON parse error in
the browser instead of a 404.

In production Cloudflare Pages serves the SPA and only the API runs here, so
these routes are the local-development and single-origin path.
"""

from __future__ import annotations

import os

from flask import Blueprint, abort, send_from_directory

spa_bp = Blueprint("spa", __name__)


# React SPA: served from frontend/dist/ (built by GitHub Action, committed to repo)
# Two levels up, not one: this module lives in routes/, so `__file__` here is
# routes/spa.py and the repo root is its grandparent. It was one level when
# these routes lived in upload_imgchest.py, and moving the file silently
# repointed SPA_DIR at routes/frontend/dist, which does not exist.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPA_DIR = os.path.join(_REPO_ROOT, "frontend", "dist")
SPA_INDEX = os.path.join(SPA_DIR, "index.html")


@spa_bp.route("/")
@spa_bp.route("/saved")
@spa_bp.route("/add")
@spa_bp.route("/customs")
@spa_bp.route("/character/<path:name>")
def index(name=None):
    if os.path.exists(SPA_INDEX):
        resp = send_from_directory(SPA_DIR, "index.html")
        # Avoid stale SPA shell after deploy; hashed /assets/* are cached separately.
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp
    return (
        "<html><body><h1>Frontend not built</h1><p>Run the GitHub Action or: "
        "<code>cd frontend && npm install && npm run build</code></p></body></html>",
        503,
        {"Content-Type": "text/html"},
    )


# Serve SPA static assets (JS, CSS from frontend/dist/assets/)
@spa_bp.route("/assets/<path:filename>")
def get_spa_assets(filename):
    assets_dir = os.path.join(SPA_DIR, "assets")
    if os.path.exists(assets_dir):
        # Vite emits content-hashed filenames — safe to cache for a year at the edge.
        return send_from_directory(assets_dir, filename, max_age=31536000)
    abort(404)
