-- The per-character accent colour, computed on the server.
--
-- v1 of the accent measured pixels in the browser and cached the answer in
-- localStorage forever. Two failure modes followed from that split: an answer
-- cached under an older algorithm was never revisited (Audrey Hall stayed red
-- through three rewrites of the extractor), and an answer cached before a
-- gallery existed was never upgraded (Tsumugi Kotobuki stayed colourless after
-- her thumbnails arrived). Both are staleness bugs that cannot exist when the
-- colour is a column recomputed from a fingerprint of its own inputs.
--
-- accent_seed is the representative colour as hex; the frontend derives the
-- full eight-token theme from it (contrast fitting is a display concern).
-- NULL means "declined" -- genuinely two-coloured or greyscale art keeps the
-- system accent -- which is a decided answer, not a missing one, and is why
-- the fingerprint columns are written even when the seed is not.
--
-- The fingerprint is what the gallery looked like when the seed was computed:
-- how many active thumbnailable images, the newest added_at among them, and
-- the portrait URL. accent_partial marks "computed while some thumbnails were
-- still missing from the disk cache", which the listing endpoint retries on
-- the next request rather than serving forever.

ALTER TABLE characters ADD COLUMN accent_seed TEXT;
ALTER TABLE characters ADD COLUMN accent_hue REAL;
ALTER TABLE characters ADD COLUMN accent_source TEXT;
ALTER TABLE characters ADD COLUMN accent_gallery_count INTEGER;
ALTER TABLE characters ADD COLUMN accent_gallery_latest TEXT;
ALTER TABLE characters ADD COLUMN accent_portrait_url TEXT;
ALTER TABLE characters ADD COLUMN accent_partial INTEGER NOT NULL DEFAULT 0;
ALTER TABLE characters ADD COLUMN accent_updated_at TEXT;
