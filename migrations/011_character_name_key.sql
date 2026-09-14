-- A stored, folded name key on the working set.
--
-- find_character matched a name by loading every character row and folding each
-- in Python -- fine at 1,700, a full scan on every Add keystroke at 50,000. The
-- folded form (NFKC, curly quotes straightened, whitespace collapsed, casefolded)
-- cannot be expressed in SQLite, so it is stored and indexed here, exactly as
-- character_catalog.name_key already is.
--
-- Written on every insert and rename. Existing rows are backfilled on the first
-- connect after this migration (`db._backfill_character_name_keys`).
ALTER TABLE characters ADD COLUMN name_key TEXT NOT NULL DEFAULT '';

CREATE INDEX idx_characters_name_key ON characters (name_key);
