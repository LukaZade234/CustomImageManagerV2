-- Suspension and ban: the state a moderation action puts an account in.
--
-- A warn is only a message (migration 017). A suspend or a ban is a *state*: it
-- changes what the account may do, and it has to outlive the notification that
-- announced it -- a recipient dismissing the message must not lift their own
-- restriction. So the live state is its own row, keyed by identity.
--
-- The anchor is the identity, and `identities.discord_id` is UNIQUE: signing in
-- again on a fresh cookie finds that same row and adopts it, so a ban follows the
-- Discord account rather than the cookie. A suspension has an expiry and lifts
-- itself at read time; a ban is open-ended until an owner clears it.

CREATE TABLE moderation_status (
    identity_id TEXT PRIMARY KEY REFERENCES identities (id) ON DELETE CASCADE,
    status      TEXT NOT NULL CHECK (status IN ('suspended', 'banned')),
    -- When a suspension ends. NULL for a ban, which has no end.
    until       TEXT,
    reason      TEXT NOT NULL DEFAULT '',
    actor_id    TEXT REFERENCES identities (id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
