"""Test harness.

SAFETY, READ THIS FIRST
-----------------------
`upload_imgchest.py` calls `load_dotenv()` at import time, and `.env` holds the
PRODUCTION Neon `DATABASE_URL`. Importing the application in a test therefore
points it at live user data, and a write test would corrupt it.

Two things prevent that, and neither should be removed:

1. `DATABASE_URL` is overwritten here at collection time, before any application
   module is imported. `load_dotenv()` defaults to `override=False`, so it will
   not clobber a value that is already set.
2. `_assert_not_production()` refuses to run at all unless the URL resolves to a
   local host, and rejects known managed-database hostnames outright.
"""

import os
import socket
import subprocess
import time
from urllib.parse import urlparse

import pytest

CONTAINER_NAME = "imgmgr-pgtest"
CONTAINER_PORT = 55432
DEFAULT_TEST_URL = f"postgresql://postgres:test@127.0.0.1:{CONTAINER_PORT}/imgmgr_test"

# Substrings that indicate a hosted database. Never run tests against these.
_PRODUCTION_MARKERS = (
    "neon.tech",
    "amazonaws.com",
    "supabase.co",
    "render.com",
    "digitalocean.com",
    "azure.com",
    "googleapis.com",
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.containers.internal"}


def _assert_not_production(url: str) -> None:
    """Abort the whole run rather than risk touching live data."""
    lowered = url.lower()
    for marker in _PRODUCTION_MARKERS:
        if marker in lowered:
            raise pytest.UsageError(
                f"Refusing to run tests: DATABASE_URL points at '{marker}', which looks "
                f"like a production database. Set TEST_DATABASE_URL to a local database."
            )
    host = urlparse(url).hostname or ""
    if host not in _LOCAL_HOSTS:
        raise pytest.UsageError(
            f"Refusing to run tests: database host '{host}' is not local. "
            f"Tests may only run against localhost."
        )


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_container() -> None:
    """Start a throwaway Postgres. Reuses one that is already running."""
    if _port_open(CONTAINER_PORT):
        return
    subprocess.run(["podman", "rm", "-f", CONTAINER_NAME], capture_output=True, check=False)
    result = subprocess.run(
        [
            "podman",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-e",
            "POSTGRES_PASSWORD=test",
            "-e",
            "POSTGRES_DB=imgmgr_test",
            "-p",
            f"{CONTAINER_PORT}:5432",
            "docker.io/library/postgres:16-alpine",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise pytest.UsageError(
            "Could not start the test database.\n"
            f"podman said: {result.stderr.strip()}\n\n"
            "Either start podman, or point TEST_DATABASE_URL at a local Postgres."
        )
    for _ in range(60):
        if _port_open(CONTAINER_PORT):
            time.sleep(0.5)  # accepting connections is not the same as ready
            return
        time.sleep(0.5)
    raise pytest.UsageError("Test database did not become ready within 30s.")


def pytest_configure(config):
    """Runs before test modules are imported, which is what makes the guard work."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        _start_container()
        url = DEFAULT_TEST_URL
    _assert_not_production(url)
    os.environ["DATABASE_URL"] = url
    # Keep the app from needing real credentials for unrelated services.
    os.environ.setdefault("IMGCHEST_API_KEY", "test-key-not-real")
    os.environ.setdefault("SECRET_KEY", "test-secret-not-real")


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ["DATABASE_URL"]


@pytest.fixture
def clean_db(database_url):
    """A database with the schema present and every table empty.

    Yields the `db` module. Import happens inside the fixture so that even an
    accidental module-level import in a test file cannot dodge the guard above.
    """
    import db as db_module

    # Belt and braces: verify what the application actually resolved to.
    _assert_not_production(os.environ["DATABASE_URL"])

    db_module._reset_db()
    _, conn = db_module._get_db()  # also creates the schema
    with conn.cursor() as cur:
        cur.execute("TRUNCATE kv_store")
    yield db_module
    db_module._reset_db()
