"""Deployment path guards.

`DATABASE_PATH` and `THUMB_DIR` both default to directories inside the code tree
so a fresh checkout needs no configuration. In production that tree is mounted
read-only (`ProtectSystem=strict`), so a default left in place fails at the
*first write* rather than at startup -- the same shape as the uploads bug, which
worked locally and failed on the server for every request.

The guard fires only for a deployed configuration (CORS_ORIGINS set), the same
signal `resolve_secret_key` uses, so local development keeps its defaults.
"""

import subprocess
import sys
from pathlib import Path

import pytest

import upload_imgchest

REPO = Path(__file__).resolve().parent.parent


def _import_app_with(env_extra: dict) -> subprocess.CompletedProcess:
    """Import the app in a subprocess, since the guard runs at import time."""
    env = {
        "PATH": "/usr/bin:/bin",
        "IMGCHEST_API_KEY": "test",
        "SECRET_KEY": "test",
        "DATABASE_PATH": "/tmp/imgmanager-deploy-check.db",
        "THUMB_DIR": "/tmp/imgmanager-deploy-thumbs",
        **env_extra,
    }
    return subprocess.run(
        [sys.executable, "-c", "import upload_imgchest"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


class TestGuardDeployedPaths:
    def test_local_configuration_keeps_the_in_tree_defaults(self, monkeypatch):
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        monkeypatch.setenv("DATABASE_PATH", str(REPO / "data" / "imgmanager.db"))
        monkeypatch.setenv("THUMB_DIR", str(REPO / "data" / "thumbs"))
        upload_imgchest._guard_deployed_paths()  # must not raise

    def test_deployed_configuration_refuses_an_in_tree_database_path(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://img.example.com")
        monkeypatch.setenv("DATABASE_PATH", str(REPO / "data" / "imgmanager.db"))
        monkeypatch.setenv("THUMB_DIR", "/tmp/imgmanager-thumbs")
        with pytest.raises(RuntimeError, match="DATABASE_PATH"):
            upload_imgchest._guard_deployed_paths()

    def test_deployed_configuration_refuses_an_in_tree_thumb_dir(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://img.example.com")
        monkeypatch.setenv("DATABASE_PATH", "/tmp/imgmanager-deploy.db")
        monkeypatch.setenv("THUMB_DIR", str(REPO / "data" / "thumbs"))
        with pytest.raises(RuntimeError, match="THUMB_DIR"):
            upload_imgchest._guard_deployed_paths()

    def test_deployed_configuration_accepts_paths_outside_the_tree(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://img.example.com")
        monkeypatch.setenv("DATABASE_PATH", "/var/lib/imgmanager/imgmanager.db")
        monkeypatch.setenv("THUMB_DIR", "/var/lib/imgmanager/thumbs")
        upload_imgchest._guard_deployed_paths()  # must not raise


def test_startup_refuses_a_deployed_config_with_a_relative_default():
    """The guard is wired at import time, not merely available."""
    result = _import_app_with(
        {"CORS_ORIGINS": "https://img.example.com", "DATABASE_PATH": "data/imgmanager.db"}
    )
    assert result.returncode != 0
    assert "DATABASE_PATH" in result.stderr
