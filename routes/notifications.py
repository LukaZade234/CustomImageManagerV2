"""Notifications: the app messaging one account, and the owner messaging many.

Not a queue — nothing here is pending work, and the unread state is only ever the
recipient's own normal messages. Pinned messages are global and always visible.
See `docs/MODERATION.md`, "Notifications", and migrations 014 and 015.
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
_SOURCES = ("notification", "pin")


@notifications_bp.route("/api/notifications", methods=["GET"])
def list_notifications():
    """This identity's normal messages plus the pinned ones it can see."""
    me = identity.current_identity()
    return jsonify(
        {
            "items": db.list_notifications(me.id, is_staff=me.is_moderator),
            "unread": db.count_unread_notifications(me.id, is_staff=me.is_moderator),
        }
    )


@notifications_bp.route("/api/notifications/read", methods=["POST"])
def mark_read():
    """Clear the unread flag on everything this identity has, pins included."""
    me = identity.current_identity()
    db.mark_notifications_read(me.id, is_staff=me.is_moderator)
    return jsonify({"success": True})


@notifications_bp.route("/api/notifications/dismiss", methods=["POST"])
def dismiss():
    """Remove one normal notification from your own inbox. Pinned cannot be."""
    data = request.get_json(silent=True) or {}
    notification_id = data.get("id")
    if not isinstance(notification_id, int):
        return jsonify({"error": "An id is required"}), 400
    if not db.dismiss_notification(identity.current_identity().id, notification_id):
        return jsonify({"error": "Notification not found"}), 404
    return jsonify({"success": True})


@notifications_bp.route("/api/notifications/delete", methods=["POST"])
@require_owner
@rate_limited("edit_character")
def delete():
    """Owner only: remove a notification from everyone's inbox.

    A normal broadcast is deleted as a group; a pinned message is a single global
    row and disappears for everyone.
    """
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    if source not in _SOURCES:
        return jsonify({"error": "source must be notification or pin"}), 400
    notification_id = data.get("id")
    if not isinstance(notification_id, int):
        return jsonify({"error": "An id is required"}), 400

    removed = db.delete_notification(source, notification_id)
    if not removed:
        return jsonify({"error": "Notification not found"}), 404
    log.info("notifications.deleted", source=source, removed=removed)
    return jsonify({"success": True, "removed": removed})


@notifications_bp.route("/api/notifications/broadcast", methods=["POST"])
@require_owner
@rate_limited("edit_character")
def broadcast():
    """Owner only: send a message to everyone, or to moderators only.

    `pinned` makes it a permanent announcement: a single row every current and
    future recipient sees, which nobody can dismiss.
    """
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

    sent = db.broadcast_notification(
        title,
        body,
        audience,
        identity.current_identity().id,
        pinned=bool(data.get("pinned")),
    )
    log.info("notifications.broadcast", audience=audience, sent=sent, pinned=bool(data.get("pinned")))
    return jsonify({"success": True, "sent": sent})
