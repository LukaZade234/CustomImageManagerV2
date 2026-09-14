-- The gender and pool list a Mudae `$im` card carries.
--
-- The card shows the gender beside the series ("NieR: Automata :male:") and the
-- pools the character belongs to underneath ("Game & Animanga · 201"). Both are
-- parsed from the lookup and kept so a character page can show them.
--
-- Neither is required. A character added by hand, imported from the catalog, or
-- added before this migration has no gender (both 0) and no pools, and the page
-- simply omits them. Both can be true: Mudae lists a character in more than one
-- gender pool.
ALTER TABLE characters ADD COLUMN is_female INTEGER NOT NULL DEFAULT 0;
ALTER TABLE characters ADD COLUMN is_male INTEGER NOT NULL DEFAULT 0;
ALTER TABLE characters ADD COLUMN pools TEXT NOT NULL DEFAULT '';
