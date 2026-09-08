-- v2 initial schema.
--
-- Timestamps are ISO-8601 UTC text: sortable as strings, readable when you open
-- the file in a GUI. `/api/last-updated` converts to the Unix seconds the
-- frontend already sorts on.
--
-- Note that SQLite does NOT enforce foreign keys unless `PRAGMA foreign_keys=ON`
-- is set on every connection. db.py does that; without it these REFERENCES
-- clauses are decoration.

CREATE TABLE characters (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    series         TEXT NOT NULL DEFAULT '',
    rank           TEXT NOT NULL DEFAULT '',
    main_image_url TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Replaces the old `last_updated` document: a column, not a parallel map
    -- that has to be kept in step with everything else.
    --
    -- NULLABLE on purpose. NULL means "never modified", which is how v1 behaved:
    -- untouched characters were simply absent from the last_updated map and the
    -- frontend sorted them last. Defaulting to 'now' would make 774 characters
    -- nobody has ever touched appear as the most recently updated.
    updated_at     TEXT
);

-- Case-insensitive lookup, for the server-side search that must land before the
-- roster grows to ~50k.
CREATE INDEX idx_characters_name_nocase ON characters (name COLLATE NOCASE);
CREATE INDEX idx_characters_series ON characters (series COLLATE NOCASE);

CREATE TABLE identities (
    id         TEXT PRIMARY KEY,
    handle     TEXT NOT NULL,
    discord_id TEXT UNIQUE,
    role       TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'moderator', 'owner')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE custom_images (
    id             INTEGER PRIMARY KEY,
    character_id   INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
    url            TEXT NOT NULL,
    -- Hash of the image bytes, so the same picture re-uploaded to a different
    -- ImgChest URL is still recognised as a duplicate.
    content_hash   TEXT,
    position       INTEGER NOT NULL,
    -- NULL for images migrated from v1: nobody owns them, so nobody can remove
    -- them except through Report. That is the intended outcome.
    added_by       TEXT REFERENCES identities (id) ON DELETE SET NULL,
    added_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Soft delete only. ImgChest never deletes the file, so a removed image is
    -- always restorable; the moderation design depends on that.
    state          TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'removed')),
    removed_by     TEXT REFERENCES identities (id) ON DELETE SET NULL,
    removed_at     TEXT,
    removed_reason TEXT,
    UNIQUE (character_id, url)
);

CREATE INDEX idx_custom_images_char ON custom_images (character_id, state, position);
CREATE INDEX idx_custom_images_hash ON custom_images (content_hash) WHERE content_hash IS NOT NULL;

-- Bookmarks, now per person. In v1 this was a single global list: if anyone
-- bookmarked a character, every visitor saw it.
CREATE TABLE saved (
    identity_id  TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (identity_id, character_id)
);

-- "Hide for me": instant, unlimited, and invisible to everyone else. The
-- pressure valve that removes the reason to delete other people's images.
CREATE TABLE user_hidden (
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    image_id    INTEGER NOT NULL REFERENCES custom_images (id) ON DELETE CASCADE,
    hidden_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (identity_id, image_id)
);

-- Logged, but deliberately drives nothing except an opt-in sort. Collecting it
-- costs nothing and keeps the option of designing a retirement policy later
-- against real evidence rather than a guess.
CREATE TABLE image_takes (
    id          INTEGER PRIMARY KEY,
    image_id    INTEGER NOT NULL REFERENCES custom_images (id) ON DELETE CASCADE,
    identity_id TEXT REFERENCES identities (id) ON DELETE SET NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('download', 'copy_command')),
    at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_image_takes_image ON image_takes (image_id);

-- Objective problems only: wrong character, dead link, NSFW, duplicate. The
-- primary key enforces one report per person per image, which is what makes
-- "two distinct reporters" a meaningful threshold.
CREATE TABLE image_reports (
    image_id    INTEGER NOT NULL REFERENCES custom_images (id) ON DELETE CASCADE,
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    reason      TEXT NOT NULL
        CHECK (reason IN ('wrong_character', 'dead_link', 'nsfw', 'duplicate')),
    at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (image_id, identity_id)
);
