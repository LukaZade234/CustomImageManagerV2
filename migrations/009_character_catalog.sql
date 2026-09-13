-- The full Mudae catalog, imported from `$wa` / `$ima` scrapes.
--
-- `characters` is the working set: rows someone has saved, customised or added
-- by hand. This table holds every character an extract knows about, so a name
-- can be searched, autocompleted or looked up without spending one of Discord's
-- ~1000 daily identifies on a `$im`, and so the working rows can be enriched in
-- bulk with a fresher rank, series and portrait.
--
-- name_key is the match key, not the display name: NFKC, curly apostrophes
-- straightened, whitespace collapsed, casefolded. SQLite's COLLATE NOCASE folds
-- ASCII only, so it cannot match "Pokemon" to "Pokemon" with an accent, nor an
-- NFD spelling to an NFC one. Enrichment therefore joins on this column while
-- `name` is stored exactly as Mudae shows it.
--
-- mudae_image_url is the canonical portrait as hosted by Mudae. Portraits are
-- display-only -- they are never part of a `$ai` command -- so the ImgChest
-- constraint does not apply to them; Mudae's own uploads are 225x350 and
-- hotlinkable. A later phase mirrors them to R2 as WebP and stores the mirrored
-- path as characters.main_image_thumb; that column deliberately does not exist
-- yet, so this migration only adds the catalog.
--
-- pool is the raw Mudae tag list ("wa,wg"); the four booleans are the parsed
-- form, because a character can be both waifu and husbando and both anime and
-- game (Truck-kun is `$wa, $ha`). The booleans exist so a future filter is a
-- plain indexed predicate rather than string surgery on the raw tag.
CREATE TABLE character_catalog (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    name_key        TEXT NOT NULL UNIQUE,
    series          TEXT NOT NULL DEFAULT '',
    rank            TEXT NOT NULL DEFAULT '',
    mudae_image_url TEXT NOT NULL DEFAULT '',
    pool            TEXT NOT NULL DEFAULT '',
    is_waifu        INTEGER NOT NULL DEFAULT 0,
    is_husbando     INTEGER NOT NULL DEFAULT 0,
    is_anime        INTEGER NOT NULL DEFAULT 0,
    is_game         INTEGER NOT NULL DEFAULT 0,
    scraped_at      TEXT NOT NULL,
    source_batch    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT
);
CREATE INDEX idx_catalog_series ON character_catalog (series COLLATE NOCASE);
CREATE INDEX idx_catalog_rank ON character_catalog (rank);

-- The "Series - 3/45" header. `listed` is how many characters the extract
-- showed for that series and `total` how many Mudae reports, so a series page
-- can say "3 of 45" and "characters you are missing" is a difference rather
-- than a second lookup.
CREATE TABLE catalog_series (
    series     TEXT PRIMARY KEY COLLATE NOCASE,
    listed     INTEGER,
    total      INTEGER,
    scraped_at TEXT NOT NULL
);
