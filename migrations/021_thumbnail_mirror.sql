-- Thumbnail mirrors.
--
-- The 600px WebP thumbnail a gallery row draws (thumbnails.py) was origin-only:
-- generated on first request, cached under THUMB_DIR, and served by the app.
-- That works, and Cloudflare caches each one, but the file lives on the one box
-- and the origin is in the path of every cold request.
--
-- The key recorded here is the R2 object the thumbnail was mirrored to, e.g.
-- "thumbs/1234-abcd1234.webp". When it is set the API hands that key to the
-- client and the grid loads the image straight from the CDN; NULL means "not
-- mirrored yet" and the client keeps using /thumbs/<id>.webp, which generates
-- and mirrors on the way through.
--
-- The key (rather than a boolean) is what portrait mirroring already stores in
-- main_image_thumb: it pins the exact object, so a changed key is a new object
-- rather than an overwrite of one served immutable for a year. The content hash
-- in the key is why. See docs/DECISIONS.md.

ALTER TABLE custom_images ADD COLUMN thumb_key TEXT;
