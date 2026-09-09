"""Optional Discord sign-in.

Sign-in is an upgrade, never a wall (DECISIONS.md section 4), so most of what
matters here is that it cannot make anything worse: the state cannot be forged,
the callback cannot be turned into an open redirect, and signing in never
orphans what you uploaded a moment earlier.
"""

import json

import pytest

import discord_auth

DISCORD_ID = "1234567890"
OTHER_DISCORD_ID = "9876543210"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("DISCORD_CLIENT_ID", "test-client")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("DISCORD_REDIRECT_URI", "https://api.example/api/auth/discord/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example")
    monkeypatch.delenv("OWNER_DISCORD_ID", raising=False)


@pytest.fixture
def discord_says(monkeypatch):
    """Stub the two outbound calls. Returns a setter for the profile."""

    def _set(discord_id, name="Someone"):
        monkeypatch.setattr(discord_auth, "exchange_code", lambda code: "token")
        monkeypatch.setattr(
            discord_auth, "fetch_user", lambda token: {"id": discord_id, "name": name}
        )

    return _set


class TestNextPath:
    @pytest.mark.parametrize(
        "raw",
        ["https://evil.example/steal", "//evil.example/steal", "http://evil.example", "evil"],
    )
    def test_a_full_url_is_refused(self, raw):
        """Accepting one is how an OAuth callback becomes a phishing hop."""
        assert discord_auth.safe_next_path(raw) == "/"

    @pytest.mark.parametrize("raw", ["/character/Rem", "/customs?page=2", "/"])
    def test_a_local_path_is_kept(self, raw):
        assert discord_auth.safe_next_path(raw) == raw

    def test_missing_becomes_the_root(self):
        assert discord_auth.safe_next_path(None) == "/"


class TestState:
    KEY = "a-test-key"

    def test_round_trip(self):
        token = discord_auth.sign_state(self.KEY, "/character/Rem")
        assert discord_auth.verify_state(self.KEY, token) == "/character/Rem"

    def test_a_forged_state_is_rejected(self):
        token = discord_auth.sign_state("some-other-key", "/")
        assert discord_auth.verify_state(self.KEY, token) is None

    def test_a_tampered_state_is_rejected(self):
        token = discord_auth.sign_state(self.KEY, "/")
        assert discord_auth.verify_state(self.KEY, f"{token}x") is None

    def test_missing_state_is_rejected(self):
        assert discord_auth.verify_state(self.KEY, None) is None

    def test_two_states_differ(self):
        """A nonce, so the same next path does not produce a reusable token."""
        a = discord_auth.sign_state(self.KEY, "/")
        b = discord_auth.sign_state(self.KEY, "/")
        assert a != b


class TestStartEndpoint:
    def test_unconfigured_is_503_not_a_broken_redirect(self, client, clean_db, monkeypatch):
        monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
        monkeypatch.delenv("DISCORD_CLIENT_SECRET", raising=False)
        assert client.get("/api/auth/discord/start").status_code == 503

    def test_redirects_to_discord_with_the_identify_scope_only(self, client, clean_db, configured):
        response = client.get("/api/auth/discord/start")
        assert response.status_code == 302
        target = response.headers["Location"]
        assert target.startswith(discord_auth.AUTHORIZE_URL)
        assert "scope=identify" in target
        assert "client_id=test-client" in target
        assert "state=" in target

    def test_me_reports_whether_sign_in_is_available(self, client, clean_db, configured):
        assert client.get("/api/me").get_json()["discord_available"] is True


class TestCallback:
    def _start(self, client):
        """Follow the real flow far enough to hold a valid state."""
        location = client.get("/api/auth/discord/start").headers["Location"]
        return location.split("state=", 1)[1].split("&", 1)[0]

    def test_a_forged_state_does_not_sign_anyone_in(self, client, clean_db, configured):
        response = client.get("/api/auth/discord/callback?code=x&state=forged")
        assert response.status_code == 302
        assert "signin=expired" in response.headers["Location"]
        assert client.get("/api/me").get_json()["signed_in"] is False

    def test_cancelling_on_discord_comes_back_cleanly(self, client, clean_db, configured):
        state = self._start(client)
        response = client.get(f"/api/auth/discord/callback?error=access_denied&state={state}")
        assert "signin=cancelled" in response.headers["Location"]
        assert client.get("/api/me").get_json()["signed_in"] is False

    def test_a_successful_sign_in_binds_the_account(
        self, client, clean_db, configured, discord_says
    ):
        discord_says(DISCORD_ID, name="Luka")
        state = self._start(client)
        response = client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        assert "signin=ok" in response.headers["Location"]

        me = client.get("/api/me").get_json()
        assert me["signed_in"] is True
        assert me["handle"] == "Luka"

    def test_it_returns_you_to_the_page_you_started_on(
        self, client, clean_db, configured, discord_says
    ):
        discord_says(DISCORD_ID)
        location = client.get("/api/auth/discord/start?next=/character/Rem").headers["Location"]
        state = location.split("state=", 1)[1].split("&", 1)[0]
        response = client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        assert response.headers["Location"].startswith("https://app.example/character/Rem")

    def test_a_full_url_in_next_cannot_redirect_off_site(
        self, client, clean_db, configured, discord_says
    ):
        discord_says(DISCORD_ID)
        location = client.get("/api/auth/discord/start?next=https://evil.example/x").headers[
            "Location"
        ]
        state = location.split("state=", 1)[1].split("&", 1)[0]
        response = client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        assert response.headers["Location"].startswith("https://app.example/")
        assert "evil.example" not in response.headers["Location"]

    def test_the_owner_is_bootstrapped_from_the_environment(
        self, client, clean_db, configured, discord_says, monkeypatch
    ):
        """No admin password exists anywhere; this is the whole mechanism."""
        monkeypatch.setenv("OWNER_DISCORD_ID", DISCORD_ID)
        discord_says(DISCORD_ID)
        state = self._start(client)
        client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        me = client.get("/api/me").get_json()
        assert me["role"] == "owner"
        assert me["is_owner"] is True

    def test_someone_else_signing_in_is_not_the_owner(
        self, client, clean_db, configured, discord_says, monkeypatch
    ):
        monkeypatch.setenv("OWNER_DISCORD_ID", OTHER_DISCORD_ID)
        discord_says(DISCORD_ID)
        state = self._start(client)
        client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        assert client.get("/api/me").get_json()["role"] == "user"


class TestIdentityMerge:
    """Signing in must never orphan what you uploaded a moment earlier."""

    def test_uploads_follow_you_into_the_account(self, clean_db):
        clean_db.ensure_identity("old-account")
        clean_db.ensure_identity("anon")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by="anon")
        clean_db.save_character("Rem", identity_id="anon")

        with clean_db.transaction() as conn:
            conn.execute(
                "UPDATE identities SET discord_id = ? WHERE id = 'old-account'", (DISCORD_ID,)
            )

        result = clean_db.bind_discord_identity("anon", DISCORD_ID)
        assert result["identity_id"] == "old-account"
        assert result["merged"] is True

        rows = clean_db.get_custom_image_rows("Rem", "old-account")
        assert rows[0]["is_mine"] is True
        assert [c["name"] for c in clean_db.get_saved_characters("old-account")] == ["Rem"]
        assert clean_db.get_identity("anon") is None

    def test_a_colliding_row_does_not_break_the_merge(self, clean_db):
        """You may have hidden the same image already from the other browser."""
        clean_db.ensure_identity("old-account")
        clean_db.ensure_identity("anon")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by=None)
        image_id = clean_db.get_custom_image_rows("Rem")[0]["id"]
        clean_db.hide_images("old-account", [image_id])
        clean_db.hide_images("anon", [image_id])

        with clean_db.transaction() as conn:
            conn.execute(
                "UPDATE identities SET discord_id = ? WHERE id = 'old-account'", (DISCORD_ID,)
            )

        clean_db.bind_discord_identity("anon", DISCORD_ID)
        assert clean_db.get_custom_image_rows("Rem", "old-account")[0]["hidden"] is True
        assert clean_db.get_identity("anon") is None

    def test_a_first_sign_in_keeps_the_identity_you_already_had(self, clean_db):
        clean_db.ensure_identity("anon")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by="anon")
        result = clean_db.bind_discord_identity("anon", DISCORD_ID)
        assert result["identity_id"] == "anon"
        assert result["merged"] is False
        assert clean_db.get_identity("anon")["discord_id"] == DISCORD_ID

    def test_signing_in_again_on_the_same_browser_changes_nothing(self, clean_db):
        clean_db.ensure_identity("anon")
        clean_db.bind_discord_identity("anon", DISCORD_ID)
        result = clean_db.bind_discord_identity("anon", DISCORD_ID)
        assert result["identity_id"] == "anon"
        assert result["merged"] is False

    def test_signing_in_never_demotes_a_moderator(self, clean_db):
        clean_db.ensure_identity("mod")
        clean_db.set_role("mod", "moderator")
        clean_db.bind_discord_identity("mod", DISCORD_ID, owner_discord_id=OTHER_DISCORD_ID)
        assert clean_db.get_identity("mod")["role"] == "moderator"


class TestLogout:
    def test_it_hands_out_a_fresh_identity_without_deleting_the_old_one(
        self, client, clean_db, configured, discord_says
    ):
        discord_says(DISCORD_ID, name="Luka")
        location = client.get("/api/auth/discord/start").headers["Location"]
        state = location.split("state=", 1)[1].split("&", 1)[0]
        client.get(f"/api/auth/discord/callback?code=abc&state={state}")
        assert client.get("/api/me").get_json()["signed_in"] is True

        client.post("/api/auth/logout", data=json.dumps({}), content_type="application/json")
        me = client.get("/api/me").get_json()
        assert me["signed_in"] is False
        assert me["handle"] != "Luka"

        # The account itself survives, so signing in again reaches it.
        conn = clean_db.get_connection()
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM identities WHERE discord_id = ?", (DISCORD_ID,)
            ).fetchone()[0]
            == 1
        )
