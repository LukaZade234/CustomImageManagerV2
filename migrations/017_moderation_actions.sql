-- Moderation actions: the record of what staff have sent a contributor.
--
-- A warn (and later a suspend or ban) does two things at once, and they are not
-- the same row. The recipient gets a **notification** -- the ordinary kind,
-- dismissible from their own inbox. Staff get a **log**, which survives the
-- recipient dismissing it: this table. A moderator can read a person's whole
-- history here; only the owner can delete a line, and deleting it takes the
-- recipient's inbox copy with it.
--
-- `notifications.moderation_action_id` links the two. ON DELETE CASCADE is the
-- owner's delete running from the log to the delivered message, so the two can
-- never disagree about whether a warning was sent.

CREATE TABLE moderation_actions (
    id          INTEGER PRIMARY KEY,
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    -- Who sent it. NULL if that account is later removed; the rest of the line
    -- stays as the record.
    actor_id    TEXT REFERENCES identities (id) ON DELETE SET NULL,
    action      TEXT NOT NULL CHECK (action IN ('warn', 'suspend', 'ban')),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_moderation_actions_identity
    ON moderation_actions (identity_id, created_at DESC);

ALTER TABLE notifications
    ADD COLUMN moderation_action_id INTEGER REFERENCES moderation_actions (id) ON DELETE CASCADE;
