"""Database layer for user data. Requires PostgreSQL (DATABASE_URL).

Concurrency
-----------
Every stored document is a whole JSON blob, so any change is a read-modify-write.
Doing that as two separate calls -- `get_x()`, mutate, `set_x()` -- loses data
whenever two requests overlap: both read the same document and the second write
discards the first. That was a live bug; `tests/test_db_concurrency.py` proves it.

The fix is that **there is no public setter**. The only way to change a document
is `mutate_*`, which takes a transaction, takes a Postgres advisory lock on the
key, then reads, applies the caller's function and writes -- all atomically. The
unsafe pattern is therefore not merely discouraged, it is unavailable.

The advisory lock serialises writes per key rather than per character. At this
scale that is the right trade: it is simple and obviously correct, and Phase 3
replaces the blob with one row per image, after which writes stop contending at
all.
"""

import atexit
import os
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


class DatabaseConfigurationError(RuntimeError):
    """Raised when DATABASE_URL is not set or PostgreSQL is unavailable."""


_pool: ConnectionPool | None = None

# Per worker process. Gunicorn runs several, so keep this modest.
_POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "5"))


def _normalise_url(url: str) -> str:
    return "postgresql://" + url[11:] if url.startswith("postgres://") else url


def _get_pool() -> ConnectionPool:
    """Lazily create the pool. The pool handles reconnection, so the old
    single global connection, its lock and its keepalive thread are all gone."""
    global _pool
    if _pool is not None:
        return _pool

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DatabaseConfigurationError(
            "DATABASE_URL is not set. Configure PostgreSQL and set DATABASE_URL."
        )

    pool = ConnectionPool(
        _normalise_url(url),
        min_size=_POOL_MIN,
        max_size=_POOL_MAX,
        # Hand out only connections that are actually alive, so a database
        # restart or an idle timeout surfaces as a retry rather than an error.
        check=ConnectionPool.check_connection,
        open=False,
        name="imgmanager",
    )
    pool.open(wait=True, timeout=30)
    _pool = pool
    # Without this, the pool's worker and scheduler threads outlive the process
    # and every gunicorn worker restart stalls for ~5s per thread while logging
    # "couldn't stop thread ... within 5.0 seconds". Gunicorn's SIGTERM handler
    # exits via SystemExit, so atexit callbacks do run on a graceful restart.
    atexit.register(_reset_pool)
    _init_schema()
    return _pool


def _reset_pool() -> None:
    """Close the pool. Used by tests between cases."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None


# Kept under the old name because tests and callers already use it.
_reset_db = _reset_pool


def _init_schema() -> None:
    with _pool.connection() as conn, conn.cursor() as cur:  # type: ignore[union-attr]
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value JSONB NOT NULL)"
        )


@contextmanager
def transaction():
    """A connection inside a transaction: commits on success, rolls back on error."""
    with _get_pool().connection() as conn:
        yield conn


def _lock_id(key: str) -> int:
    """Stable across processes and restarts, unlike the built-in hash()."""
    return zlib.crc32(key.encode("utf-8"))


def read[T](key: str, default: T) -> T:
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def mutate[T](key: str, default: T, fn: Callable[[T], Any]) -> Any:
    """Atomically read-modify-write one document.

    `fn` receives the current value and **mutates it in place**; whatever it
    returns is passed back to the caller. The document written is always the
    object handed to `fn`.

    The advisory lock is taken before the read so that two concurrent callers
    cannot both observe the pre-change state. It is released automatically when
    the transaction ends, including on rollback.
    """
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_lock_id(key),))
        cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
        row = cur.fetchone()
        data = row[0] if row else default
        result = fn(data)
        cur.execute(
            "INSERT INTO kv_store (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, Jsonb(data)),
        )
        return result


# --- Custom images: {char_name: [url, ...]} ---


def get_custom_images() -> dict:
    return read("custom_images", {})


def mutate_custom_images(fn: Callable[[dict], Any]) -> Any:
    return mutate("custom_images", {}, fn)


# --- Saved characters (bookmarks) ---


def get_saved_characters() -> list:
    return read("saved_characters", [])


def mutate_saved_characters(fn: Callable[[list], Any]) -> Any:
    return mutate("saved_characters", [], fn)


# --- Last updated: {char_name: unix_timestamp} ---


def get_last_updated() -> dict:
    raw = read("last_updated", {})
    return raw if isinstance(raw, dict) else {}


def mutate_last_updated(fn: Callable[[dict], Any]) -> Any:
    return mutate("last_updated", {}, fn)


def update_last_modified(char_name: str) -> None:
    import time

    stamp = time.time()
    mutate_last_updated(lambda data: data.__setitem__(char_name, stamp))


# --- Characters: [{name, series, rank, main_image_url}] ---


def get_characters() -> list | None:
    """API shape. Returns None when the table has not been seeded yet."""
    raw = read("characters", None)
    if raw is None:
        return None
    chars = raw if isinstance(raw, list) else []
    return [
        {
            "name": c["name"],
            "series": c.get("series", ""),
            "rank": c.get("rank", ""),
            "image": c.get("main_image_url", ""),
        }
        for c in chars
    ]


def mutate_characters(fn: Callable[[list], Any]) -> Any:
    return mutate("characters", [], fn)


def add_character(name: str, series: str, rank: str, main_image_url: str = "") -> bool:
    """Add a character. Returns False if the name already exists."""

    def _add(chars: list) -> bool:
        if any(c.get("name") == name for c in chars):
            return False
        chars.append(
            {"name": name, "series": series, "rank": rank, "main_image_url": main_image_url}
        )
        return True

    return mutate_characters(_add)


def update_character(orig_name: str, new_name: str, series: str, rank: str) -> bool:
    """Update a character. Returns False if orig_name was not found."""

    def _update(chars: list) -> bool:
        for c in chars:
            if c.get("name") == orig_name:
                c["name"] = new_name
                c["series"] = series
                c["rank"] = rank
                return True
        return False

    return mutate_characters(_update)


def set_main_image(char_name: str, image_url: str) -> bool:
    """Set a character's main image. Returns False if not found."""

    def _set(chars: list) -> bool:
        for c in chars:
            if c.get("name") == char_name:
                c["main_image_url"] = image_url
                return True
        return False

    return mutate_characters(_set)
