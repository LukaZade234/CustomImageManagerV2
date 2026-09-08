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
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

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


def get_custom_images() -> dict:
    """{name: [url, ...]} for every character with active images.

    Same shape v1 served at /custom_images.json. Phase 9 replaces this endpoint
    with per-character fetches plus a stats endpoint.
    """
    conn = get_connection()
    out: dict[str, list[str]] = {}
    rows = conn.execute(
        "SELECT c.name AS name, i.url AS url"
        "  FROM custom_images i JOIN characters c ON c.id = i.character_id"
        " WHERE i.state = 'active'"
        " ORDER BY c.name, i.position, i.id"
    )
    for row in rows:
        out.setdefault(row["name"], []).append(row["url"])
    return out


def get_custom_images_for(char_name: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT i.url AS url"
        "  FROM custom_images i JOIN characters c ON c.id = i.character_id"
        " WHERE c.name = ? AND i.state = 'active'"
        " ORDER BY i.position, i.id",
        (char_name,),
    )
    return [r["url"] for r in rows]


def add_custom_images(char_name: str, urls: Iterable[str], added_by: str | None = None) -> int:
    """Append images, skipping any URL already present. Returns how many landed.

    Two people adding at once no longer contend: these are separate INSERTs.
    """
    with transaction() as conn:
        char_id = _ensure_character(conn, char_name)
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS p FROM custom_images WHERE character_id = ?",
            (char_id,),
        ).fetchone()
        position = int(row["p"]) + 1
        added = 0
        for url in urls:
            cur = conn.execute(
                "INSERT INTO custom_images (character_id, url, position, added_by, added_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT (character_id, url) DO NOTHING",
                (char_id, url, position, added_by, _now()),
            )
            if cur.rowcount:
                position += 1
                added += 1
        conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))
        return added


def delete_custom_images(char_name: str, urls: Iterable[str]) -> str:
    """Remove images. Returns 'no_character', 'no_match' or 'deleted'.

    Hard delete for now; Phase 6 turns this into a soft delete by setting
    `state='removed'` so the Removed drawer can restore it.
    """
    doomed = list(urls)
    with transaction() as conn:
        char_id = _character_id(conn, char_name)
        if char_id is None:
            return "no_character"
        if not doomed:
            return "no_match"
        placeholders = ",".join("?" for _ in doomed)
        cur = conn.execute(
            f"DELETE FROM custom_images WHERE character_id = ? AND url IN ({placeholders})",
            (char_id, *doomed),
        )
        if not cur.rowcount:
            return "no_match"
        conn.execute("UPDATE characters SET updated_at = ? WHERE id = ?", (_now(), char_id))
        return "deleted"


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
    conn = get_connection()
    rows = conn.execute(
        "SELECT c.name AS name, c.series AS series, c.rank AS rank,"
        "       c.main_image_url AS image"
        "  FROM saved s JOIN characters c ON c.id = s.character_id"
        " WHERE s.identity_id = ? ORDER BY s.created_at",
        (identity_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _ensure_identity(conn: sqlite3.Connection, identity_id: str) -> None:
    conn.execute(
        "INSERT INTO identities (id, handle) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
        (identity_id, "Legacy"),
    )


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
