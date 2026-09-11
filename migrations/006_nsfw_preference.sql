-- Whether this visitor wants to see images marked NSFW.
--
-- Nothing reads it yet: no image carries a rating, so there is nothing to
-- filter. It exists now so the preference is already recorded when the filter
-- arrives -- people will have set it, and their setting will apply to the first
-- image ever marked, rather than everyone being defaulted on the day it ships.
--
-- Defaults to 0 (hide). A filter that arrives switched on for everybody is a
-- filter nobody consented to, and the safer default is the one that cannot
-- surprise somebody.

ALTER TABLE identities ADD COLUMN show_nsfw INTEGER NOT NULL DEFAULT 0;
