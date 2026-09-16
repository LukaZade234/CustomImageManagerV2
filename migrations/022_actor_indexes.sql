-- Indexes for the moderation and profile views.
--
-- `custom_images` carried only two indexes: by (character_id, state, position)
-- and by content_hash. But the moderation section and the profile Removed tab
-- filter it by actor -- `added_by = ?` and `removed_by = ?` appear in ten
-- queries, and `list_images_by_identity` alone runs three per page view (a
-- COUNT, the page, and a totals aggregate). Every one of those was a full scan
-- of the table.
--
-- It is survivable at ~8,500 rows, which is exactly why it would go unnoticed
-- until it was not. SQLite is fast at scanning a small table and unforgiving
-- once it grows.
--
-- Partial, because both columns are nullable and mostly NULL: the v1-migrated
-- library predates ownership tracking, so indexing only the rows that have a
-- value keeps the indexes small. The trailing timestamp serves the ORDER BY in
-- list_images_by_identity (`added_at DESC, i.id DESC`); the removed side orders
-- by `COALESCE(removed_at, added_at)`, which the index cannot fully serve, but
-- the filter is the part that was scanning.

CREATE INDEX idx_custom_images_added_by
    ON custom_images (added_by, added_at DESC)
    WHERE added_by IS NOT NULL;

CREATE INDEX idx_custom_images_removed_by
    ON custom_images (removed_by, removed_at DESC)
    WHERE removed_by IS NOT NULL;
