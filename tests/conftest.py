"""Test harness.

SAFETY, READ THIS FIRST
-----------------------
The hazard changed shape in Phase 3 but did not go away. It used to be "the app
calls load_dotenv() at import and .env holds the production Neon URL, so an
unguarded test would write to live user data". Now the database is a local file
and the risk is writing to the *working* database instead of a throwaway one --
still destructive, just quieter.

Two things prevent it, and neither should be removed:

1. `DATABASE_PATH` is **always** overwritten at collection time, before any
   application module is imported, so a value inherited from the environment or
   from `.env` cannot reach the app.
2. To point the suite at your own database, set `TEST_DATABASE_PATH` -- which is
   opt-in and validated. `_assert_disposable()` refuses to run if the path is the
   working database, or is anywhere outside a temporary directory.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMPDIR: str | None = None


def _assert_disposable(path: Path) -> None:
    """Abort the run rather than risk writing to a database someone cares about."""
    resolved = path.resolve()
    default = (Path(__file__).resolve().parent.parent / "data" / "imgmanager.db").resolve()
    if resolved == default:
        raise pytest.UsageError(
            f"Refusing to run tests against the working database at {resolved}. "
            f"Unset TEST_DATABASE_PATH and let the harness create a temporary one."
        )
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if tmp_root not in resolved.parents:
        raise pytest.UsageError(
            f"Refusing to run tests against {resolved}: it is not inside "
            f"{tmp_root}. Tests may only touch a throwaway database."
        )


def pytest_configure(config):
    """Runs before test modules are imported, which is what makes the guard work."""
    global _TMPDIR
    override = os.environ.get("TEST_DATABASE_PATH")
    if override:
        path = Path(override)
    else:
        _TMPDIR = tempfile.mkdtemp(prefix="imgmanager-tests-")
        path = Path(_TMPDIR) / "test.db"
    # Validated whether it came from the environment or from us. DATABASE_PATH is
    # overwritten unconditionally below so no inherited value survives.
    _assert_disposable(path)
    os.environ["DATABASE_PATH"] = str(path)
    # Keep the app from needing real credentials for unrelated services.
    os.environ.setdefault("IMGCHEST_API_KEY", "test-key-not-real")
    os.environ.setdefault("SECRET_KEY", "test-secret-not-real")


def pytest_unconfigure(config):
    if _TMPDIR and os.path.isdir(_TMPDIR):
        shutil.rmtree(_TMPDIR, ignore_errors=True)


@pytest.fixture
def clean_db():
    """An empty database with the schema applied.

    Imported inside the fixture so that even an accidental module-level import in
    a test file cannot dodge the guard above.
    """
    import db as db_module

    _assert_disposable(db_module.database_path())

    db_module._reset_db()
    path = db_module.database_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()

    # Opening the connection applies the migrations.
    db_module.get_connection()
    yield db_module
    db_module._reset_db()


@pytest.fixture
def client(clean_db):
    """Flask test client against the clean test database."""
    from upload_imgchest import app

    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def identity_id(client):
    """The identity id behind the test client's cookie.

    Tests need this to seed images *owned by the caller*, since the ownership
    rule is the thing under test. It is deliberately awkward to obtain -- the
    cookie is HttpOnly and /api/me does not return the id -- so it is unwrapped
    here once rather than in every test.
    """
    from flask import current_app

    import identity as identity_module
    from upload_imgchest import app

    client.get("/api/me")
    with app.app_context():
        token = client.get_cookie(identity_module.COOKIE_NAME).value
        return identity_module.unsign(token, current_app.config["SECRET_KEY"])


@pytest.fixture
def make_moderator(clean_db, identity_id):
    """Promote the test client's identity. Returns the callable, not the effect."""

    def promote(role="moderator"):
        clean_db.ensure_identity(identity_id)
        with clean_db.transaction() as conn:
            conn.execute("UPDATE identities SET role = ? WHERE id = ?", (role, identity_id))

    return promote
