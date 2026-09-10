"""Per-identity rate limiting.

There was none at all before this. The one that actually matters is on uploads:
every upload is an ImgChest API call against a shared key, so an unbounded
client can get that key throttled and take the app's whole purpose with it.

Two properties are load-bearing and easy to lose: limits must be per identity
(a shared bucket would let one abuser lock everyone out) and per action (a
report storm must not stop people uploading).
"""

import json

import ratelimit


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


class TestCounter:
    def test_allows_up_to_the_limit_then_refuses(self, clean_db):
        for _ in range(3):
            allowed, _ = clean_db.check_rate_limit("a", "upload", limit=3, per_seconds=60)
            assert allowed
        allowed, retry_after = clean_db.check_rate_limit("a", "upload", limit=3, per_seconds=60)
        assert allowed is False
        assert 0 < retry_after <= 60

    def test_blocked_attempts_still_count(self, clean_db):
        """A client retrying into a closed window should not get a free pass."""
        for _ in range(6):
            clean_db.check_rate_limit("a", "upload", limit=2, per_seconds=60)
        assert clean_db.rate_limit_usage("a", "upload", 60) == 6

    def test_buckets_are_per_identity(self, clean_db):
        for _ in range(4):
            clean_db.check_rate_limit("noisy", "upload", limit=2, per_seconds=60)
        allowed, _ = clean_db.check_rate_limit("quiet", "upload", limit=2, per_seconds=60)
        assert allowed, "one abusive client must not lock everyone else out"

    def test_buckets_are_per_action(self, clean_db):
        for _ in range(4):
            clean_db.check_rate_limit("a", "report", limit=2, per_seconds=60)
        allowed, _ = clean_db.check_rate_limit("a", "upload", limit=2, per_seconds=60)
        assert allowed, "a report storm must not stop the same person uploading"

    def test_a_new_window_starts_fresh(self, clean_db):
        base = 1_000_000_000
        base -= base % 60
        for _ in range(5):
            clean_db.check_rate_limit("a", "upload", limit=2, per_seconds=60, now=base)
        allowed, _ = clean_db.check_rate_limit(
            "a", "upload", limit=2, per_seconds=60, now=base + 60
        )
        assert allowed

    def test_retry_after_points_at_the_window_end(self, clean_db):
        base = 1_000_000_000
        base -= base % 60
        clean_db.check_rate_limit("a", "upload", limit=0, per_seconds=60, now=base + 15)
        _, retry_after = clean_db.check_rate_limit(
            "a", "upload", limit=0, per_seconds=60, now=base + 15
        )
        assert retry_after == 45

    def test_it_works_for_an_identity_with_no_row(self, clean_db):
        """Abusive clients are exactly the ones that have never written anything."""
        allowed, _ = clean_db.check_rate_limit("never-seen", "upload", limit=1, per_seconds=60)
        assert allowed
        assert clean_db.get_identity("never-seen") is None


class TestEndpoints:
    def test_a_burst_gets_429_with_retry_after(self, client, clean_db, identity_id, monkeypatch):
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "hide", [(3, 60)])
        for _ in range(3):
            assert _post(client, "/api/hide-images", {"image_ids": []}).status_code == 200
        response = _post(client, "/api/hide-images", {"image_ids": []})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
        assert "too quickly" in response.get_json()["error"]

    def test_the_limit_does_not_leak_between_actions(
        self, client, clean_db, identity_id, monkeypatch
    ):
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "hide", [(1, 60)])
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "report", [(5, 60)])
        _post(client, "/api/hide-images", {"image_ids": []})
        assert _post(client, "/api/hide-images", {"image_ids": []}).status_code == 429
        # Report is a different bucket, so it is unaffected -- 400 for a missing
        # field, not 429.
        assert _post(client, "/api/report-image", {}).status_code == 400

    def test_moderators_get_more_headroom(
        self, client, clean_db, identity_id, make_moderator, monkeypatch
    ):
        """A limit sized for a visitor would block the person curating the site."""
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "hide", [(1, 60)])
        make_moderator()
        # One request would exhaust a plain user; the staff multiplier is 10x.
        for _ in range(5):
            assert _post(client, "/api/hide-images", {"image_ids": []}).status_code == 200

    def test_a_plain_user_is_blocked_where_a_moderator_is_not(
        self, client, clean_db, identity_id, monkeypatch
    ):
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "hide", [(1, 60)])
        _post(client, "/api/hide-images", {"image_ids": []})
        assert _post(client, "/api/hide-images", {"image_ids": []}).status_code == 429

    def test_reports_are_limited_more_tightly_than_hides(self):
        """Reports can remove other people's work; hiding affects nobody else."""
        by_window = lambda windows: {per: limit for limit, per in windows}  # noqa: E731
        report_hourly = by_window(ratelimit.RATE_LIMITS["report"])[3600]
        hide_hourly = by_window(ratelimit.RATE_LIMITS["hide"])[3600]
        assert report_hourly < hide_hourly


class TestConfiguration:
    def test_limits_can_be_overridden_by_environment(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_UPLOAD", "5/60,50/3600")
        assert ratelimit._limits_from_env("upload", [(1, 1)]) == [(5, 60), (50, 3600)]

    def test_a_malformed_override_falls_back_to_the_default(self, monkeypatch):
        """A typo in an env var must not silently disable a limit."""
        monkeypatch.setenv("RATE_LIMIT_UPLOAD", "lots please")
        assert ratelimit._limits_from_env("upload", [(7, 60)]) == [(7, 60)]

    def test_every_action_used_by_a_route_has_limits_defined(self):
        """A decorator naming a missing action would raise KeyError on a live request."""
        for action, windows in ratelimit.RATE_LIMITS.items():
            assert windows, f"{action} has no windows"
            for limit, per_seconds in windows:
                assert limit > 0 and per_seconds > 0
