-- Where a character's portrait is mirrored on our own CDN as WebP.
--
-- Portraits come from `mudae.net` (see 009). They are display-only -- never part
-- of a `$ai` command -- so mirroring them to R2 removes a hotlink dependency on
-- someone else's host and puts them behind a cache we control, in a format an
-- eighth the size.
--
-- The column holds an object key relative to the image base, e.g.
-- "portraits/42-9f3ab2c1.webp", never a host: the deployment's CDN domain stays
-- in configuration, not in the data, exactly like the committed character
-- images and the generated thumbnails. An empty value means the original URL is
-- still what to show, which is also what a development build does.
--
-- characters.main_image_thumb is only ever set when the working row's portrait
-- still points at the catalog's mudae URL; a hand-uploaded main image (ImgChest)
-- keeps no mirror and displays from its own URL.
ALTER TABLE characters ADD COLUMN main_image_thumb TEXT NOT NULL DEFAULT '';
ALTER TABLE character_catalog ADD COLUMN mudae_image_thumb TEXT NOT NULL DEFAULT '';
