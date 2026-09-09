-- Per-identity rate limiting.
--
-- Counts *attempts*, not successes, which is the whole point: an upload that
-- fails still cost an ImgChest API call, and a client hammering failures is
-- exactly what needs stopping. Deriving limits from the existing tables
-- (custom_images.added_at, image_reports.at) would have needed no new storage
-- but would only ever have seen the requests that worked.
--
-- Fixed windows rather than a sliding log: one row per identity per action per
-- window, incremented in place. A burst can therefore straddle a boundary and
-- briefly allow up to 2x the limit, which is an acceptable trade for one small
-- row instead of one row per request.

CREATE TABLE rate_limit_hits (
    identity_id  TEXT NOT NULL,
    action       TEXT NOT NULL,
    -- Unix seconds, floored to the window size. Integer rather than ISO text so
    -- the arithmetic is trivial and the sweep below is a plain range scan.
    window_start INTEGER NOT NULL,
    hits         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (identity_id, action, window_start)
);

-- Deliberately no foreign key to identities. Rows there are created lazily on
-- first write, and rate limiting has to work for a caller who has not written
-- anything yet -- indeed especially for them, since that is what an abusive
-- client looks like. Forcing an identities row just to count a request would
-- also let anyone fill that table by sending requests.

-- Supports the periodic sweep of expired windows.
CREATE INDEX idx_rate_limit_window ON rate_limit_hits (window_start);
