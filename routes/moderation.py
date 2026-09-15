"""The staff moderation surface: a read-only inspection of who did what.

Not a queue. Nothing here is counted as pending, nothing is actionable, and the
acting verbs (removal, restore, promote) stay on the character page where the
image and its context are. The page is opened deliberately, when the operator
already has a reason, and it answers a question rather than assigning work. See
`docs/MODERATION.md` and `DECISIONS.md` §1 and §5 for why that distinction is
load-bearing.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import db
from identity import require_moderator

moderation_bp = Blueprint("moderation", __name__)

# The detail lists can show additions or removals; anything else is a bad request
# rather than a silent fallback, the same shape `sort` gets in routes/customs.py.
_STATES = ("active", "removed")

_DEFAULT_PER_PAGE = 24
_MAX_PER_PAGE = 100


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
