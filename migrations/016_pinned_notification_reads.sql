-- Read state for pinned notifications, per identity.
--
-- A pin is one global row (migration 015) so a later account still sees it, but
-- that left nowhere to record that a given person had read it. This join table
-- is that place: a pin is unread for an identity until a row exists here. A brand
-- new cookie has no rows at all, so every pinned message it can see counts as
-- unread until it opens the notifications page once.
--
-- This is read state only. Pins still cannot be dismissed: there is no delete
-- path here, and dismissing only ever removes a row from `notifications`.

CREATE TABLE pinned_notification_reads (
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    pinned_id   INTEGER NOT NULL REFERENCES pinned_notifications (id) ON DELETE CASCADE,
    read_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (identity_id, pinned_id)
);
