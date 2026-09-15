"""Notifications: the app messaging one account, and the owner messaging many.

Not a queue — nothing here is pending work, and the unread state is only ever the
recipient's own messages. See `docs/MODERATION.md`, "Notifications", and
migration 014.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import db
import identity
import logs
from identity import require_owner
from ratelimit import rate_limited

log = logs.get(__name__)
notifications_bp = Blueprint("notifications", __name__)

MAX_TITLE = 200
MAX_BODY = 2000
_AUDIENCES = ("everyone", "moderators")


@notifications_bp.route("/api/notifications", methods=["GET"])
def list_notifications():
    """This identity's own messages, newest first, with the unread count."""
    me = identity.current_identity()
    return jsonify(
        {
            "items": db.list_notifications(me.id),
            "unread": db.count_unread_notifications(me.id),
        }
    )


@notifications_bp.route("/api/notifications/read", methods=["POST"])
def mark_read():
    """Clear the unread flag on everything this identity has."""
    db.mark_notifications_read(identity.current_identity().id)
    return jsonify({"success": True})


@notifications_bp.route("/api/notifications/broadcast", methods=["POST"])
@require_owner
@rate_limited("edit_character")
def broadcast():
    """Owner only: send a message to everyone, or to moderators only."""
    data = request.get_json(silent=True) or {}
    audience = data.get("audience")
    if audience not in _AUDIENCES:
        return jsonify({"error": "audience must be everyone or moderators"}), 400

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title:
        return jsonify({"error": "A title is required"}), 400
    if len(title) > MAX_TITLE:
        return jsonify({"error": f"Title too long (max {MAX_TITLE} characters)"}), 400
    if len(body) > MAX_BODY:
        return jsonify({"error": f"Message too long (max {MAX_BODY} characters)"}), 400

    sent = db.broadcast_notification(title, body, audience, identity.current_identity().id)
    log.info("notifications.broadcast", audience=audience, sent=sent)
    return jsonify({"success": True, "sent": sent})
