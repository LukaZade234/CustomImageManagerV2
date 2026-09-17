-- Add 'ai_artwork' as a report reason.
--
-- `reason` carries a CHECK constraint listing the allowed values, and SQLite
-- cannot widen one in place: ALTER TABLE has no clause for it. The table is
-- rebuilt with the new list instead.
--
-- This is safe here for the reason rebuilds usually are not: `image_reports` is
-- a child table. Nothing references it, so dropping and recreating it cannot
-- cascade into other rows, and the only data at risk is its own -- copied across
-- below. It is also empty in production at the time of writing, so the copy is a
-- formality.
--
-- Note `executescript` cannot run inside a transaction (see `db._apply_migrations`),
-- so this is four statements rather than one atomic unit. On a fresh database
-- the remedy for a half-applied migration is to delete the file and re-run.
CREATE TABLE image_reports_new (
    image_id    INTEGER NOT NULL REFERENCES custom_images (id) ON DELETE CASCADE,
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    reason      TEXT NOT NULL
        CHECK (reason IN ('wrong_character', 'dead_link', 'nsfw', 'duplicate', 'ai_artwork')),
    at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (image_id, identity_id)
);

INSERT INTO image_reports_new (image_id, identity_id, reason, at)
    SELECT image_id, identity_id, reason, at FROM image_reports;

DROP TABLE image_reports;

ALTER TABLE image_reports_new RENAME TO image_reports;
