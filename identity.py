"""Cookie-pseudonym identity.

Every visitor gets a signed cookie carrying a stable id on their first request.
There is no login screen and the user never notices. See DECISIONS.md section 4
for why this shape was chosen over accounts.

Two properties worth keeping in mind:

**This is not secure identity, and does not need to be.** Clearing cookies makes
you a new person. That is acceptable because no destructive action is available
to anyone -- under the section 1 moderation design, the worst an evader achieves
is losing their own hidden set and their ability to remove their own uploads.
Cookies are signed so an id cannot be *forged* into someone else's, which is the
property that actually matters for ownership.

**The identities row is created lazily, on first write.** Issuing a cookie is
free; inserting a row for every crawler that touches the site is not. Anything
that stores an identity_id must call db.ensure_identity first, and code reading a
role must tolerate the row not existing yet.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass

from flask import g, request
from itsdangerous import BadSignature, URLSafeSerializer

COOKIE_NAME = "imid"
# Five years. The cookie *is* the account, so expiring it silently deletes
# someone's ownership of their own uploads.
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 5

# Bumping the salt invalidates every existing cookie. Only do that deliberately.
_SALT = "imgmanager-identity-v1"

# Roughly 65 x 66 = 4290 combinations. Handles are cosmetic -- the id is what
# identifies someone -- so collisions are harmless and no uniqueness check is
# needed anywhere.
_ADJECTIVES = (  # noqa: SIM905 - a wrapped sentence reads better than 65 quoted items
    "amber azure brisk bronze calm candid clever cobalt copper coral crimson curious "
    "dapper deft eager fleet fond gentle gilded golden hardy hazel jade jolly keen "
    "lively lucid lunar mellow merry mild nimble noble opal patient placid plucky "
    "prompt quiet rapid ruby rustic sage scarlet serene sharp silver sleek solar "
    "spry stellar sturdy sunny swift teal tidy tranquil trusty umber upbeat vivid "
    "warm willow witty zesty"
).split()

_ANIMALS = (  # noqa: SIM905 - see above
    "otter heron falcon marten badger ibis lynx tapir civet gecko oriole shrike "
    "quokka wombat vervet dingo caiman kestrel puffin auklet fulmar gannet petrel "
    "curlew godwit plover dunlin sanderling turnstone whimbrel redshank greenshank "
    "avocet oystercatcher bittern egret spoonbill crake moorhen coot grebe merganser "
    "goldeneye pochard shoveler pintail gadwall wigeon teal eider scoter smew "
    "goosander shelduck brant barnacle pinkfoot bewick whooper mute crane "
    "stork marmot pika tamarin saola"
).split()

if len(_ADJECTIVES) < 60 or len(_ANIMALS) < 60:  # pragma: no cover - import guard
    raise RuntimeError("Handle wordlists shrank; too few combinations to stay distinguishable.")


@dataclass(frozen=True)
class Identity:
    id: str
    handle: str
    role: str = "user"
    discord_id: str | None = None

    @property
    def is_moderator(self) -> bool:
        return self.role in ("moderator", "owner")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def new_identity_id() -> str:
    return secrets.token_urlsafe(16)


def handle_for(identity_id: str) -> str:
    """Derive a display handle from an id.

    Deterministic rather than stored, so the handle can be reconstructed anywhere
    -- including for an identity whose row has not been written yet -- without
    carrying it in the cookie where the client could tamper with it.
    """
    digest = hashlib.blake2b(identity_id.encode("utf-8"), digest_size=4).digest()
    adjective = _ADJECTIVES[digest[0] % len(_ADJECTIVES)]
    animal = _ANIMALS[digest[1] % len(_ANIMALS)]
    return f"{adjective.capitalize()} {animal.capitalize()}"


def _serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt=_SALT)


def sign(identity_id: str, secret_key: str) -> str:
    return _serializer(secret_key).dumps(identity_id)


def unsign(token: str, secret_key: str) -> str | None:
    """The id, or None if the cookie is absent, malformed or not ours."""
    try:
        value = _serializer(secret_key).loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, str) and value else None


def resolve_secret_key() -> tuple[str, bool]:
    """(key, is_ephemeral).

    SECRET_KEY signs identity cookies, so if it changes every visitor silently
    becomes a new person and loses their uploads and hidden set. There is no safe
    hardcoded default: shipping one to production would let anyone forge another
    user's identity cookie.

    So: a deployed configuration must set it, and refuses to start otherwise.
    Local development gets a random per-process key and a warning, which keeps
    `python upload_imgchest.py --web` working without ceremony.

    CORS_ORIGINS is the signal for "deployed" because it is set exactly when the
    SPA is served from a different origin, which only happens in production.
    """
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key, False
    if os.environ.get("CORS_ORIGINS", "").strip():
        raise RuntimeError(
            "SECRET_KEY is required. It signs identity cookies: without a stable "
            "value every visitor becomes a new person on each restart, losing "
            "ownership of their uploads. Generate one with "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"` '
            "and set it in the environment."
        )
    return secrets.token_urlsafe(48), True


def cookie_is_cross_site() -> bool:
    """Whether the SPA calls this API from another origin.

    Cloudflare Pages serves the SPA from a different origin than the API, and a
    cookie is only sent on a cross-site request when it is SameSite=None, which
    browsers in turn only accept with Secure. Locally the Vite proxy makes it
    same-origin, where Secure would stop the cookie working over plain http.
    """
    return bool(os.environ.get("CORS_ORIGINS", "").strip())


def load_identity() -> None:
    """before_request hook: resolve the caller, minting an id if they are new."""
    from flask import current_app

    secret_key = current_app.config["SECRET_KEY"]
    token = request.cookies.get(COOKIE_NAME)
    identity_id = unsign(token, secret_key) if token else None

    if identity_id is None:
        identity_id = new_identity_id()
        g.identity_is_new = True
    else:
        g.identity_is_new = False
    g.identity_id = identity_id
    # Role is looked up lazily: most requests never need it, and most identities
    # have no row yet.
    g.identity_loaded = None


def persist_identity(response):
    """after_request hook: hand a new visitor their cookie."""
    from flask import current_app

    if not getattr(g, "identity_is_new", False):
        return response
    identity_id = getattr(g, "identity_id", None)
    if not identity_id:
        return response

    cross_site = cookie_is_cross_site()
    response.set_cookie(
        COOKIE_NAME,
        sign(identity_id, current_app.config["SECRET_KEY"]),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=cross_site,
        samesite="None" if cross_site else "Lax",
        path="/",
    )
    return response


def current_identity() -> Identity:
    """The caller. Never None -- an id is minted for anyone without one."""
    cached = getattr(g, "identity_loaded", None)
    if cached is not None:
        return cached

    identity_id = getattr(g, "identity_id", None)
    if identity_id is None:
        # Outside a request that ran the hook (a CLI path, say). Give a
        # throwaway rather than crashing the caller.
        return Identity(id=new_identity_id(), handle="Anonymous")

    import db

    row = db.get_identity(identity_id)
    if row is None:
        loaded = Identity(id=identity_id, handle=handle_for(identity_id))
    else:
        loaded = Identity(
            id=identity_id,
            handle=row.get("handle") or handle_for(identity_id),
            role=row.get("role") or "user",
            discord_id=row.get("discord_id"),
        )
    g.identity_loaded = loaded
    return loaded
