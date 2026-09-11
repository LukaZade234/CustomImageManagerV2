-- Per-identity display preferences.
--
-- Both are *display* settings, deliberately. The moderation model rests on
-- `custom_images.added_by`: removal is ownership-scoped, so you can only remove
-- your own uploads. If "anonymous" dropped that link the uploader would lose the
-- ability to manage their own images, and those images would fall into the same
-- unowned bucket as the 8,547 migrated from v1 -- permanently, with no way to
-- reclaim them. So ownership is always recorded and only ever hidden at render
-- time, which also makes both toggles retroactive and reversible for free.
--
-- They are separate because they hide different things from different audiences.
-- Someone may be happy to appear on the contributor ranking while not wanting
-- individual images traced back to them, which is the harder of the two to undo
-- socially.
--
-- Neither hides anything from moderators or the owner, who need ownership to
-- moderate at all. The profile page says so in as many words rather than
-- leaving it to be discovered.

ALTER TABLE identities ADD COLUMN hide_from_leaderboard INTEGER NOT NULL DEFAULT 0;
ALTER TABLE identities ADD COLUMN hide_attribution INTEGER NOT NULL DEFAULT 0;
