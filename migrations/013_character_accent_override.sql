-- A hand-picked per-character accent override.
--
-- The measured accent (see 007_character_accent.sql) is the dominant colour
-- the art agrees on. It is occasionally wrong in a way no statistic can fix:
-- the colour the community reads as a character's is sometimes not the one
-- with the most pixels -- Audrey Hall is blonde-haired and green-dressed, and
-- the gold wins on area.
--
-- So a staff member can point at a pixel and say "this is her colour". The
-- override is written through to `accent_seed` as well, so every existing read
-- path (the list, the saved rows, the gallery endpoint) shows it with no query
-- change; `accent_override` is the flag that says the value was chosen, not
-- measured, and `accent_extract` refuses to recompute over it. Clearing nulls
-- both so the next visit measures afresh.
--
-- Like every accent, the seed is hex and the frontend derives the eight-token
-- theme from it. NULL means "not overridden".

ALTER TABLE characters ADD COLUMN accent_override TEXT;
ALTER TABLE characters ADD COLUMN accent_override_by TEXT;
ALTER TABLE characters ADD COLUMN accent_override_at TEXT;
