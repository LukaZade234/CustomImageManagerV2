"""Discord sign-in.

An upgrade, never a wall: nobody is asked to log in, and everything works
without an account. Signing in binds the cookie pseudonym already in the
browser to a Discord account, so the identity survives losing the cookie, and
it is how the owner role is bootstrapped without an admin password existing
anywhere.

The state parameter is signed with the app's SECRET_KEY, which is reached
through `current_app` — a blueprint has no app of its own, and inside a request
`current_app` is the one handling it.
"""

from __future__ import annotations

import requests
from flask import Blueprint, current_app, jsonify, redirect, request

import db
import discord_auth
import identity
import logs
from ratelimit import rate_limited

log = logs.get(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/discord/start", methods=["GET"])
@rate_limited("auth")
def discord_auth_start():
    """Send the browser to Discord's consent screen.

    `next` is carried through the signed state so you come back to the page you
    started on, and is restricted to a path on our own frontend -- accepting a
    full URL here is how an OAuth callback becomes an open redirect.
    """
    if not discord_auth.configured():
        return jsonify({"error": "Discord sign-in is not configured"}), 503
    next_path = discord_auth.safe_next_path(request.args.get("next"))
    state = discord_auth.sign_state(current_app.config["SECRET_KEY"], next_path)
    return redirect(discord_auth.authorize_url(state))


@auth_bp.route("/api/auth/discord/callback", methods=["GET"])
@rate_limited("auth")
def discord_auth_callback():
    """Where Discord sends the browser back.

    Errors redirect to the frontend with a query flag rather than rendering JSON:
    the person here is in a browser mid-flow, and a raw error body is a dead end.
    """
    if not discord_auth.configured():
        return jsonify({"error": "Discord sign-in is not configured"}), 503

    base = discord_auth.frontend_base()
    next_path = discord_auth.verify_state(
        current_app.config["SECRET_KEY"], request.args.get("state")
    )
    if next_path is None:
        # Forged, tampered or simply left open too long.
        return redirect(f"{base}/?signin=expired")
    if request.args.get("error"):
        # The user pressed Cancel on the consent screen.
        return redirect(f"{base}{next_path}?signin=cancelled")

    code = request.args.get("code")
    if not code:
        return redirect(f"{base}{next_path}?signin=failed")

    try:
        profile = discord_auth.fetch_user(discord_auth.exchange_code(code))
    except (ValueError, requests.RequestException) as e:
        log.warning("auth.signin_failed", error=str(e))
        return redirect(f"{base}{next_path}?signin=failed")

    result = db.bind_discord_identity(
        identity.current_identity().id,
        profile["id"],
        display_name=profile["name"],
        owner_discord_id=discord_auth.owner_discord_id(),
    )
    # The caller may now be a different identity than the one they arrived with,
    # so the cookie has to be reissued rather than left pointing at the old one.
    identity.adopt(result["identity_id"])
    log.info("auth.signed_in", role=result["role"], merged=result["merged"])
    return redirect(f"{base}{next_path}?signin=ok")


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    """Forget the current identity in this browser.

    Deliberately not a delete: the identity and everything it owns stays, and
    signing in again reaches it. This only hands out a fresh anonymous cookie.
    """
    identity.adopt(identity.new_identity_id())
    return jsonify({"success": True})


@auth_bp.route("/api/me", methods=["GET"])
def get_me():
    """Who the caller is, as far as the server is concerned.

    Deliberately does not return the identity id. The cookie is HttpOnly so that
    script cannot read or copy it; handing the same value back in JSON would
    give that away for nothing. The frontend never needs the id -- ownership is
    reported per image by the server, which is the only place it can be decided
    anyway.
    """
    me = identity.current_identity()
    return jsonify(
        {
            "handle": me.handle,
            "role": me.role,
            "is_moderator": me.is_moderator,
            "is_owner": me.is_owner,
            "signed_in": me.discord_id is not None,
            "discord_available": discord_auth.configured(),
            "settings": db.get_identity_settings(me.id),
        }
    )


@auth_bp.route("/api/me/settings", methods=["PATCH"])
@rate_limited("settings")
def update_my_settings():
    """Change a display preference.

    Only the two privacy toggles are writable. Neither touches what is stored --
    ownership is always recorded, because removal is ownership-scoped and an
    uploader who could not be identified could not manage their own images. Both
    are applied when rendering, which is what makes them retroactive and
    reversible.
    """
    data = request.get_json(silent=True) or {}
    me = identity.current_identity()
    settings = db.update_identity_settings(
        me.id,
        hide_from_leaderboard=data.get("hide_from_leaderboard"),
        hide_attribution=data.get("hide_attribution"),
    )
    log.info("settings.updated", **settings)
    return jsonify({"success": True, "settings": settings})


@auth_bp.route("/api/me/hidden", methods=["GET"])
def my_hidden_images():
    """Everything this visitor has hidden, across every character."""
    return jsonify(db.get_hidden_for_identity(identity.current_identity().id))


@auth_bp.route("/api/me/removed", methods=["GET"])
def my_removed_images():
    """Everything this visitor removed, across every character. All restorable."""
    return jsonify(db.get_removed_by_identity(identity.current_identity().id))


@auth_bp.route("/api/me/history", methods=["GET"])
def my_history():
    """Characters this visitor has looked at, most recent first."""
    return jsonify(db.get_view_history(identity.current_identity().id))


@auth_bp.route("/api/me/contributions", methods=["GET"])
def my_contributions():
    return jsonify({"images": db.count_images_added_by(identity.current_identity().id)})
