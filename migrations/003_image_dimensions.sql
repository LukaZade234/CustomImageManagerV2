-- Intrinsic image dimensions.
--
-- The gallery lays images out in justified rows, which needs each image's shape
-- *before* it can decide how wide to make it. Without these the browser has to
-- load an image to find out, so every arrival reflows the row it lands in --
-- barely noticeable on a character with six images, and a visible cascade of
-- warping on one with 256.
--
-- Nullable because the 8,547 images migrated from v1 have no dimensions until
-- the backfill script has run, and because a backfill can legitimately fail for
-- an image whose host has since dropped it. The frontend falls back to measuring
-- on load, exactly as it did before, so a NULL here degrades rather than breaks.

ALTER TABLE custom_images ADD COLUMN width INTEGER;
ALTER TABLE custom_images ADD COLUMN height INTEGER;
