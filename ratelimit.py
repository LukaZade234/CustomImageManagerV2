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

# --- Rate limiting ------------------------------------------------------
#
# There was none at all before this. The limit that actually matters is on
# uploads: every one is an ImgChest API call against a shared key, so an
# unbounded client can get that key throttled or blocked and take the app's
# whole reason for existing with it. The rest are bounded because an endpoint
# with no ceiling is a liability, not because abuse is expected.
#
# Each action carries one or more (limit, window seconds) pairs. Two windows let
# a burst be allowed while a sustained rate is not: 30 uploads in a minute is a
# person pasting a batch, 2000 in an hour is not a person.

_RATE_LIMIT_MULTIPLIER_FOR_STAFF = 10


def _limits_from_env(name: str, default: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Override with e.g. RATE_LIMIT_UPLOAD="30/60,300/3600"."""
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
        print(f"[RATELIMIT] Ignoring malformed RATE_LIMIT_{name.upper()}={raw!r}", flush=True)
        return default


RATE_LIMITS = {
    "upload": _limits_from_env("upload", [(30, 60), (300, 3600)]),
    "import_urls": _limits_from_env("import_urls", [(10, 60), (100, 3600)]),
    "add_character": _limits_from_env("add_character", [(10, 60), (60, 3600)]),
    "edit_character": _limits_from_env("edit_character", [(30, 60), (200, 3600)]),
    "remove": _limits_from_env("remove", [(30, 60), (200, 3600)]),
    "restore": _limits_from_env("restore", [(30, 60), (200, 3600)]),
    # Hiding is harmless to everyone else, so this is generous -- it exists only
    # to stop an endpoint being an unbounded write loop.
    "hide": _limits_from_env("hide", [(120, 60), (1000, 3600)]),
    # Reports can remove other people's work, so an implausible rate should cool
    # down. This is the "auto-cooldown" the roadmap asks for: at two distinct
    # reporters per removal, 20 an hour is far more than honest use needs.
    "report": _limits_from_env("report", [(5, 60), (20, 3600)]),
    # Each Mudae call burns one of Discord's ~1000 daily identify calls.
    "mudae": _limits_from_env("mudae", [(10, 60), (60, 3600)]),
    # Sign-in is cheap for us but hits Discord's API, and a loop here would look
    # like an attack from their side.
    "auth": _limits_from_env("auth", [(10, 60), (40, 3600)]),
}


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
                    print(f"[RATELIMIT] {action} blocked for {me.handle}", flush=True)
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

