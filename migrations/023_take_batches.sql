-- A batch is one completed "Copy $ai command" action.
--
-- `image_takes` already records a row per image copied, but nothing tied the
-- rows from a single copy together. That made "the images I copied last time"
-- unanswerable without guessing a time window, which is wrong the moment two
-- copies happen close together.
--
-- `batch_id` groups the rows written by one copy. It is set on the first click
-- of "Copy $ai command" and covers every image in that command, however many
-- Discord message parts the paste is split across -- the split is a delivery
-- detail, not a separate intent.
--
-- Nullable, and not backfilled. The rows that predate this column belong to no
-- batch, and cannot be attributed to one without inventing a boundary. They
-- still count towards "copied ever", which is all they can honestly support.
ALTER TABLE image_takes ADD COLUMN batch_id TEXT;

-- "The last batch for this person on this character" is the read this serves:
-- filter by actor, newest first. Nullable rows are excluded by the partial
-- clause, since a take with no batch is not a batch member.
CREATE INDEX idx_image_takes_batch
    ON image_takes (identity_id, at DESC)
    WHERE batch_id IS NOT NULL;
