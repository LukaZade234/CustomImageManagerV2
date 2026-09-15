-- Notifications: the app telling one person something, or the owner telling many.
--
-- Two kinds in one table, because they are read the same way:
--   mechanical  the system talking to one account about itself (a role change, a
--               removal). Always one row, one recipient.
--   broadcast   an owner-written message, fanned out to one row per recipient at
--               send time so read state is a plain `read_at` on the row. The
--               alternative -- an audience resolved at read time -- needs a
--               second table to remember who has dismissed what; the cost of
--               fanning out is only that someone who arrives after the send
--               does not receive it, which is what a dated message means.
--
-- Nothing here is a queue: no row is "pending work", and the unread state is
-- only ever the recipient's own messages.

CREATE TABLE notifications (
    id          INTEGER PRIMARY KEY,
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'mechanical' CHECK (kind IN ('mechanical', 'broadcast')),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    -- The owner who sent a broadcast; NULL for mechanical messages.
    created_by  TEXT REFERENCES identities (id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    read_at     TEXT
);

CREATE INDEX idx_notifications_identity ON notifications (identity_id, created_at DESC);
