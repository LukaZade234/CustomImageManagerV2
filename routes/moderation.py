"""The staff moderation surface: a read-only inspection of who did what.

Not a queue. Nothing here is counted as pending, nothing is actionable, and the
acting verbs (removal, restore, promote) stay on the character page where the
image and its context are. The page is opened deliberately, when the operator
already has a reason, and it answers a question rather than assigning work. See
`docs/MODERATION.md` and `DECISIONS.md` §1 and §5 for why that distinction is
load-bearing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request

import db
import identity
import logs
from identity import require_moderator, require_owner
from ratelimit import rate_limited
from routes.notifications import MAX_BODY, MAX_TITLE

log = logs.get(__name__)
moderation_bp = Blueprint("moderation", __name__)

# The detail lists can show additions or removals; anything else is a bad request
# rather than a silent fallback, the same shape `sort` gets in routes/customs.py.
_STATES = ("active", "removed")

_DEFAULT_PER_PAGE = 24
_MAX_PER_PAGE = 100

# A year is the ceiling: a suspension is meant to be shorter than a ban, and
# anything open-ended should be a ban (which an owner has to lift explicitly).
_MAX_SUSPEND_DAYS = 365


@moderation_bp.route("/api/moderation/users")
@require_moderator
def moderation_users():
    """Every contributor, with the counts the detail panes will show.

    Unpaged: bounded by people who have written something, not by visitors.
    """
    users = db.list_contributors()
    return jsonify({"items": users, "total": len(users)})


@moderation_bp.route("/api/moderation/users/<ref>/images")
@require_moderator
def moderation_user_images(ref):
    """One page of an actor's additions or removals, newest first."""
    identity_id = db.identity_by_ref(ref)
    if identity_id is None:
        return jsonify({"error": "Unknown contributor"}), 404

    state = request.args.get("state") or "active"
    if state not in _STATES:
        return jsonify({"error": "state must be active or removed"}), 400

    try:
        page = int(request.args.get("page") or 1)
        per_page = int(request.args.get("per_page") or _DEFAULT_PER_PAGE)
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400
    per_page = max(1, min(_MAX_PER_PAGE, per_page))

    character = (request.args.get("char") or "").strip() or None
    result = db.list_images_by_identity(
        identity_id,
        state=state,
        character=character,
        page=page,
        per_page=per_page,
    )
    return jsonify(result)


@moderation_bp.route("/api/moderation/users/<ref>/characters")
@require_moderator
def moderation_user_characters(ref):
    """The same actor's work grouped by character, sorted like Browse Customs."""
    identity_id = db.identity_by_ref(ref)
    if identity_id is None:
        return jsonify({"error": "Unknown contributor"}), 404

    state = request.args.get("state") or "active"
    if state not in _STATES:
        return jsonify({"error": "state must be active or removed"}), 400

    sort = request.args.get("sort") or "count"
    if sort not in db.MODERATION_CHARACTER_SORT_KEYS:
        return jsonify({"error": "unknown sort"}), 400
    # Rank reads best-first ascending; the count keys read best descending.
    order = request.args.get("order") or ("asc" if sort == "rank" else "desc")
    if order not in ("asc", "desc"):
        return jsonify({"error": "order must be asc or desc"}), 400

    try:
        page = int(request.args.get("page") or 1)
        per_page = int(request.args.get("per_page") or _DEFAULT_PER_PAGE)
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400
    per_page = max(1, min(_MAX_PER_PAGE, per_page))

    query = (request.args.get("character") or "").strip() or None
    result = db.list_characters_by_identity(
        identity_id,
        state=state,
        query=query,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )
    return jsonify(result)


# The role a moderator may be moved between. `owner` is deliberately absent:
# the owner is bootstrapped from OWNER_DISCORD_ID and there is only ever one, so
# there is nobody to promote into it and no way to remove it from here.
_ROLE_CHOICES = ("user", "moderator")


@moderation_bp.route("/api/moderation/users/<ref>/role", methods=["POST"])
@require_owner
@rate_limited("edit_character")
def moderation_set_role(ref):
    """Promote a user to moderator, or demote a moderator back to user.

    Owner only. A moderator has every other power the owner has, but may not
    change anyone's role -- including their own or another moderator's.
    """
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404

    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role not in _ROLE_CHOICES:
        return jsonify({"error": "role must be user or moderator"}), 400

    target = db.get_identity(target_id)
    if target is None:
        return jsonify({"error": "Contributor has no identity yet"}), 404
    if target["role"] == "owner":
        return jsonify({"error": "The owner's role cannot be changed"}), 400
    if target_id == identity.current_identity().id:
        return jsonify({"error": "You cannot change your own role"}), 400

    if not db.set_role(target_id, role):
        return jsonify({"error": "Could not change the role"}), 500
    # Tell the person. This is the first mechanical notification; the channel it
    # uses is the one the owner's broadcasts go out on (docs/MODERATION.md).
    if role == "moderator":
        db.add_notification(
            target_id,
            "You are now a moderator",
            "You have been given access to the moderation surface, in your profile.",
        )
    else:
        db.add_notification(
            target_id,
            "Your moderator role was removed",
            "You no longer have access to the moderation surface.",
        )
    log.info("moderation.role_changed", ref=ref, role=role)
    return jsonify({"success": True, "ref": ref, "role": role})


def _days_from_now(days: int) -> str:
    """An ISO instant `days` ahead, in the same shape db._now() writes."""
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _read_message(data: dict) -> tuple[str, str, str | None]:
    """Pull and validate a moderator's title and body. Returns (title, body, error)."""
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title:
        return "", "", "A title is required"
    if len(title) > MAX_TITLE:
        return "", "", f"Title too long (max {MAX_TITLE} characters)"
    if len(body) > MAX_BODY:
        return "", "", f"Message too long (max {MAX_BODY} characters)"
    return title, body, None


def _refuse_restricting(target_id: str):
    """Shared guards for suspend and ban.

    The owner is never a target, you cannot target yourself, and a moderator
    cannot target another moderator -- staff-on-staff restriction is an owner
    move. A moderator may still restrict ordinary users.
    """
    target = db.get_identity(target_id)
    if target is None:
        return jsonify({"error": "Contributor has no identity yet"}), 404

    actor = identity.current_identity()
    if target["role"] == "owner":
        return jsonify({"error": "The owner cannot be restricted"}), 400
    if target_id == actor.id:
        return jsonify({"error": "You cannot restrict your own account"}), 400
    if target["role"] == "moderator" and not actor.is_owner:
        return jsonify({"error": "Only the owner can restrict a moderator"}), 403
    return None


@moderation_bp.route("/api/moderation/users/<ref>/warn", methods=["POST"])
@require_moderator
@rate_limited("moderate")
def moderation_warn(ref):
    """Send one contributor a warning: a message in their inbox, and a log line.

    Any moderator may warn. The message is the recipient's to dismiss, but the
    record is not -- it stays in their moderation history for staff to read, and
    only the owner can remove it. A warn changes nothing else; suspend and ban
    (below) are the ones that carry a state.
    """
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404

    title, body, error = _read_message(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    action_id = db.moderate_identity(target_id, identity.current_identity().id, "warn", title, body)
    log.info("moderation.warned", ref=ref, action_id=action_id)
    return jsonify({"success": True, "id": action_id, "ref": ref})


@moderation_bp.route("/api/moderation/users/<ref>/suspend", methods=["POST"])
@require_moderator
@rate_limited("moderate")
def moderation_suspend(ref):
    """Suspend a contributor for a number of days.

    Time-boxed and self-lifting: the account may still read the site and is told
    why, but every write is refused while it lasts (identity.block_restricted_writes).
    """
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404
    refusal = _refuse_restricting(target_id)
    if refusal:
        return refusal

    data = request.get_json(silent=True) or {}
    title, body, error = _read_message(data)
    if error:
        return jsonify({"error": error}), 400
    try:
        days = int(data.get("days"))
    except (TypeError, ValueError):
        return jsonify({"error": "A number of days is required"}), 400
    if not 1 <= days <= _MAX_SUSPEND_DAYS:
        return jsonify({"error": f"Days must be between 1 and {_MAX_SUSPEND_DAYS}"}), 400

    actor = identity.current_identity()
    until = _days_from_now(days)
    db.set_moderation_status(target_id, "suspended", until=until, reason=body, actor_id=actor.id)
    action_id = db.moderate_identity(target_id, actor.id, "suspend", title, body)
    log.info("moderation.suspended", ref=ref, days=days, action_id=action_id)
    return jsonify({"success": True, "id": action_id, "ref": ref, "until": until})


@moderation_bp.route("/api/moderation/users/<ref>/ban", methods=["POST"])
@require_moderator
@rate_limited("moderate")
def moderation_ban(ref):
    """Ban a contributor, open-ended.

    The same shape as a suspension without an end: the anchor is the identity,
    whose Discord id is unique, so signing in again adopts the banned row rather
    than escaping it.
    """
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404
    refusal = _refuse_restricting(target_id)
    if refusal:
        return refusal

    title, body, error = _read_message(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    actor = identity.current_identity()
    db.set_moderation_status(target_id, "banned", reason=body, actor_id=actor.id)
    action_id = db.moderate_identity(target_id, actor.id, "ban", title, body)
    log.info("moderation.banned", ref=ref, action_id=action_id)
    return jsonify({"success": True, "id": action_id, "ref": ref})


@moderation_bp.route("/api/moderation/users/<ref>/lift", methods=["POST"])
@require_owner
@rate_limited("moderate")
def moderation_lift(ref):
    """Owner only: lift a suspension or ban, and tell the person."""
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404

    if not db.clear_moderation_status(target_id):
        return jsonify({"error": "That account is not suspended or banned"}), 400

    db.add_notification(
        target_id,
        "Your account has been restored",
        "The restriction on your account has been lifted. You can contribute again.",
        created_by=identity.current_identity().id,
    )
    log.info("moderation.lifted", ref=ref)
    return jsonify({"success": True, "ref": ref})


@moderation_bp.route("/api/moderation/users/<ref>/history")
@require_moderator
def moderation_history(ref):
    """Everything staff have sent this contributor, newest first."""
    target_id = db.identity_by_ref(ref)
    if target_id is None:
        return jsonify({"error": "Unknown contributor"}), 404
    items = db.list_moderation_actions(target_id)
    return jsonify({"items": items, "total": len(items)})


@moderation_bp.route("/api/moderation/history/<int:action_id>/delete", methods=["POST"])
@require_owner
@rate_limited("moderate")
def moderation_delete_history(action_id):
    """Owner only: remove a moderation record, and the recipient's copy with it."""
    if not db.delete_moderation_action(action_id):
        return jsonify({"error": "Moderation record not found"}), 404
    log.info("moderation.history_deleted", action_id=action_id)
    return jsonify({"success": True})
