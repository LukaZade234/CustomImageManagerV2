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

import functools
import hashlib
import os
import secrets
from dataclasses import dataclass

from flask import g, jsonify, request
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
    moderation_status: str | None = None
    moderation_until: str | None = None
    moderation_reason: str = ""

    @property
    def is_moderator(self) -> bool:
        return self.role in ("moderator", "owner")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_signed_in(self) -> bool:
        return self.discord_id is not None

    @property
    def is_suspended(self) -> bool:
        # An expired suspension is normalised away by db.get_identity, so this is
        # only ever the live kind.
        return self.moderation_status == "suspended"

    @property
    def is_banned(self) -> bool:
        return self.moderation_status == "banned"

    @property
    def is_restricted(self) -> bool:
        return self.is_suspended or self.is_banned


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


def public_ref(identity_id: str) -> str:
    """A stable, non-reversible reference for an identity, safe for a URL.

    The identity id never reaches the client -- the cookie is HttpOnly and
    `/api/me` deliberately omits it -- so surfaces that need to name a user in a
    URL key off this hash instead. It is a one-way digest with a distinct
    `person` string, so leaking a ref buys nothing and cannot collide with the
    handle's derivation.
    """
    return hashlib.blake2b(
        identity_id.encode("utf-8"), digest_size=8, person=b"modref"
    ).hexdigest()


def require_moderator(fn):
    """403 unless the caller is a moderator or the owner.

    The gate is a decorator rather than inlined per route so there is one
    implementation to reason about. The frontend redirects non-staff away for a
    clean experience, but this is the boundary that actually enforces the role.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_identity().is_moderator:
            return jsonify({"error": "Not permitted"}), 403
        return fn(*args, **kwargs)

    return wrapper


def require_owner(fn):
    """403 unless the caller is the owner.

    A stricter gate than `require_moderator`, for the one class of action a
    moderator may not take: changing anyone's role.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_identity().is_owner:
            return jsonify({"error": "Not permitted"}), 403
        return fn(*args, **kwargs)

    return wrapper


def require_signed_in(fn=None, *, action: str = "add images"):
    """403 unless the caller has linked a Discord account.

    A cookie-only visitor may browse and curate their own view freely, but two
    actions are tied to a real account on purpose: adding an image uploads bytes
    to ImgChest under our key, and reordering a shared gallery changes what
    everyone sees (see `DECISIONS.md` §1). An account can be held to, and it is
    what makes a ban mean something -- clearing a cookie mints a fresh pseudonym
    for free, so a rule that ignores the account is no rule at all.

    Usable bare (`@require_signed_in`) for the default upload wording, or with an
    action (`@require_signed_in(action="reorder a gallery")`) so the message
    names what the person was trying to do.
    """

    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if not current_identity().is_signed_in:
                return (
                    jsonify(
                        {
                            "error": f"Sign in with Discord to {action}",
                            "code": "discord_required",
                        }
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapper

    if fn is None:
        return decorator
    return decorator(fn)


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


def client_ip() -> str:
    """The caller's address, as best the deployment allows.

    Cloudflare sets `CF-Connecting-IP`; `X-Forwarded-For`'s first hop is the next
    best. Both are only meaningful when the origin is reached through the proxy,
    which is the production shape; locally neither is present and the socket
    address is the client. This feeds a moderation *signal*, never a gate, so the
    spoofing caveat is acceptable.
    """
    forwarded = request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded.strip()
    chain = request.headers.get("X-Forwarded-For")
    if chain:
        return chain.split(",")[0].strip()
    return request.remote_addr or ""


def ip_hash(ip: str) -> str:
    """A keyed digest of an address, so the address itself is never stored.

    Keyed with SECRET_KEY: rotating the key invalidates every stored link, which
    is the right failure mode for a short-lived signal.
    """
    from flask import current_app

    key = current_app.config["SECRET_KEY"].encode("utf-8")[:64]
    return hashlib.blake2b(ip.encode("utf-8"), key=key, digest_size=16).hexdigest()


def record_network() -> None:
    """before_request hook: remember which network an identity wrote from.

    It runs before `block_restricted_writes` so a blocked attempt is still
    recorded -- a restricted account coming back is exactly the link worth
    seeing. Only non-GETs are recorded: a read says nothing about who is
    contributing, and recording every page view would be a log of where everyone
    browsed.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    identity_id = getattr(g, "identity_id", None)
    if not identity_id:
        return None
    ip = client_ip()
    if not ip:
        return None

    import db

    db.record_identity_network(identity_id, ip_hash(ip))
    return None


# A restricted account may still read, so the few POSTs that are *reads* in
# disguise stay open: leaving, reading the notice, fetching an image to download,
# copying a command. Exact paths, not a prefix, so a future route is not opened
# by accident.
_RESTRICTED_ALLOWLIST = frozenset(
    {
        "/api/auth/logout",
        "/api/notifications/read",
        "/api/notifications/dismiss",
        "/api/download-image-proxy",
        "/api/takes",
    }
)


def _restricted_allowed(path: str) -> bool:
    if path in _RESTRICTED_ALLOWLIST:
        return True
    # Recording a page view is part of browsing, not contributing; its path has a
    # name in the middle, so it cannot live in the exact-match set.
    return path.startswith("/api/characters/") and path.endswith("/view")


def block_restricted_writes():
    """before_request hook: a suspended or banned identity may read, not write.

    Browsing is public and anonymous, so a restriction cannot hide the site and
    does not try to -- it removes the ability to *change* anything, which is the
    only lever a ban actually has. It is applied once, to every non-GET, rather
    than by a decorator per endpoint: a new write route should be covered by
    default, not only if its author remembers.

    Sign-in is a GET (the Discord callback), so a banned person can still sign in
    and be told why -- and the ban follows the unique Discord row across cookies.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if _restricted_allowed(request.path):
        return None

    me = current_identity()
    if not me.is_restricted:
        return None

    error = "Your account is banned." if me.is_banned else "Your account is suspended."
    return jsonify({"error": error, "reason": me.moderation_reason, "restricted": True}), 403


def adopt(identity_id: str) -> None:
    """Become a different identity for the rest of this request, and reissue the cookie.

    Signing in can hand you an identity you did not arrive with -- the one your
    Discord account was already bound to -- so the cookie has to be rewritten
    rather than left pointing at the anonymous one.
    """
    g.identity_id = identity_id
    g.identity_is_new = True
    g.identity_loaded = None


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
            moderation_status=row.get("moderation_status"),
            moderation_until=row.get("moderation_until"),
            moderation_reason=row.get("moderation_reason") or "",
        )
    g.identity_loaded = loaded
    return loaded
