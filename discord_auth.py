"""Optional Discord sign-in.

An upgrade, never a wall (DECISIONS.md section 4). Nobody is asked to log in;
signing in binds an existing cookie pseudonym to a Discord account so the
identity survives losing the cookie, and it is how the owner role is
bootstrapped without an admin password existing anywhere.

Unrelated to `mudae_discord.py`. That holds a **self-bot user token** and drives
a real account's chat commands. This is an ordinary OAuth2 application. The two
must never share credentials — a user token cannot perform OAuth, and putting an
OAuth secret where the bot token goes would achieve nothing but leaking it.

Only the `identify` scope is requested: a user id and a display name. Not email,
not guilds, not anything else.
"""

from __future__ import annotations

import os
import secrets

import requests
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"
SCOPE = "identify"

_STATE_SALT = "discord-oauth-state-v1"
# Long enough to read a consent screen, short enough that a leaked link is
# useless by the time anyone finds it.
STATE_MAX_AGE_SECONDS = 600

TIMEOUT_SECONDS = 15


def client_id() -> str:
    return os.environ.get("DISCORD_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.environ.get("DISCORD_CLIENT_SECRET", "").strip()


def owner_discord_id() -> str:
    return os.environ.get("OWNER_DISCORD_ID", "").strip()


def redirect_uri() -> str:
    """Where Discord sends the browser back to.

    Configured explicitly rather than derived from the request. Behind the
    Cloudflare Tunnel the app sees `http://localhost:8080`, so anything built
    from `request.url_root` would not match what is registered with Discord —
    and Discord compares this string exactly.
    """
    configured_uri = os.environ.get("DISCORD_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri
    return "http://localhost:5000/api/auth/discord/callback"


def frontend_base() -> str:
    """Origin of the SPA, for sending the browser back after sign-in.

    In production the SPA is on Cloudflare Pages and the API is on another
    origin, so this cannot be a relative redirect. Locally the Vite proxy makes
    them the same origin and an empty base is correct.
    """
    explicit = os.environ.get("FRONTEND_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    origins = os.environ.get("CORS_ORIGINS", "").strip()
    first = next((o.strip() for o in origins.split(",") if o.strip()), "")
    return first.rstrip("/")


def configured() -> bool:
    return bool(client_id() and client_secret())


def safe_next_path(raw: str | None) -> str:
    """Restrict the post-sign-in destination to a path on our own frontend.

    Never a full URL. Accepting one would make this an open redirect, which is
    the standard way an OAuth callback gets turned into a phishing hop.
    """
    value = (raw or "/").strip()
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def sign_state(secret_key: str, next_path: str) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt=_STATE_SALT)
    return serializer.dumps({"n": secrets.token_urlsafe(8), "r": next_path})


def verify_state(secret_key: str, token: str | None) -> str | None:
    """The stored next path, or None if the state is missing, forged or stale."""
    if not token:
        return None
    serializer = URLSafeTimedSerializer(secret_key, salt=_STATE_SALT)
    try:
        payload = serializer.loads(token, max_age=STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    return safe_next_path(payload.get("r"))


def authorize_url(state: str) -> str:
    from urllib.parse import urlencode

    query = urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            # Always show the consent screen rather than silently re-authorising,
            # so signing in is a visible act.
            "prompt": "consent",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(code: str) -> str:
    """Trade the one-time code for an access token. Raises on failure."""
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id(),
            "client_secret": client_secret(),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise ValueError(f"Discord rejected the authorisation code ({response.status_code})")
    token = response.json().get("access_token")
    if not token:
        raise ValueError("Discord returned no access token")
    return token


def fetch_user(access_token: str) -> dict:
    """{'id', 'name'} for the signed-in account. Raises on failure."""
    response = requests.get(
        USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise ValueError(f"Could not read the Discord profile ({response.status_code})")
    body = response.json()
    discord_id = str(body.get("id") or "").strip()
    if not discord_id:
        raise ValueError("Discord profile had no id")
    # global_name is the current display name; username is the legacy handle.
    name = (body.get("global_name") or body.get("username") or "").strip()
    return {"id": discord_id, "name": name}
