"""The Flask application: construction, cross-cutting concerns, and status.

The routes themselves live in `routes/`, one blueprint per subject. They used to
live here, all forty-six of them, because `@app.route` needs the app object to
already exist — so every route had to sit below `# Before anything else that might log, so no startup line is lost.
logs.setup()
log = logs.get(__name__)

app = Flask(__name__)` in this
file, and the file was 1,700 lines. A Blueprint records the same declarations
without an app, which is what lets them move out; this module attaches them at
the bottom, so the import only ever goes one way.

Paths did not change. A blueprint here owns a subject, not a URL prefix.

What stays is what genuinely belongs to the app rather than to any one subject:
the Flask object and its SECRET_KEY, CORS, the identity hooks, the upload guard,
the database-configuration error handler, and the three status endpoints that
describe the deployment itself.
"""

import io
import os
import subprocess
import sys

# Force UTF-8 for stdout/stderr to fix Windows console encoding errors
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# Import utility functions
import db
import identity
import logs
import thumbnails
from imgchest_utils import upload_to_imgchest
from routes.auth import auth_bp
from routes.characters import characters_bp
from routes.customs import customs_bp
from routes.media import media_bp
from routes.mudae import mudae_bp
from routes.spa import spa_bp

# Before anything else that might log, so no startup line is lost.
logs.setup()
log = logs.get(__name__)

app = Flask(__name__)

# SECRET_KEY signs identity cookies from Phase 6 on, so it is load-bearing: a
# changed key silently turns every visitor into a new person. resolve_secret_key
# refuses to start a deployed configuration without one, and generates an
# ephemeral key for local development.
_secret_key, _secret_is_ephemeral = identity.resolve_secret_key()
app.config["SECRET_KEY"] = _secret_key
if _secret_is_ephemeral:
    log.warning(
        "identity.ephemeral_secret_key",
        detail="identities reset on restart; fine for local development",
    )

# CORS.
#
# The SPA moved to Cloudflare Pages, so in production the browser calls this API
# from a different origin and must send the identity cookie with it. That means
# credentialed CORS, and browsers reject credentialed requests against a wildcard
# origin -- so "*" is refused outright rather than failing later in a way that
# looks like "nobody is ever logged in".
#
# Unset means same-origin only, which is correct for local development (the Vite
# dev server proxies to Flask) and for Flask serving the built SPA itself.
_origins = os.environ.get("CORS_ORIGINS", "").strip()
if _origins == "*":
    raise RuntimeError(
        "CORS_ORIGINS='*' is not allowed: this API sends credentials, and browsers "
        "reject Access-Control-Allow-Origin: * on credentialed requests. List the "
        "exact origins instead, e.g. CORS_ORIGINS=https://imgmanager.example.com"
    )
cors_origins = [o.strip() for o in _origins.split(",") if o.strip()]
if cors_origins:
    CORS(app, origins=cors_origins, supports_credentials=True)

# Every request resolves a caller; a visitor without a cookie is issued one on
# the way out. Registered here rather than per-blueprint so no route can
# accidentally run without an identity available.
app.before_request(identity.load_identity)
app.after_request(identity.persist_identity)

# Blueprints. Each owns a subject, not a URL prefix -- paths are unchanged from
# when every route was declared here with @app.route.
app.register_blueprint(auth_bp)
app.register_blueprint(characters_bp)
app.register_blueprint(customs_bp)
app.register_blueprint(media_bp)
app.register_blueprint(mudae_bp)
app.register_blueprint(spa_bp)


@app.before_request
def _guard_custom_image_upload_preprocess():
    """Reject bad POSTs using headers only — do not touch request.form (avoids blocking on ghost/slow bodies)."""
    if request.method != "POST" or request.path != "/api/custom-image":
        return None
    ct = (request.content_type or "").lower()
    if "multipart/form-data" not in ct:
        return jsonify({"error": "Content-Type must be multipart/form-data"}), 400
    ua = (request.headers.get("User-Agent") or "").strip()
    if not ua:
        log.warning("upload.rejected", reason="missing_user_agent")
        return jsonify({"error": "Missing User-Agent"}), 400
    cl = request.content_length
    if cl is not None and cl == 0:
        return jsonify({"error": "Empty body"}), 400
    return None


@app.errorhandler(db.DatabaseConfigurationError)
def _handle_database_configuration_error(exc):
    return jsonify({"error": str(exc)}), 503


def _deployed_revision() -> str:
    """Short commit hash of the running code.

    Lets you confirm what is actually live, which matters because the frontend
    deploys itself via Pages while the backend is pulled by a timer -- so the two
    halves can briefly be on different commits. Resolved once at import.
    """
    override = os.environ.get("APP_REVISION")
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        # Not a git checkout, git missing, or the timeout fired. Never fatal:
        # health must answer even when it cannot identify itself.
        return "unknown"


_DEPLOYED_REVISION = _deployed_revision()



@app.route("/api/health", methods=["GET"])
def health():
    """Is this deployment actually serving? 200 if yes, 503 if not.

    This used to return a static dict, which meant it answered "ok" while the
    database was unreachable — reporting healthy in precisely the situation the
    check exists to catch. Since DEPLOYMENT.md says to check /api/health before
    going further, a check that cannot fail is worse than no check: it turns a
    broken deploy into a confident green light.

    `characters` is reported because a database that opens fine but holds
    nothing is what an unmounted volume looks like (migrations run on connect,
    so the schema is always there). It is not treated as an error, because a
    fresh install before seeding looks identical — see db.check_health.

    `revision` sits outside the status: which commit is answering is useful
    whether or not it is healthy, and is usually the first thing you need.
    """
    database = db.check_health()
    body = {
        "status": "ok" if database["ok"] else "error",
        "service": "imgmanager",
        "revision": _DEPLOYED_REVISION,
        "database": database["detail"],
        "characters": database["characters"],
    }
    return jsonify(body), (200 if database["ok"] else 503)


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Everything the landing page renders, in one request.

    Replaces the home page's full-map fetch: it used to download every image URL
    for every character -- around 475 KB uncompressed -- and count them in the
    browser to display two integers.

    The highlights are best-effort and separately guarded. If that query fails
    the totals still render, because a landing page showing two numbers is a
    great deal better than one showing an error.
    """
    totals = {"custom_images": 0, "characters_with_customs": 0}
    try:
        totals = db.get_custom_image_stats()
    except Exception:
        log.exception("stats.read_failed")

    highlights = {
        "best_covered": [],
        "top_series": [],
        "recent": [],
        "contributors": [],
        "series_count": 0,
    }
    try:
        highlights = db.get_home_highlights()
        highlights["recent"] = [
            {**row, "thumb": thumbnails.thumb_url(row["id"], row["url"])}
            for row in highlights["recent"]
        ]
    except Exception:
        log.exception("stats.highlights_failed")

    return jsonify({**totals, **highlights})


@app.route("/api/last-updated", methods=["GET"])
def get_last_updated():
    try:
        return jsonify(db.get_last_updated())
    except db.DatabaseConfigurationError:
        raise
    except Exception:
        log.exception("last_updated.read_failed")
    return jsonify({})











# ... existing code ...





































if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Run web server
        print("Starting web server at http://localhost:5000")
        print("Open your browser to http://localhost:5000")
        app.run(debug=True, host="0.0.0.0", port=5000)
    elif len(sys.argv) > 1:
        # Command line usage
        file_path = sys.argv[1]
        upload_to_imgchest(file_path)
    else:
        # GUI file selector
        import tkinter as tk
        from tkinter import filedialog

        print("No file provided via arguments. Opening file selector...")
        root = tk.Tk()
        root.withdraw()

        file_path = filedialog.askopenfilename(
            title="Select Image to Upload",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"), ("All Files", "*.*")],
        )

        if file_path:
            upload_to_imgchest(file_path)
        else:
            print("No file selected.")
