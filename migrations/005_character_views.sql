-- Character page views.
--
-- Serves two things that both need it: "recently viewed" on the profile, and
-- "most visited" on the landing page. Neither was possible before -- nothing
-- recorded page views at all, and `image_takes` counts copy and download
-- actions, which measure something else entirely.
--
-- The primary key is what makes the numbers mean anything. Keying on
-- (identity, character, hour) means a refresh does not count twice: the insert
-- collides and updates the timestamp instead of adding a row. So one row is one
-- person looking at one character in one hour, and somebody sitting on F5 moves
-- the ranking by exactly as much as somebody who visited once.
--
-- `identity_id` carries no foreign key, for the same reason `rate_limit_hits`
-- does not: identity rows are created lazily on first write, and forcing one
-- into existence merely because somebody looked at a page would turn every
-- reader into a stored user.
--
-- Rows are swept after 90 days. History older than that is not worth the space,
-- and the popularity window is a week.

CREATE TABLE character_views (
    character_id INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
    identity_id  TEXT NOT NULL,
    -- 'YYYY-MM-DDTHH', the hour the view fell in.
    bucket       TEXT NOT NULL,
    viewed_at    TEXT NOT NULL,
    PRIMARY KEY (identity_id, character_id, bucket)
);

-- "What have I looked at lately", newest first.
CREATE INDEX idx_character_views_identity ON character_views (identity_id, viewed_at DESC);

-- "What has been popular this week", and the sweep.
CREATE INDEX idx_character_views_recent ON character_views (viewed_at);
