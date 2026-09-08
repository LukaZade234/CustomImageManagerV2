"""CORS behaviour for the split-origin deployment.

The SPA is served by Cloudflare Pages and the API lives on a different origin, so
every request is cross-origin and must carry the identity cookie. That means
credentialed CORS, and browsers refuse credentialed requests against a wildcard
origin -- a combination that fails silently in the browser rather than raising
anything server-side, which is why the app refuses it at startup instead.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _import_app_with(env_extra: dict) -> subprocess.CompletedProcess:
    """Import the app in a subprocess, since the CORS check runs at import time."""
    env = {
        "PATH": "/usr/bin:/bin",
        "IMGCHEST_API_KEY": "test",
        "SECRET_KEY": "test",
        "DATABASE_PATH": "/tmp/imgmanager-cors-check.db",
        **env_extra,
    }
    return subprocess.run(
        [sys.executable, "-c", "import upload_imgchest"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


def test_wildcard_origin_is_refused_at_startup():
    result = _import_app_with({"CORS_ORIGINS": "*"})
    assert result.returncode != 0, "the app started with CORS_ORIGINS='*'"
    assert "not allowed" in result.stderr
    assert "credential" in result.stderr.lower()


def test_explicit_origins_are_accepted():
    result = _import_app_with({"CORS_ORIGINS": "https://img.example.com"})
    assert result.returncode == 0, result.stderr


def test_unset_origins_is_accepted_as_same_origin_only():
    result = _import_app_with({})
    assert result.returncode == 0, result.stderr


@pytest.fixture
def cors_client(clean_db, monkeypatch):
    """A client whose app was configured with one allowed origin."""
    import importlib

    monkeypatch.setenv("CORS_ORIGINS", "https://img.example.com")
    import upload_imgchest

    importlib.reload(upload_imgchest)
    upload_imgchest.app.config.update(TESTING=True)
    with upload_imgchest.app.test_client() as c:
        yield c
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    importlib.reload(upload_imgchest)


def test_allowed_origin_gets_credentialed_cors_headers(cors_client):
    r = cors_client.get("/api/health", headers={"Origin": "https://img.example.com"})
    assert r.headers.get("Access-Control-Allow-Origin") == "https://img.example.com"
    assert r.headers.get("Access-Control-Allow-Credentials") == "true"
    # Never a wildcard: browsers reject that alongside credentials.
    assert r.headers.get("Access-Control-Allow-Origin") != "*"


def test_disallowed_origin_gets_no_cors_headers(cors_client):
    r = cors_client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("Access-Control-Allow-Origin") is None
