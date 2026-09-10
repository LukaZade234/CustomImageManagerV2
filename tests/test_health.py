"""The health check, and specifically that it can fail.

`/api/health` used to return a static dict, so it answered "ok" with the
database unreachable — green in exactly the situation the check exists to
catch. DEPLOYMENT.md tells you to check it before going further, which makes a
check that cannot fail worse than no check at all: it turns a broken deploy
into a confident all-clear.

So the tests that matter here are the failing ones. A test that only asserts
200-when-healthy would have passed against the old static version too.
"""

import sqlite3

import db
import upload_imgchest


class TestHealthy:
    def test_it_reports_ok_with_a_working_database(self, client, clean_db):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "ok"
        assert body["service"] == "imgmanager"
        assert body["database"] == "ok"
        assert body["revision"], "revision must never be empty"

    def test_an_empty_library_is_healthy_but_says_so(self, client, clean_db):
        """A fresh install before seeding is not an error — but it is visible.

        This is also the shape an unmounted volume takes, since migrations run
        on connect and hand back a valid empty schema. The endpoint reports the
        count rather than guessing which of the two it is looking at.
        """
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json()["characters"] == 0


class TestUnhealthy:
    """Each of these fails against the old static implementation."""

    def test_an_unreadable_database_is_503(self, client, clean_db, monkeypatch):
        def broken():
            raise sqlite3.OperationalError("unable to open database file")

        monkeypatch.setattr(db, "get_connection", broken)
        r = client.get("/api/health")
        assert r.status_code == 503
        assert r.get_json()["status"] == "error"
        assert "unable to open database file" in r.get_json()["database"]

    def test_a_misconfigured_database_is_503(self, client, clean_db, monkeypatch):
        def broken():
            raise db.DatabaseConfigurationError("DATABASE_URL is not set")

        monkeypatch.setattr(db, "get_connection", broken)
        r = client.get("/api/health")
        assert r.status_code == 503
        assert "DATABASE_URL is not set" in r.get_json()["database"]

    def test_a_missing_schema_is_503(self, client, clean_db, monkeypatch):
        """Reachable after a half-applied migration rather than on a fresh file.

        A fresh file gets its schema from `_connect()`, so this is not the
        unmounted-volume case — that one is covered by the character count.
        """

        class _NoSchema:
            def execute(self, *_args, **_kwargs):
                raise sqlite3.OperationalError("no such table: characters")

        monkeypatch.setattr(db, "get_connection", lambda: _NoSchema())
        r = client.get("/api/health")
        assert r.status_code == 503
        assert "no such table" in r.get_json()["database"]

    def test_the_revision_is_still_reported_when_unhealthy(self, client, clean_db, monkeypatch):
        """Which commit is broken is the first thing you need to know."""
        monkeypatch.setattr(upload_imgchest, "_DEPLOYED_REVISION", "deadbee")
        monkeypatch.setattr(
            db,
            "get_connection",
            lambda: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
        )
        body = client.get("/api/health").get_json()
        assert body["revision"] == "deadbee"


class TestCheckHealthDirectly:
    def test_it_reports_ok_and_the_count(self, clean_db):
        assert db.check_health() == {"ok": True, "detail": "ok", "characters": 0}

    def test_it_does_not_raise_on_failure(self, clean_db, monkeypatch):
        """The route must be able to answer 503, not 500."""
        monkeypatch.setattr(
            db,
            "get_connection",
            lambda: (_ for _ in ()).throw(sqlite3.DatabaseError("file is not a database")),
        )
        result = db.check_health()
        assert result["ok"] is False
        assert "file is not a database" in result["detail"]
