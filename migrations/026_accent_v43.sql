-- The V43 accent (docs/ACCENT.md section 29).
--
-- The accent used to be measured inline, on the gallery request, from the
-- colours of up to 60 thumbnails. V43 first cuts each character out of its image
-- and parses the face (hair, skin, clothes) with two models, which take about a
-- second per image and 1.9 GB of memory -- far too much for a request. So the
-- models run once per image, in a background worker (accent_worker.py), and
-- what they found is kept here; recomputing a character afterwards is fast.
--
-- accent_version names the algorithm that produced a character's seed: NULL for
-- the original extractor, 'v43' for this one. With the V43 engine switched on, a
-- seed from anything else counts as stale and is queued, never recomputed inline.
--
-- accent_image_data holds one row per gallery image (keyed by its row, so a
-- permanently deleted image takes its data with it) and accent_main_data one per
-- main-image URL: the cut-out mask and the face parser's labels at the 200px
-- measurement size (a compressed numpy blob), each face's hair colour, and the
-- data version (accent_models.DATA_VERSION) so a model change can supersede it.
--
-- accent_queue is the worker's to-do list: characters whose seed is stale. One
-- row per character; a failed attempt is counted and retried later.

ALTER TABLE characters ADD COLUMN accent_version TEXT;

CREATE TABLE accent_image_data (
    image_id     INTEGER PRIMARY KEY REFERENCES custom_images (id) ON DELETE CASCADE,
    version      TEXT NOT NULL,
    data         BLOB NOT NULL,
    face_hair    TEXT NOT NULL,
    n_faces      INTEGER NOT NULL,
    computed_at  TEXT NOT NULL
);

CREATE TABLE accent_main_data (
    url          TEXT PRIMARY KEY,
    version      TEXT NOT NULL,
    data         BLOB NOT NULL,
    face_hair    TEXT NOT NULL,
    n_faces      INTEGER NOT NULL,
    computed_at  TEXT NOT NULL
);

CREATE TABLE accent_queue (
    character_id INTEGER PRIMARY KEY REFERENCES characters (id) ON DELETE CASCADE,
    queued_at    TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    next_try_at  TEXT NOT NULL,
    last_error   TEXT
);

CREATE INDEX idx_accent_queue_next ON accent_queue (next_try_at);
