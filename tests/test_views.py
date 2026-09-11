"""Character view tracking.

Nothing recorded page views before this, so both "recently viewed" on the
profile and "most visited" on the landing page were impossible. The design
question is not how to count but how not to over-count: a metric a single
enthusiast can move by holding F5 is worse than no metric, because it looks
authoritative.

Two defences, both tested below. One row per person per character per hour, so
a refresh updates a timestamp instead of adding a row; and popularity ranked by
distinct people rather than by rows.
"""

from datetime import UTC, datetime, timedelta


def _seed(db, *names):
    for n in names:
        db.add_character(n, "Re:Zero", "1", f"{n}.png")


def _view_at(db, char, identity_id, when):
    """Write a view directly, to stand in for one that happened in the past."""
    conn = db.get_connection()
    cid = conn.execute("SELECT id FROM characters WHERE name = ?", (char,)).fetchone()["id"]
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with db.transaction() as c:
        c.execute(
            "INSERT INTO character_views (character_id, identity_id, bucket, viewed_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (identity_id, character_id, bucket)"
            " DO UPDATE SET viewed_at = excluded.viewed_at",
            (cid, identity_id, stamp[:13], stamp),
        )


class TestRecording:
    def test_a_view_is_recorded(self, client, clean_db):
        _seed(clean_db, "Rem")
        assert client.post("/api/characters/Rem/view").status_code == 200
        assert [h["name"] for h in client.get("/api/me/history").get_json()] == ["Rem"]

    def test_an_unknown_character_is_404(self, client, clean_db):
        assert client.post("/api/characters/Nobody/view").status_code == 404

    def test_refreshing_does_not_count_twice(self, client, clean_db):
        """The whole reason the primary key includes the hour."""
        _seed(clean_db, "Rem")
        for _ in range(25):
            client.post("/api/characters/Rem/view")
        assert client.get("/api/me/history").get_json()[0]["visits"] == 1

    def test_recording_never_breaks_the_page(self, client, clean_db, monkeypatch):
        """Best-effort: a page someone is already looking at must not fail."""
        _seed(clean_db, "Rem")
        monkeypatch.setattr(clean_db, "record_character_view", lambda *a, **kw: 1 / 0)
        r = client.post("/api/characters/Rem/view")
        assert r.status_code == 200
        assert r.get_json() == {"success": False}


class TestHistory:
    def test_most_recent_first_and_each_character_once(self, client, clean_db, identity_id):
        _seed(clean_db, "Rem", "Emilia", "Ram")
        now = datetime.now(UTC)
        _view_at(clean_db, "Rem", identity_id, now - timedelta(days=2))
        _view_at(clean_db, "Emilia", identity_id, now - timedelta(hours=5))
        _view_at(clean_db, "Ram", identity_id, now - timedelta(days=9))
        # A second look at Rem, later, moves it to the front without duplicating.
        _view_at(clean_db, "Rem", identity_id, now)

        history = client.get("/api/me/history").get_json()
        assert [h["name"] for h in history] == ["Rem", "Emilia", "Ram"]
        assert history[0]["visits"] == 2

    def test_it_carries_what_a_list_needs_to_render(self, client, clean_db):
        _seed(clean_db, "Rem")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png", "https://cdn/b.png"])
        client.post("/api/characters/Rem/view")
        row = client.get("/api/me/history").get_json()[0]
        assert row["series"] == "Re:Zero"
        assert row["images"] == 2
        assert row["image"] == "Rem.png"

    def test_your_history_is_yours(self, client, clean_db):
        _seed(clean_db, "Rem")
        client.post("/api/characters/Rem/view")
        stranger = client.application.test_client()
        assert stranger.get("/api/me/history").get_json() == []


class TestMostViewed:
    def test_ranked_by_distinct_people_not_by_hits(self, client, clean_db):
        """One enthusiast must not outrank a genuinely popular character."""
        _seed(clean_db, "Rem", "Emilia")
        now = datetime.now(UTC)
        # One person looks at Rem in six different hours.
        for hours in range(6):
            _view_at(clean_db, "Rem", "fan", now - timedelta(hours=hours))
        # Two different people look at Emilia once each.
        _view_at(clean_db, "Emilia", "a", now)
        _view_at(clean_db, "Emilia", "b", now)

        ranked = client.get("/api/stats").get_json()["most_viewed"]
        assert [(r["name"], r["viewers"]) for r in ranked] == [("Emilia", 2), ("Rem", 1)]

    def test_only_counts_the_last_week(self, client, clean_db):
        _seed(clean_db, "Rem", "Emilia")
        now = datetime.now(UTC)
        _view_at(clean_db, "Rem", "a", now - timedelta(days=30))
        _view_at(clean_db, "Emilia", "b", now - timedelta(days=1))

        ranked = client.get("/api/stats").get_json()["most_viewed"]
        assert [r["name"] for r in ranked] == ["Emilia"]

    def test_it_is_empty_before_anyone_has_looked(self, client, clean_db):
        _seed(clean_db, "Rem")
        assert client.get("/api/stats").get_json()["most_viewed"] == []


class TestRetention:
    def test_views_past_the_window_are_swept(self, client, clean_db, identity_id):
        _seed(clean_db, "Rem", "Emilia")
        now = datetime.now(UTC)
        _view_at(clean_db, "Rem", identity_id, now - timedelta(days=200))
        _view_at(clean_db, "Emilia", identity_id, now - timedelta(days=3))

        # The sweep is throttled, so it has to be allowed to run.
        clean_db._last_view_sweep = 0
        client.post("/api/characters/Emilia/view")

        assert [h["name"] for h in client.get("/api/me/history").get_json()] == ["Emilia"]
