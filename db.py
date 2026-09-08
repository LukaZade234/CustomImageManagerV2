"""
Database layer for user data. Requires PostgreSQL (DATABASE_URL).
"""
import json
import os
import threading
import time
from typing import Callable, TypeVar

_T = TypeVar("_T")


class DatabaseConfigurationError(RuntimeError):
    """Raised when DATABASE_URL is not set or PostgreSQL is unavailable."""

_db = None
_db_lock = threading.Lock()
_keepalive_thread = None


def _reset_db():
    """Clear cached DB connection (e.g., after stale connection)."""
    global _db
    with _db_lock:
        if _db is not None:
            try:
                _db[1].close()
            except Exception:
                pass
        _db = None


def _is_connection_error(exc):
    """Check if exception indicates a stale/failed DB connection."""
    ename = type(exc).__name__
    return ename in ('OperationalError', 'InterfaceError', 'DatabaseError')


# Keepalive interval (seconds) - ping DB before server closes idle connections (~5 min typical)
_KEEPALIVE_INTERVAL = 4 * 60


def _keepalive_loop():
    """Background thread: ping DB periodically so connection never goes idle."""
    global _db
    while True:
        time.sleep(_KEEPALIVE_INTERVAL)
        with _db_lock:
            if _db is None:
                return
            conn = _db[1]
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:
            _reset_db()  # Next request will reconnect


def _start_keepalive():
    """Start background keepalive thread for PostgreSQL."""
    global _keepalive_thread
    if _keepalive_thread is not None and _keepalive_thread.is_alive():
        return
    _keepalive_thread = threading.Thread(target=_keepalive_loop, daemon=True)
    _keepalive_thread.start()


def _get_db():
    """Get PostgreSQL connection. Requires DATABASE_URL."""
    global _db
    with _db_lock:
        if _db is not None:
            return _db
        url = os.environ.get('DATABASE_URL')
        if not url:
            raise DatabaseConfigurationError(
                'DATABASE_URL is not set. Configure PostgreSQL (e.g. on DigitalOcean) and set DATABASE_URL.'
            )
        import psycopg2
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[11:]
        conn = psycopg2.connect(
            url,
            keepalives=1,
            keepalives_idle=60,
            keepalives_interval=30,
            keepalives_count=5,
        )
        conn.autocommit = True
        _init_postgres(conn)
        _db = ('postgres', conn)
        _start_keepalive()
        return _db


def _init_postgres(conn):
    """Create kv_store table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL
            )
        """)


def _get_pg(conn, key, default):
    """Read from PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def _set_pg(conn, key, value):
    """Write to PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO kv_store (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, json.dumps(value))
        )


def _with_retry(fn: Callable[[], _T]) -> _T:
    """Execute fn() and retry once on connection error (stale PostgreSQL)."""
    for attempt in range(2):
        try:
            return fn()
        except Exception as e:
            if attempt == 0 and _is_connection_error(e):
                _reset_db()
                continue
            raise
    raise AssertionError("_with_retry: exhausted retries without return")


def get_custom_images():
    """Get {char_name: [url1, url2, ...]}."""
    def _do():
        _, conn = _get_db()
        return _get_pg(conn, 'custom_images', {})
    return _with_retry(_do)


def set_custom_images(data):
    """Save custom_images."""
    def _do():
        _, conn = _get_db()
        _set_pg(conn, 'custom_images', data)
    _with_retry(_do)


def get_saved_characters():
    """Get list of saved character objects."""
    def _do():
        _, conn = _get_db()
        return _get_pg(conn, 'saved_characters', [])
    return _with_retry(_do)


def set_saved_characters(data):
    """Save saved_characters."""
    def _do():
        _, conn = _get_db()
        _set_pg(conn, 'saved_characters', data)
    _with_retry(_do)


def get_last_updated():
    """Get {char_name: timestamp, ...}."""
    def _do():
        _, conn = _get_db()
        raw = _get_pg(conn, 'last_updated', {})
        return raw if isinstance(raw, dict) else {}

    return _with_retry(_do)


def set_last_updated(data):
    """Save last_updated."""
    def _do():
        _, conn = _get_db()
        _set_pg(conn, 'last_updated', data)
    _with_retry(_do)


def update_last_modified(char_name):
    """Update timestamp for a character."""
    import time
    data = get_last_updated()
    data[char_name] = time.time()
    set_last_updated(data)


# --- Characters (name, series, rank, main_image_url) ---

def get_characters():
    """Get list of characters as [{name, series, rank, image}, ...] for API."""
    def _do():
        _, conn = _get_db()
        raw = _get_pg(conn, 'characters', None)
        if raw is None:
            return None  # Not yet migrated
        chars = raw if isinstance(raw, list) else []
        return [{'name': c['name'], 'series': c.get('series', ''), 'rank': c.get('rank', ''), 'image': c.get('main_image_url', '')} for c in chars]
    return _with_retry(_do)


def _get_characters_raw():
    """Get raw character list (internal)."""
    def _do():
        _, conn = _get_db()
        raw = _get_pg(conn, 'characters', [])
        return raw if isinstance(raw, list) else []
    return _with_retry(_do)


def _set_characters_raw(chars):
    """Save raw character list (internal)."""
    def _do():
        _, conn = _get_db()
        _set_pg(conn, 'characters', chars)
    _with_retry(_do)


def add_character(name, series, rank, main_image_url=''):
    """Add a character. Returns False if name already exists."""
    chars = _get_characters_raw()
    if any(c.get('name') == name for c in chars):
        return False
    chars.append({'name': name, 'series': series, 'rank': rank, 'main_image_url': main_image_url})
    _set_characters_raw(chars)
    return True


def update_character(orig_name, new_name, series, rank):
    """Update character. Returns False if orig_name not found."""
    chars = _get_characters_raw()
    for c in chars:
        if c.get('name') == orig_name:
            c['name'] = new_name
            c['series'] = series
            c['rank'] = rank
            _set_characters_raw(chars)
            return True
    return False


def set_main_image(char_name, image_url):
    """Set main image for character. Returns False if not found."""
    chars = _get_characters_raw()
    for c in chars:
        if c.get('name') == char_name:
            c['main_image_url'] = image_url
            _set_characters_raw(chars)
            return True
    return False
