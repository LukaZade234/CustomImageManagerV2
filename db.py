"""Data layer. SQLite, one file, no server (see docs/DECISIONS.md section 8).

Concurrency
-----------
v1 stored whole JSON documents and changed them with a read-modify-write spread
across two calls, which lost data whenever two requests overlapped. That is gone:
images are rows, so two people adding to the same character insert two rows and
never contend. Operations that genuinely need to be atomic take a transaction.

SQLite specifics that matter
----------------------------
* Foreign keys are **not** enforced unless `PRAGMA foreign_keys=ON` is set on every
  connection. Without it the REFERENCES clauses in the schema are decoration.
* Connections are per thread (`sqlite3` objects are not safe to share), held in a
  thread-local and closed at exit.
* WAL mode allows concurrent readers alongside a writer; `busy_timeout` makes a
  writer wait for a lock rather than failing instantly.
"""

import atexit
import os
import sqlite3
import threading
import time
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import identity
import thumbnails

_REPO_ROOT = Path(__file__).resolve().parent
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"

DEFAULT_DB_PATH = _REPO_ROOT / "data" / "imgmanager.db"

# Bridge until Phase 6 introduces real identities. v1 bookmarks were a single
# global list, so they are migrated onto one shared identity and the saved
# endpoints use it as "the current user". Phase 6 replaces this with the real
# identity from the request.
LEGACY_IDENTITY_ID = "legacy-shared"

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False


class DatabaseConfigurationError(RuntimeError):
    """Raised when the database cannot be opened."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def database_path() -> Path:
    """Resolved from DATABASE_PATH, falling back to ./data/imgmanager.db."""
    configured = os.environ.get("DATABASE_PATH")
    return Path(configured) if configured else DEFAULT_DB_PATH


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Wait rather than raising "database is locked" the instant a writer holds it.
    conn.execute("PRAGMA busy_timeout = 5000")
    # Safe with WAL: survives process crashes, only risks the last commits on a
    # sudden power loss -- and Litestream has already shipped those to R2.
    conn.execute("PRAGMA synchronous = NORMAL")


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        # executescript issues an implicit COMMIT first, so a migration cannot be
        # wrapped in an outer transaction. On a fresh single-file database the
        # remedy for a half-applied migration is to delete the file and re-run.
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)", (path.name, _now())
        )
        conn.commit()


def _connect() -> sqlite3.Connection:
    global _initialised
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path), timeout=5.0, isolation_level="DEFERRED")
    except sqlite3.Error as exc:
        raise DatabaseConfigurationError(f"Could not open database at {path}: {exc}") from exc
    _configure(conn)

    with _init_lock:
        if not _initialised:
            # Persistent, stored in the file itself; only needs setting once.
            conn.execute("PRAGMA journal_mode = WAL")
            _apply_migrations(conn)
            _initialised = True
    return conn


def get_connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


def close_connection() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


def _reset_db() -> None:
    """Drop cached state so the next call reopens. Used by tests."""
    global _initialised
    close_connection()
    with _init_lock:
        _initialised = False


atexit.register(close_connection)


@contextmanager
def transaction():
    """Commit on success, roll back on error."""
    conn = get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


# --- Characters ---------------------------------------------------------


def _character_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM characters WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


def _ensure_character(conn: sqlite3.Connection, name: str) -> int:
    """Return the id, creating a bare row if the character is unknown.

    v1 let custom images be attached to any name, whether or not it appeared in
    the character list, so the same must remain possible here.
    """
    # INSERT-then-SELECT rather than check-then-INSERT. The latter is a race:
    # two threads both see the name missing, both insert, and one fails on the
    # UNIQUE constraint. This is the same read-modify-write hazard Phase 2
    # removed from the document layout, and it is easy to reintroduce here.
    conn.execute("INSERT INTO characters (name) VALUES (?) ON CONFLICT (name) DO NOTHING", (name,))
    row = conn.execute("SELECT id FROM characters WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def get_characters() -> list | None:
    """API shape. None when nothing has been seeded yet, which callers treat as
    "the database is not ready" exactly as v1 did."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, series, rank, main_image_url FROM characters ORDER BY id"
    ).fetchall()
    if not rows:
        return None
    return [
        {
            "name": r["name"],
            "series": r["series"],
            "rank": r["rank"],
            "image": r["main_image_url"],
        }
        for r in rows
    ]


def add_character(name: str, series: str, rank: str, main_image_url: str = "") -> bool:
    """False if the name is already taken."""
    with transaction() as conn:
        # Let the UNIQUE constraint decide, rather than checking first and
        # racing another writer between the check and the insert.
        cur = conn.execute(
            "INSERT INTO characters (name, series, rank, main_image_url) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (name) DO NOTHING",
            (name, series, rank, main_image_url),
        )
        return bool(cur.rowcount)


def update_character(orig_name: str, new_name: str, series: str, rank: str) -> bool:
    """Rename and re-describe. False if orig_name is unknown.

    This is the whole rename: images, bookmarks and the timestamp all hang off
    `characters.id`, so nothing else has to be touched. v1 needed a 67-line
    cascade across three documents here, which could half-fail.
    """
    with transaction() as conn:
        char_id = _character_id(conn, orig_name)
        if char_id is None:
            return False
        conn.execute(
            "UPDATE characters SET name = ?, series = ?, rank = ?, updated_at = ? WHERE id = ?",
            (new_name, series, rank, _now(), char_id),
        )
        return True


def set_main_image(char_name: str, image_url: str) -> bool:
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return False
        conn.execute(
            "UPDATE characters SET main_image_url = ?, updated_at = ? WHERE id = ?",
            (image_url, _now(), char_id),
        )
        return True


def update_last_modified(char_name: str) -> None:
    with transaction() as conn:
        char_id = _ensure_character(conn, char_name)
        conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))


def check_health() -> dict:
    """Is the database usable, and does it hold anything?

    Returns {"ok", "detail", "characters"}.

    Two failure modes matter, and only one of them is an error:

    - **Unusable.** The file cannot be opened or read. That is `ok: False`.
    - **Usable but empty.** This is the shape an unmounted volume takes here.
      `_connect()` applies migrations on first use, so a fresh empty file does
      not stay schemaless — it comes back fully formed with zero rows, and any
      check that only asks "does this table exist" reports it perfectly healthy.

    The count is what separates that from a working deployment, so it is
    reported rather than judged: zero characters is also what a legitimate fresh
    install looks like before seeding, and 503 on a correct first boot would be
    its own kind of lie. A human reading the endpoint, or a probe with a
    threshold, can tell the two apart; this function will not guess.
    """
    try:
        conn = get_connection()
        row = conn.execute("SELECT count(*) AS n FROM characters").fetchone()
    except DatabaseConfigurationError as exc:
        return {"ok": False, "detail": str(exc), "characters": 0}
    except sqlite3.Error as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}", "characters": 0}
    return {"ok": True, "detail": "ok", "characters": int(row["n"]) if row else 0}


def get_last_updated() -> dict:
    """{name: unix_seconds}. Converted here because the frontend sorts numerically."""
    conn = get_connection()
    out = {}
    # NULL updated_at means never modified: omitted, exactly as v1 omitted such
    # names from the document, so the frontend keeps sorting them last.
    for row in conn.execute("SELECT name, updated_at FROM characters WHERE updated_at IS NOT NULL"):
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=UTC
            )
            out[row["name"]] = stamp.timestamp()
        except (ValueError, TypeError):
            out[row["name"]] = 0.0
    return out


# --- Custom images ------------------------------------------------------


# Whitelisted, never interpolated from user input. Each entry is an ORDER BY
# fragment; a caller passes the key, not the SQL.
_CUSTOMS_SORTS = {
    # NULL updated_at means "never modified"; SQLite sorts NULL lowest, so DESC
    # already puts those last, which is what v1 did.
    "recent": "c.updated_at DESC, c.name COLLATE NOCASE ASC",
    # rank is TEXT and often empty, so unranked characters go last rather than
    # sorting as zero.
    "rank_asc": "CASE WHEN c.rank = '' THEN 1 ELSE 0 END, CAST(c.rank AS INTEGER) ASC",
    "name_asc": "c.name COLLATE NOCASE ASC",
    "name_desc": "c.name COLLATE NOCASE DESC",
    "series_asc": "c.series COLLATE NOCASE ASC, c.name COLLATE NOCASE ASC",
    "count_desc": "image_count DESC, c.name COLLATE NOCASE ASC",
    "count_asc": "image_count ASC, c.name COLLATE NOCASE ASC",
}

CUSTOMS_SORT_KEYS = tuple(_CUSTOMS_SORTS)


def get_custom_image_stats() -> dict:
    """The two numbers the landing page shows.

    Previously the frontend downloaded every image URL for every character --
    around 475 KB -- and counted them in the browser.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS images, COUNT(DISTINCT character_id) AS characters"
        "  FROM custom_images WHERE state = 'active'"
    ).fetchone()
    return {"custom_images": row["images"], "characters_with_customs": row["characters"]}


def list_characters_with_customs(
    *,
    query: str = "",
    mode: str = "name",
    sort: str = "recent",
    page: int = 1,
    per_page: int = 20,
    preview_count: int = 3,
) -> dict:
    """One page of the browse-customs list, searched and sorted in SQL.

    Doing this in the browser meant shipping the entire library to render twenty
    rows, and it does not survive the roster growing -- the plan is to seed tens
    of thousands of characters, at which point client-side filtering stops being
    an option at all.
    """
    order_by = _CUSTOMS_SORTS.get(sort) or _CUSTOMS_SORTS["recent"]
    page = max(1, int(page))
    per_page = max(1, min(100, int(per_page)))

    column = "c.series" if mode == "series" else "c.name"
    term = (query or "").strip()
    where = "i.state = 'active'"
    params: list = []
    if term:
        # LIKE with COLLATE NOCASE rather than lower(): it uses the existing
        # NOCASE indexes on name and series.
        where += f" AND {column} LIKE ? ESCAPE '\\' COLLATE NOCASE"
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")

    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT c.id FROM characters c"
        "  JOIN custom_images i ON i.character_id = c.id"
        f" WHERE {where} GROUP BY c.id)",
        params,
    ).fetchone()["n"]

    rows = conn.execute(
        "SELECT c.id AS id, c.name AS name, c.series AS series, c.rank AS rank,"
        "       c.main_image_url AS image, COUNT(i.id) AS image_count"
        "  FROM characters c"
        "  JOIN custom_images i ON i.character_id = c.id"
        f" WHERE {where}"
        " GROUP BY c.id"
        f" ORDER BY {order_by}"
        " LIMIT ? OFFSET ?",
        (*params, per_page, (page - 1) * per_page),
    ).fetchall()

    items = [
        {
            "name": r["name"],
            "series": r["series"],
            "rank": r["rank"],
            "image": r["image"],
            "count": r["image_count"],
            "previews": [],
        }
        for r in rows
    ]

    # Previews for this page only, in one query rather than one per row.
    if rows and preview_count > 0:
        ids = [r["id"] for r in rows]
        by_id: dict[int, list[str]] = {i: [] for i in ids}
        placeholders = ",".join("?" for _ in ids)
        previews = conn.execute(
            "SELECT character_id, url FROM custom_images"
            f" WHERE state = 'active' AND character_id IN ({placeholders})"
            " ORDER BY character_id, position, id",
            ids,
        )
        for row in previews:
            bucket = by_id[row["character_id"]]
            if len(bucket) < preview_count:
                bucket.append(row["url"])
        for item, r in zip(items, rows, strict=True):
            item["previews"] = by_id[r["id"]]

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, -(-total // per_page)),
    }


def count_custom_images_ever(char_name: str) -> int:
    """How many images this character has *ever* had, removed ones included.

    Used to number uploads on ImgChest, and it deliberately ignores state.
    Counting only active images makes the number go down when one is removed, so
    the next upload reuses it — three uploads with a removal between each all
    came out as `lucy-118`. Nothing is ever hard-deleted, so counting every row
    gives a number that only ever climbs.

    The cost is that it drifts from the gallery position once images have been
    removed. That is the right way round: an ImgChest name is fixed at upload
    time and can never be corrected, so it should be a stable identifier rather
    than a position that was only briefly true.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM custom_images i"
        "  JOIN characters c ON c.id = i.character_id"
        " WHERE c.name = ?",
        (char_name,),
    ).fetchone()
    return int(row["n"])


def get_custom_image_rows(char_name: str, viewer_id: str | None = None) -> list[dict]:
    """Active images for a character, with ownership and this viewer's hidden set.

    Note what is *not* returned: `added_by` itself. Clients get the owner's
    handle and a boolean for "yours", never the raw id -- the id is the thing the
    identity cookie protects, and ownership can only be decided here anyway.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT i.id AS id, i.url AS url, i.added_by AS added_by,"
        "       i.width AS width, i.height AS height,"
        "       owner.handle AS owner_handle,"
        "       (hidden.image_id IS NOT NULL) AS is_hidden"
        "  FROM custom_images i"
        "  JOIN characters c ON c.id = i.character_id"
        "  LEFT JOIN identities owner ON owner.id = i.added_by"
        "  LEFT JOIN user_hidden hidden"
        "    ON hidden.image_id = i.id AND hidden.identity_id = ?"
        " WHERE c.name = ? AND i.state = 'active'"
        " ORDER BY i.position, i.id",
        (viewer_id, char_name),
    )
    return [
        {
            "id": r["id"],
            "url": r["url"],
            # NULL until the backfill has seen this image. The gallery falls back
            # to measuring on load, which is what it did before these existed.
            "width": r["width"],
            "height": r["height"],
            # What the grid renders. The `url` above stays canonical: it is what
            # every $ai command, download and lightbox uses, because Mudae
            # accepts nothing else.
            "thumb": thumbnails.thumb_url(r["id"], r["url"]),
            # NULL for images migrated from v1: nobody owns them, so nobody can
            # remove them except a moderator or the report threshold.
            "owner": r["owner_handle"],
            "is_mine": bool(viewer_id) and r["added_by"] == viewer_id,
            "hidden": bool(r["is_hidden"]),
        }
        for r in rows
    ]


def get_custom_images_for(char_name: str) -> list[str]:
    """Just the URLs, in order. For callers that do not care who owns what."""
    return [row["url"] for row in get_custom_image_rows(char_name)]


def add_custom_images(
    char_name: str,
    urls: Iterable[str],
    added_by: str | None = None,
    dimensions: dict[str, tuple[int, int]] | None = None,
) -> int:
    """Append images, skipping any URL already present. Returns how many landed.

    Two people adding at once no longer contend: these are separate INSERTs.

    `dimensions` maps url -> (width, height). Supplying it is what keeps the
    gallery from reflowing as images arrive; it is optional because the import
    paths do not always have the file to hand.
    """
    with transaction() as conn:
        char_id = _ensure_character(conn, char_name)
        # The identities row is created lazily, so it may not exist yet; without
        # this the added_by foreign key rejects the insert.
        if added_by is not None:
            _ensure_identity(conn, added_by)
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS p FROM custom_images WHERE character_id = ?",
            (char_id,),
        ).fetchone()
        position = int(row["p"]) + 1
        added = 0
        sizes = dimensions or {}
        for url in urls:
            width, height = sizes.get(url, (None, None))
            cur = conn.execute(
                "INSERT INTO custom_images"
                " (character_id, url, position, added_by, added_at, width, height)"
                " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (character_id, url) DO NOTHING",
                (char_id, url, position, added_by, _now(), width, height),
            )
            if cur.rowcount:
                position += 1
                added += 1
        conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))
        return added


def remove_custom_images(
    char_name: str,
    urls: Iterable[str],
    actor_id: str,
    *,
    is_moderator: bool = False,
    reason: str | None = None,
) -> dict | None:
    """Soft-delete images the actor is allowed to remove.

    This is the rule that makes griefing unimplementable rather than merely
    discouraged (DECISIONS.md section 1): **you can only remove images you
    added.** Moderators are the documented manual fallback, not the mechanism.

    Images migrated from v1 have `added_by IS NULL` -- nobody owns them, so no
    ordinary user can remove them. That is the intended outcome, not an
    oversight: the alternative is letting anyone delete the entire inherited
    library.

    Nothing is ever hard-deleted. ImgChest keeps the file regardless, so a
    removal is always restorable and the Removed drawer costs nothing.

    Returns None if the character is unknown, otherwise a report of what
    happened to each URL, so the caller can explain a partial refusal instead of
    silently dropping half the request.
    """
    doomed = list(dict.fromkeys(urls))
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return None
        result: dict[str, list[str]] = {"removed": [], "denied": [], "missing": []}
        if not doomed:
            return result

        placeholders = ",".join("?" for _ in doomed)
        rows = conn.execute(
            f"SELECT id, url, added_by FROM custom_images"
            f" WHERE character_id = ? AND state = 'active' AND url IN ({placeholders})",
            (char_id, *doomed),
        ).fetchall()
        by_url = {r["url"]: r for r in rows}

        removable = []
        for url in doomed:
            row = by_url.get(url)
            if row is None:
                result["missing"].append(url)
            elif is_moderator or (row["added_by"] is not None and row["added_by"] == actor_id):
                removable.append(row)
            else:
                result["denied"].append(url)

        if removable:
            _ensure_identity(conn, actor_id)
            now = _now()
            conn.executemany(
                "UPDATE custom_images"
                "   SET state = 'removed', removed_by = ?, removed_at = ?, removed_reason = ?"
                " WHERE id = ?",
                [(actor_id, now, reason, row["id"]) for row in removable],
            )
            conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (now, char_id))
            result["removed"] = [row["url"] for row in removable]
        return result


def get_image_url(image_id: int) -> str | None:
    """The source URL for one image row, whatever its state.

    Removed images keep their thumbnails working, which the Removed drawer needs.
    """
    conn = get_connection()
    row = conn.execute("SELECT url FROM custom_images WHERE id = ?", (image_id,)).fetchone()
    return row["url"] if row else None


def images_missing_dimensions(limit: int = 500, exclude_ids: Iterable[int] = ()) -> list[dict]:
    """Rows the backfill still has to measure.

    `exclude_ids` skips rows already tried and failed in this run. Without it a
    permanently unreadable image is returned by every batch forever — it never
    gets a width, so it always matches the filter — and the caller refetches it
    once per batch for the length of the run.
    """
    skip = list(dict.fromkeys(exclude_ids))
    conn = get_connection()
    if skip:
        placeholders = ",".join("?" for _ in skip)
        rows = conn.execute(
            "SELECT id, url FROM custom_images"
            f" WHERE (width IS NULL OR height IS NULL) AND id NOT IN ({placeholders})"
            " LIMIT ?",
            (*skip, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, url FROM custom_images WHERE width IS NULL OR height IS NULL LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "url": r["url"]} for r in rows]


def set_image_dimensions(sizes: dict[int, tuple[int, int]]) -> int:
    """Record measured dimensions. Returns how many rows were updated."""
    if not sizes:
        return 0
    with transaction() as conn:
        cur = conn.executemany(
            "UPDATE custom_images SET width = ?, height = ? WHERE id = ?",
            [(w, h, image_id) for image_id, (w, h) in sizes.items()],
        )
        return cur.rowcount


def get_removed_for(char_name: str) -> list[dict]:
    """The Removed drawer: everything soft-deleted for this character."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT i.id AS id, i.url AS url, i.removed_at AS removed_at,"
        "       i.removed_reason AS removed_reason,"
        "       remover.handle AS removed_by_handle"
        "  FROM custom_images i"
        "  JOIN characters c ON c.id = i.character_id"
        "  LEFT JOIN identities remover ON remover.id = i.removed_by"
        " WHERE c.name = ? AND i.state = 'removed'"
        " ORDER BY i.removed_at DESC, i.id DESC",
        (char_name,),
    )
    return [
        {
            "id": r["id"],
            "url": r["url"],
            "thumb": thumbnails.thumb_url(r["id"], r["url"]),
            "removed_by": r["removed_by_handle"],
            "removed_at": r["removed_at"],
            "reason": r["removed_reason"],
        }
        for r in rows
    ]


def restore_custom_images(char_name: str, urls: Iterable[str]) -> int:
    """Un-remove images. Returns how many came back.

    Deliberately open to anyone: restoring is not destructive, and a removal
    that was wrong should be cheap for the next person to undo.
    """
    wanted = list(dict.fromkeys(urls))
    if not wanted:
        return 0
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return 0
        placeholders = ",".join("?" for _ in wanted)
        cur = conn.execute(
            f"UPDATE custom_images"
            f"   SET state = 'active', removed_by = NULL, removed_at = NULL,"
            f"       removed_reason = NULL"
            f" WHERE character_id = ? AND state = 'removed' AND url IN ({placeholders})",
            (char_id, *wanted),
        )
        if cur.rowcount:
            conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))
        return cur.rowcount


# --- Hide for me --------------------------------------------------------
#
# The pressure valve. Instant, unlimited, and invisible to everyone else, which
# is what removes the reason to delete other people's images in the first place.


def hide_images(identity_id: str, image_ids: Iterable[int]) -> int:
    wanted = list(dict.fromkeys(image_ids))
    if not wanted:
        return 0
    with transaction() as conn:
        _ensure_identity(conn, identity_id)
        now = _now()
        cur = conn.executemany(
            "INSERT INTO user_hidden (identity_id, image_id, hidden_at) VALUES (?, ?, ?)"
            " ON CONFLICT (identity_id, image_id) DO NOTHING",
            [(identity_id, image_id, now) for image_id in wanted],
        )
        return cur.rowcount


def unhide_images(identity_id: str, image_ids: Iterable[int]) -> int:
    wanted = list(dict.fromkeys(image_ids))
    if not wanted:
        return 0
    with transaction() as conn:
        placeholders = ",".join("?" for _ in wanted)
        cur = conn.execute(
            f"DELETE FROM user_hidden WHERE identity_id = ? AND image_id IN ({placeholders})",
            (identity_id, *wanted),
        )
        return cur.rowcount


# --- Rate limiting ------------------------------------------------------

# Expired windows are swept at most this often, from whichever request happens
# to notice. A background job would be tidier but is not worth a process for a
# table this small.
_SWEEP_INTERVAL_SECONDS = 300
_last_sweep = 0.0


def _sweep_expired_rate_limits(conn: sqlite3.Connection, now: int) -> None:
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    # A day is comfortably longer than any window we use, so this only ever
    # removes rows nothing can still be counting against.
    conn.execute("DELETE FROM rate_limit_hits WHERE window_start < ?", (now - 86400,))


def check_rate_limit(
    identity_id: str, action: str, *, limit: int, per_seconds: int, now: int | None = None
) -> tuple[bool, int]:
    """Count one attempt. Returns (allowed, retry_after_seconds).

    The increment happens *before* the count is read, so two concurrent requests
    cannot both see "one under the limit" and both proceed. This is the same
    "let the write decide, then read the outcome" pattern `_ensure_character`
    uses, and for the same reason -- check-then-act is a race.

    A blocked attempt still counts. That is deliberate: a client retrying into a
    closed window should not get a free pass for doing so, and because the window
    end is fixed, `retry_after` stays honest either way.
    """
    now = int(time.time()) if now is None else int(now)
    window_start = now - (now % per_seconds)
    with transaction() as conn:
        _sweep_expired_rate_limits(conn, now)
        conn.execute(
            "INSERT INTO rate_limit_hits (identity_id, action, window_start, hits)"
            " VALUES (?, ?, ?, 1)"
            " ON CONFLICT (identity_id, action, window_start)"
            " DO UPDATE SET hits = hits + 1",
            (identity_id, action, window_start),
        )
        hits = conn.execute(
            "SELECT hits FROM rate_limit_hits"
            " WHERE identity_id = ? AND action = ? AND window_start = ?",
            (identity_id, action, window_start),
        ).fetchone()["hits"]

    if hits <= limit:
        return True, 0
    return False, max(1, window_start + per_seconds - now)


def rate_limit_usage(identity_id: str, action: str, per_seconds: int) -> int:
    """Attempts recorded in the current window. For tests and diagnostics."""
    now = int(time.time())
    window_start = now - (now % per_seconds)
    conn = get_connection()
    row = conn.execute(
        "SELECT hits FROM rate_limit_hits"
        " WHERE identity_id = ? AND action = ? AND window_start = ?",
        (identity_id, action, window_start),
    ).fetchone()
    return row["hits"] if row else 0


# --- Reports ------------------------------------------------------------
#
# Objective problems only: wrong character, dead link, NSFW, duplicate. Never
# taste -- that is what hide-for-me is for. The primary key on
# (image_id, identity_id) is what makes "two distinct reporters" meaningful:
# one person cannot reach the threshold alone.

REPORT_REASONS = ("wrong_character", "dead_link", "nsfw", "duplicate")

# Two, not more, because the userbase is too small to produce a larger quorum
# in any reasonable time (DECISIONS.md section 1). Removal is soft and anyone
# can restore, so the cost of a wrong call is low.
REPORT_REMOVAL_THRESHOLD = 2


def report_image(image_id: int, identity_id: str, reason: str) -> dict | None:
    """Record a report. Returns None if the image does not exist.

    Otherwise {'reports': n, 'removed': bool, 'already_reported': bool}. Removal
    happens on the second *distinct* reporter; a second report from the same
    person changes nothing, which is the point of the composite primary key.
    """
    if reason not in REPORT_REASONS:
        raise ValueError(f"Unknown report reason: {reason!r}")
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, character_id, state FROM custom_images WHERE id = ?", (image_id,)
        ).fetchone()
        if row is None:
            return None

        _ensure_identity(conn, identity_id)
        cur = conn.execute(
            "INSERT INTO image_reports (image_id, identity_id, reason, at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT (image_id, identity_id) DO NOTHING",
            (image_id, identity_id, reason, _now()),
        )
        already_reported = not cur.rowcount

        reports = conn.execute(
            "SELECT COUNT(*) AS n FROM image_reports WHERE image_id = ?", (image_id,)
        ).fetchone()["n"]

        removed = row["state"] == "removed"
        if not removed and reports >= REPORT_REMOVAL_THRESHOLD:
            now = _now()
            conn.execute(
                "UPDATE custom_images"
                "   SET state = 'removed', removed_at = ?, removed_reason = ?"
                " WHERE id = ?",
                (now, f"reported: {reason}", image_id),
            )
            # removed_by stays NULL: no single person made this call.
            conn.execute(
                "UPDATE characters SET updated_at = ? WHERE id = ?", (now, row["character_id"])
            )
            removed = True

        return {"reports": reports, "removed": removed, "already_reported": already_reported}


# --- Takes --------------------------------------------------------------


def log_take(image_id: int, identity_id: str | None, kind: str) -> bool:
    """Record that someone took an image away with them.

    Deliberately drives nothing. It is logged because collecting it costs
    nothing and keeps the option of designing a retirement policy later against
    real evidence rather than a guess -- see DECISIONS.md section 1, where
    retirement-by-disuse was rejected precisely for lack of that evidence.
    """
    if kind not in ("download", "copy_command"):
        raise ValueError(f"Unknown take kind: {kind!r}")
    with transaction() as conn:
        exists = conn.execute("SELECT 1 FROM custom_images WHERE id = ?", (image_id,)).fetchone()
        if exists is None:
            return False
        if identity_id is not None:
            _ensure_identity(conn, identity_id)
        conn.execute(
            "INSERT INTO image_takes (image_id, identity_id, kind, at) VALUES (?, ?, ?, ?)",
            (image_id, identity_id, kind, _now()),
        )
        return True


def reorder_custom_images(char_name: str, new_order: list[str]) -> bool:
    """Apply an ordering. False if the character is unknown.

    Only images that still exist are reordered, and any the client did not know
    about are kept at the end -- assigning the client's list wholesale used to
    delete images uploaded while the page was open.
    """
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return False
        rows = conn.execute(
            "SELECT url FROM custom_images WHERE character_id = ? AND state = 'active'"
            " ORDER BY position, id",
            (char_id,),
        ).fetchall()
        current = [r["url"] for r in rows]
        existing = set(current)
        requested = set(new_order)
        ordered = [url for url in new_order if url in existing]
        ordered.extend(url for url in current if url not in requested)
        for position, url in enumerate(ordered):
            conn.execute(
                "UPDATE custom_images SET position = ? WHERE character_id = ? AND url = ?",
                (position, char_id, url),
            )
        conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))
        return True


# --- Bookmarks ----------------------------------------------------------


def get_saved_characters(identity_id: str = LEGACY_IDENTITY_ID) -> list:
    """Bookmarks, most recently updated first.

    The timestamp comes back with each row so the client does not have to fetch
    a last-updated map for all ~700 characters just to order a handful of
    bookmarks. NULL updated_at means never modified, and SQLite sorts NULL
    lowest, so DESC already puts those last.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT c.name AS name, c.series AS series, c.rank AS rank,"
        "       c.main_image_url AS image, c.updated_at AS updated_at"
        "  FROM saved s JOIN characters c ON c.id = s.character_id"
        " WHERE s.identity_id = ?"
        " ORDER BY c.updated_at DESC, s.created_at DESC",
        (identity_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _ensure_identity(conn: sqlite3.Connection, identity_id: str, handle: str | None = None) -> None:
    """Create the row if this is the identity's first write.

    Rows are created lazily: a cookie is issued to every visitor, but only
    someone who actually stores something needs a row. INSERT-then-ignore rather
    than check-then-insert, for the usual reason.
    """
    if handle is None:
        handle = identity.handle_for(identity_id)
    conn.execute(
        "INSERT INTO identities (id, handle) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
        (identity_id, handle),
    )


def ensure_identity(identity_id: str, handle: str | None = None) -> None:
    """Public form of the above, for callers outside a transaction."""
    with transaction() as conn:
        _ensure_identity(conn, identity_id, handle)


def get_identity(identity_id: str) -> dict | None:
    """The stored row, or None if this identity has never written anything."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, handle, discord_id, role, created_at FROM identities WHERE id = ?",
        (identity_id,),
    ).fetchone()
    return dict(row) if row else None


def _merge_identity(conn: sqlite3.Connection, source: str, target: str) -> dict:
    """Move everything owned by `source` onto `target`, then delete `source`.

    Used when someone signs in on a browser holding a fresh anonymous identity
    and Discord says they are an account bound to an older one. Without this,
    uploading and then signing in would silently orphan what you just added --
    exactly the frustration this phase exists to remove.

    UPDATE OR IGNORE on the three tables with composite primary keys: you may
    already have hidden or reported the same image from the other browser, and
    the collision means the target already has the row. Whatever the update
    skips is deleted afterwards rather than left pointing at a dead identity.
    """
    moved = {}
    for table, column in (("custom_images", "added_by"), ("custom_images", "removed_by")):
        cur = conn.execute(f"UPDATE {table} SET {column} = ? WHERE {column} = ?", (target, source))
        moved[column] = cur.rowcount

    for table in ("saved", "user_hidden", "image_reports"):
        cur = conn.execute(
            f"UPDATE OR IGNORE {table} SET identity_id = ? WHERE identity_id = ?",
            (target, source),
        )
        moved[table] = cur.rowcount
        conn.execute(f"DELETE FROM {table} WHERE identity_id = ?", (source,))

    cur = conn.execute(
        "UPDATE image_takes SET identity_id = ? WHERE identity_id = ?", (target, source)
    )
    moved["image_takes"] = cur.rowcount

    # Not carried over. These are ephemeral counters that the sweep would drop
    # anyway, and merging two identities' buckets would punish the account for
    # the anonymous session's usage.
    conn.execute("DELETE FROM rate_limit_hits WHERE identity_id = ?", (source,))
    conn.execute("DELETE FROM identities WHERE id = ?", (source,))
    return moved


def bind_discord_identity(
    current_id: str, discord_id: str, *, display_name: str = "", owner_discord_id: str = ""
) -> dict:
    """Attach a Discord account to an identity, adopting an existing one if there is one.

    Returns {'identity_id', 'merged', 'role'} -- `identity_id` is who the caller
    is from now on, which may not be who they were a moment ago.
    """
    with transaction() as conn:
        _ensure_identity(conn, current_id)
        existing = conn.execute(
            "SELECT id FROM identities WHERE discord_id = ?", (discord_id,)
        ).fetchone()

        merged = False
        if existing is None:
            target = current_id
            conn.execute(
                "UPDATE identities SET discord_id = ? WHERE id = ?", (discord_id, current_id)
            )
        else:
            target = existing["id"]
            if target != current_id:
                _merge_identity(conn, current_id, target)
                merged = True

        if display_name:
            conn.execute("UPDATE identities SET handle = ? WHERE id = ?", (display_name, target))

        # The owner is bootstrapped by matching an environment variable at login,
        # so there is no admin password anywhere and no chicken-and-egg problem.
        # Only ever promotes: signing in must not demote an existing moderator.
        if owner_discord_id and discord_id == owner_discord_id:
            conn.execute(
                "UPDATE identities SET role = 'owner' WHERE id = ? AND role != 'owner'",
                (target,),
            )

        role = conn.execute("SELECT role FROM identities WHERE id = ?", (target,)).fetchone()[
            "role"
        ]
        return {"identity_id": target, "merged": merged, "role": role}


def set_role(identity_id: str, role: str) -> bool:
    """Promote or demote. Owner-only at the route level."""
    if role not in ("user", "moderator", "owner"):
        raise ValueError(f"Unknown role: {role!r}")
    with transaction() as conn:
        cur = conn.execute("UPDATE identities SET role = ? WHERE id = ?", (role, identity_id))
        return bool(cur.rowcount)


def save_character(char_name: str, identity_id: str = LEGACY_IDENTITY_ID) -> bool:
    """False if already bookmarked by this identity."""
    with transaction() as conn:
        _ensure_identity(conn, identity_id)
        char_id = _ensure_character(conn, char_name)
        cur = conn.execute(
            "INSERT INTO saved (identity_id, character_id, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT (identity_id, character_id) DO NOTHING",
            (identity_id, char_id, _now()),
        )
        return bool(cur.rowcount)


def unsave_character(char_name: str, identity_id: str = LEGACY_IDENTITY_ID) -> bool:
    """False if it was not bookmarked."""
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return False
        cur = conn.execute(
            "DELETE FROM saved WHERE identity_id = ? AND character_id = ?",
            (identity_id, char_id),
        )
        return bool(cur.rowcount)
