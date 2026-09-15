-- Permanent deletion, and the handle needed to do it.
--
-- ImgChest refuses to delete the only image in a post ("You can't delete the only
-- image on a post"), and every upload here is a single-image post -- so the
-- reachable lever is deleting the *post*, via DELETE /v1/post/{id}. We never kept
-- its id; the create-post response carries it as `data.id`.
--
-- Existing rows have none. There is no file->post lookup in the API, so those
-- images cannot be purged -- see docs/MODERATION.md.
--
-- `purged_at` is the tombstone: the row stays (so the record never silently
-- vanishes) with state='removed', hidden from the Removed drawer and refused by
-- restore. The API's `state` CHECK predates this, so purged is not a state value.

ALTER TABLE custom_images ADD COLUMN imgchest_post_id TEXT;
ALTER TABLE custom_images ADD COLUMN purged_at TEXT;
