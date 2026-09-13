-- Whether character pages may borrow their accent from the character's artwork.
--
-- On by default, because it is one of the things that makes a character page
-- feel like that character's page. It is recorded per identity rather than in
-- the browser because it is also a promise about server work: a visitor who
-- turns it off has their gallery requests skip accent measurement entirely
-- (see accent_extract.ensure_accent and the /api/custom-image route), so no
-- pixels are read for a colour they have said they do not want to see.
--
-- 1 = on, 0 = off. An identity that has never touched the switch is on, which
-- is why the default is 1 rather than this being a nullable opt-in.

ALTER TABLE identities ADD COLUMN character_accents INTEGER NOT NULL DEFAULT 1;
