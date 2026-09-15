-- Pinned notifications, and grouping a broadcast so the owner can delete it.
--
-- A normal notification is a row per recipient (migration 014): it is delivered
-- at send time and each recipient can dismiss their own copy. A **pinned** one
-- cannot work that way — it must stay visible, including to an account created
-- after it was sent, and it cannot be dismissed. So a pin is a single global row,
-- resolved at read time by audience, with no per-identity copy to read or delete.
--
-- `group_id` ties the rows of one broadcast together so the owner can remove a
-- message from everyone's inbox at once; a mechanical row has none. Dismissal is
-- a hard delete of the recipient's own row, so no dismissed flag is needed.

ALTER TABLE notifications ADD COLUMN group_id TEXT;
CREATE INDEX idx_notifications_group ON notifications (group_id) WHERE group_id IS NOT NULL;

CREATE TABLE pinned_notifications (
    id         INTEGER PRIMARY KEY,
    audience   TEXT NOT NULL DEFAULT 'everyone' CHECK (audience IN ('everyone', 'moderators')),
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    created_by TEXT REFERENCES identities (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_pinned_audience ON pinned_notifications (audience, created_at DESC);
