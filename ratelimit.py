"""Per-identity rate limiting.

Separated from the routes so the policy — what is limited and how hard — can be
read in one screen, and so a blueprint can apply it without importing the app.
"""

from __future__ import annotations

import os
from functools import wraps

from flask import jsonify

import db
import identity
import logs

# --- Rate limiting ------------------------------------------------------
#
# There was none at all before this. The limit that actually matters is on
# uploads: every one is an ImgChest API call against a shared key, so an
# unbounded client can get that key throttled or blocked and take the app's
# whole reason for existing with it. The rest are bounded because an endpoint
# with no ceiling is a liability, not because abuse is expected.
#
# Each action carries one or more (limit, window seconds) pairs. Two windows let
# a burst be allowed while a sustained rate is not.
#
# The two image-adding limits are set against what a person does, not what a
# batch does, because both paths cost one request per *image*. A web drop is
# hard-coded to a single URL per call (useCustomImageUpload.js), and a file
# upload loops one file per multipart request even though the endpoint accepts a
# list. So "10 a minute" on imports was ten dragged images, and "30 a minute" on
# uploads was a 30-file batch -- both reachable by someone curating a gallery in
# one sitting. They now match: a minute's burst, and an hour that a script
# churning an upload loop will still meet.

_RATE_LIMIT_MULTIPLIER_FOR_STAFF = 10


def _limits_from_env(name: str, default: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Override with e.g. RATE_LIMIT_UPLOAD="60/60,600/3600"."""
    raw = os.environ.get(f"RATE_LIMIT_{name.upper()}", "").strip()
    if not raw:
        return default
    try:
        return [
            (int(part.split("/")[0]), int(part.split("/")[1]))
            for part in raw.split(",")
            if part.strip()
        ] or default
    except (ValueError, IndexError):
        log.warning("ratelimit.bad_env", variable=f"RATE_LIMIT_{name.upper()}", value=raw)
        return default


RATE_LIMITS = {
    "upload": _limits_from_env("upload", [(60, 60), (600, 3600)]),
    "import_urls": _limits_from_env("import_urls", [(60, 60), (600, 3600)]),
    "add_character": _limits_from_env("add_character", [(10, 60), (60, 3600)]),
    "edit_character": _limits_from_env("edit_character", [(30, 60), (200, 3600)]),
    "remove": _limits_from_env("remove", [(30, 60), (200, 3600)]),
    "restore": _limits_from_env("restore", [(30, 60), (200, 3600)]),
    # Reordering is not destructive, but it redistributes prominence, which
    # DECISIONS.md section 1 treats as the same problem as removal -- and unlike
    # a removal it used to leave no trace. Generous enough for an honest
    # keyboard session (each arrow key press is one request), tight enough that
    # a script cannot churn a gallery.
    "reorder": _limits_from_env("reorder", [(120, 60), (900, 3600)]),
    # Hiding is harmless to everyone else, so this is generous -- it exists only
    # to stop an endpoint being an unbounded write loop.
    "hide": _limits_from_env("hide", [(120, 60), (1000, 3600)]),
    # Reports can remove other people's work, so an implausible rate should cool
    # down. This is the "auto-cooldown" the roadmap asks for: at two distinct
    # reporters per removal, 20 an hour is far more than honest use needs.
    "report": _limits_from_env("report", [(5, 60), (20, 3600)]),
    # A moderation message lands in someone's inbox, like a report lands against
    # their work; modest ceilings, but not a button that can be held down.
    "moderate": _limits_from_env("moderate", [(10, 60), (60, 3600)]),
    # Each Mudae call burns one of Discord's ~1000 daily identify calls.
    "mudae": _limits_from_env("mudae", [(10, 60), (60, 3600)]),
    # Sign-in is cheap for us but hits Discord's API, and a loop here would look
    # like an attack from their side.
    "auth": _limits_from_env("auth", [(10, 60), (40, 3600)]),
    # Flipping a switch is cheap, but an endpoint with no ceiling is a liability.
    "settings": _limits_from_env("settings", [(30, 60), (200, 3600)]),
    # Recording a page view is one small upsert, and browsing quickly is normal.
    "view": _limits_from_env("view", [(120, 60), (1000, 3600)]),
    # Catalog suggestions are debounced DB reads; the ceiling is only so the
    # endpoint is not an unbounded loop.
    "suggest": _limits_from_env("suggest", [(120, 60), (1500, 3600)]),
}


log = logs.get(__name__)


def rate_limited(action):
    """Reject the caller with 429 once they exceed `RATE_LIMITS[action]`."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            me = identity.current_identity()
            # Moderators and the owner do the bulk curation work, so a limit set
            # for a visitor would block exactly the person maintaining the site.
            scale = _RATE_LIMIT_MULTIPLIER_FOR_STAFF if me.is_moderator else 1
            for limit, per_seconds in RATE_LIMITS[action]:
                allowed, retry_after = db.check_rate_limit(
                    me.id, action, limit=limit * scale, per_seconds=per_seconds
                )
                if not allowed:
                    log.info(
                        "ratelimit.blocked",
                        action=action,
                        limit=limit * scale,
                        per_seconds=per_seconds,
                    )
                    response = jsonify(
                        {
                            "error": "You are doing that too quickly. Wait a moment and try again.",
                            "retry_after": retry_after,
                        }
                    )
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response
            return view(*args, **kwargs)

        return wrapper

    return decorator
