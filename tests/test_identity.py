"""Cookie-pseudonym identity.

The properties worth protecting here are narrow but load-bearing: an id must
survive across requests (or people lose their uploads), and it must not be
forgeable (or ownership means nothing). Everything else about this identity is
deliberately weak -- see DECISIONS.md section 4.
"""

import pytest

import identity


def _set_cookie_header(response):
    return response.headers.get("Set-Cookie", "")


def _issued_token(response):
    """The signed value out of a Set-Cookie header, or None if none was set."""
    header = _set_cookie_header(response)
    if identity.COOKIE_NAME + "=" not in header:
        return None
    return header.split(identity.COOKIE_NAME + "=", 1)[1].split(";", 1)[0]


class TestHandles:
    def test_handle_is_deterministic(self):
        assert identity.handle_for("abc") == identity.handle_for("abc")

    def test_different_ids_generally_differ(self):
        ids = [identity.new_identity_id() for _ in range(200)]
        handles = {identity.handle_for(i) for i in ids}
        # Collisions are expected and harmless at ~4300 combinations; a single
        # handle for 200 ids would mean the derivation is broken.
        assert len(handles) > 150

    def test_handle_is_two_capitalised_words(self):
        handle = identity.handle_for("whatever")
        first, second = handle.split(" ")
        assert first[0].isupper() and second[0].isupper()


class TestSigning:
    KEY = "a-test-key"

    def test_round_trip(self):
        token = identity.sign("ident-1", self.KEY)
        assert identity.unsign(token, self.KEY) == "ident-1"

    def test_tampered_token_is_rejected(self):
        token = identity.sign("ident-1", self.KEY)
        assert identity.unsign(token + "x", self.KEY) is None

    def test_token_from_another_key_is_rejected(self):
        token = identity.sign("ident-1", "some-other-key")
        assert identity.unsign(token, self.KEY) is None

    def test_garbage_is_rejected_rather_than_raising(self):
        assert identity.unsign("not-a-token", self.KEY) is None


class TestSecretKey:
    def test_explicit_key_is_used_verbatim(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "explicit")
        key, ephemeral = identity.resolve_secret_key()
        assert key == "explicit"
        assert ephemeral is False

    def test_local_development_gets_an_ephemeral_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        key, ephemeral = identity.resolve_secret_key()
        assert key and ephemeral is True

    def test_deployed_configuration_refuses_to_start_without_one(self, monkeypatch):
        """A missing key in production is silent data loss, so it must be loud."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
        with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
            identity.resolve_secret_key()


class TestRequestLifecycle:
    def test_first_request_issues_a_cookie(self, client):
        response = client.get("/api/me")
        assert response.status_code == 200
        assert _issued_token(response) is not None

    def test_cookie_is_httponly_and_not_secure_for_same_origin(self, client):
        header = _set_cookie_header(client.get("/api/me"))
        assert "HttpOnly" in header
        # Locally the Vite proxy makes this same-origin; Secure would stop the
        # cookie working over plain http.
        assert "Secure" not in header
        assert "SameSite=Lax" in header

    def test_identity_survives_across_requests(self, client):
        first = client.get("/api/me").get_json()
        second = client.get("/api/me").get_json()
        assert first["handle"] == second["handle"]

    def test_cookie_is_not_reissued_once_held(self, client):
        client.get("/api/me")
        assert _issued_token(client.get("/api/me")) is None

    def test_forged_cookie_is_ignored_and_replaced(self, client):
        """A cookie signed with the wrong key must not grant that identity."""
        forged = identity.sign("someone-elses-id", "not-the-app-key")
        client.set_cookie(identity.COOKIE_NAME, forged, domain="localhost")
        response = client.get("/api/me")
        assert _issued_token(response) is not None
        assert response.get_json()["handle"] != identity.handle_for("someone-elses-id")

    def test_me_does_not_leak_the_identity_id(self, client):
        """The cookie is HttpOnly; echoing the id back in JSON would undo that."""
        body = client.get("/api/me").get_json()
        assert set(body) == {"handle", "role", "is_moderator", "is_owner", "signed_in"}

    def test_new_visitor_defaults_to_the_user_role(self, client):
        body = client.get("/api/me").get_json()
        assert body["role"] == "user"
        assert body["is_moderator"] is False


class TestLazyRowCreation:
    def test_browsing_alone_creates_no_identity_row(self, client, clean_db):
        """A crawler touching the site must not put a row in the table."""
        client.get("/api/me")
        client.get("/api/characters")
        conn = clean_db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 0

    def test_ensure_identity_creates_the_row_with_a_derived_handle(self, clean_db):
        clean_db.ensure_identity("ident-1")
        row = clean_db.get_identity("ident-1")
        assert row["handle"] == identity.handle_for("ident-1")
        assert row["role"] == "user"

    def test_ensure_identity_is_idempotent(self, clean_db):
        clean_db.ensure_identity("ident-1")
        clean_db.ensure_identity("ident-1")
        conn = clean_db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1

    def test_get_identity_is_none_when_never_written(self, clean_db):
        assert clean_db.get_identity("never-seen") is None

    def test_role_is_read_back_from_the_row(self, client, clean_db):
        """A promoted identity must be reported as a moderator on later requests."""
        client.get("/api/me")
        conn = clean_db.get_connection()
        # Derive the id the same way the app did, from the cookie it issued.
        from flask import current_app

        from upload_imgchest import app

        with app.app_context():
            token = client.get_cookie(identity.COOKIE_NAME).value
            identity_id = identity.unsign(token, current_app.config["SECRET_KEY"])
        assert identity_id is not None

        clean_db.ensure_identity(identity_id)
        with clean_db.transaction() as tx:
            tx.execute("UPDATE identities SET role = 'moderator' WHERE id = ?", (identity_id,))
        conn.commit()

        body = client.get("/api/me").get_json()
        assert body["role"] == "moderator"
        assert body["is_moderator"] is True
