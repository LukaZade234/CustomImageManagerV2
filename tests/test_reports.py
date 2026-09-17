"""Reports and take logging.

The report threshold is the one automated removal path in the design, so the
arithmetic matters: it must take two *distinct* people, and a single determined
reporter must not be able to reach it alone. DECISIONS.md section 1.
"""

import json

import pytest

OTHER = "another-identity"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _seed_one(db, char="Rem", url="https://cdn/a.png", owner=None):
    if owner is not None:
        db.ensure_identity(owner)
    db.add_custom_images(char, [url], added_by=owner)
    return db.get_custom_image_rows(char)[0]["id"]


def _image_id(db, char, url):
    """The id of one seeded image. `get_custom_image_rows` is ordered, so
    indexing [0] returns the first image of the character, not this one."""
    return next(r["id"] for r in db.get_custom_image_rows(char) if r["url"] == url)


class TestReportThreshold:
    def test_one_report_does_not_remove(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        body = _post(
            client, "/api/report-image", {"image_id": image_id, "reason": "nsfw"}
        ).get_json()
        assert body["reports"] == 1
        assert body["removed"] is False
        assert clean_db.get_custom_image_rows("Rem")

    def test_the_second_distinct_reporter_removes(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        clean_db.report_image(image_id, OTHER, "dead_link")
        body = _post(
            client, "/api/report-image", {"image_id": image_id, "reason": "dead_link"}
        ).get_json()
        assert body["reports"] == 2
        assert body["removed"] is True
        assert clean_db.get_custom_image_rows("Rem") == []

    def test_the_same_person_reporting_twice_changes_nothing(self, client, clean_db, identity_id):
        """Otherwise one determined person is a removal button."""
        image_id = _seed_one(clean_db)
        _post(client, "/api/report-image", {"image_id": image_id, "reason": "nsfw"})
        body = _post(
            client, "/api/report-image", {"image_id": image_id, "reason": "nsfw"}
        ).get_json()
        assert body["reports"] == 1
        assert body["removed"] is False
        assert body["already_reported"] is True
        assert len(clean_db.get_custom_image_rows("Rem")) == 1

    def test_a_reported_removal_is_restorable_like_any_other(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        clean_db.report_image(image_id, OTHER, "duplicate")
        _post(client, "/api/report-image", {"image_id": image_id, "reason": "duplicate"})

        drawer = client.get("/api/removed/Rem").get_json()
        assert drawer[0]["reason"] == "reported: duplicate"
        # No single person made the call, so nobody is named as the remover.
        assert drawer[0]["removed_by"] is None

        _post(
            client,
            "/api/restore-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/a.png"]},
        )
        assert len(clean_db.get_custom_image_rows("Rem")) == 1

    def test_reporting_an_owner_s_own_image_is_allowed(self, client, clean_db, identity_id):
        """No special case: the threshold applies uniformly."""
        image_id = _seed_one(clean_db, owner=identity_id)
        body = _post(
            client, "/api/report-image", {"image_id": image_id, "reason": "nsfw"}
        ).get_json()
        assert body["reports"] == 1


class TestReportValidation:
    def test_reason_must_be_one_of_the_objective_four(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        r = _post(client, "/api/report-image", {"image_id": image_id, "reason": "ugly"})
        assert r.status_code == 400
        assert "wrong_character" in r.get_json()["error"]

    def test_unknown_image_is_404(self, client, clean_db, identity_id):
        assert (
            _post(client, "/api/report-image", {"image_id": 9999, "reason": "nsfw"}).status_code
            == 404
        )

    def test_missing_fields_are_400(self, client, clean_db, identity_id):
        assert _post(client, "/api/report-image", {"reason": "nsfw"}).status_code == 400
        assert _post(client, "/api/report-image", {"image_id": 1}).status_code == 400

    def test_non_integer_image_id_is_400(self, client, clean_db, identity_id):
        assert (
            _post(client, "/api/report-image", {"image_id": "abc", "reason": "nsfw"}).status_code
            == 400
        )


class TestTakes:
    def test_a_take_is_logged(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        body = _post(client, "/api/takes", {"image_ids": [image_id], "kind": "download"}).get_json()
        assert body["logged"] == 1
        conn = clean_db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM image_takes").fetchone()[0] == 1

    def test_takes_drive_nothing(self, client, clean_db, identity_id):
        """Logged for future evidence, with no effect on visibility today."""
        image_id = _seed_one(clean_db)
        for _ in range(20):
            _post(client, "/api/takes", {"image_ids": [image_id], "kind": "copy_command"})
        assert len(clean_db.get_custom_image_rows("Rem")) == 1
        assert client.get("/api/removed/Rem").get_json() == []

    def test_an_unknown_image_is_skipped_not_an_error(self, client, clean_db, identity_id):
        """This is fire-and-forget; it must never break the action it accompanies."""
        r = _post(client, "/api/takes", {"image_ids": [9999], "kind": "download"})
        assert r.status_code == 200
        assert r.get_json()["logged"] == 0

    def test_kind_is_validated(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        r = _post(client, "/api/takes", {"image_ids": [image_id], "kind": "admired"})
        assert r.status_code == 400

    def test_one_copy_is_one_batch(self, client, clean_db, identity_id):
        """Every image in one $ai copy shares a batch id, however many parts it
        was split into for Discord -- the split is delivery, not intent."""
        a = _seed_one(clean_db, url="https://cdn/a.png")
        b = _seed_one(clean_db, url="https://cdn/b.png")
        c = _seed_one(clean_db, url="https://cdn/c.png")
        body = _post(
            client, "/api/takes", {"image_ids": [a, b, c], "kind": "copy_command"}
        ).get_json()
        assert body["logged"] == 3
        conn = clean_db.get_connection()
        batches = conn.execute(
            "SELECT DISTINCT batch_id FROM image_takes WHERE kind = 'copy_command'"
        ).fetchall()
        assert len(batches) == 1
        assert batches[0]["batch_id"]

    def test_each_copy_is_its_own_batch(self, client, clean_db, identity_id):
        a = _seed_one(clean_db, url="https://cdn/a.png")
        b = _seed_one(clean_db, url="https://cdn/b.png")
        _post(client, "/api/takes", {"image_ids": [a], "kind": "copy_command"})
        _post(client, "/api/takes", {"image_ids": [b], "kind": "copy_command"})
        conn = clean_db.get_connection()
        assert (
            conn.execute(
                "SELECT COUNT(DISTINCT batch_id) FROM image_takes WHERE kind = 'copy_command'"
            ).fetchone()[0]
            == 2
        )

    def test_a_download_is_not_a_batch(self, client, clean_db, identity_id):
        """Batches are about what was copied into Mudae. A download has no
        batch, so it can never become someone's 'last copied'."""
        image_id = _seed_one(clean_db)
        body = _post(client, "/api/takes", {"image_ids": [image_id], "kind": "download"}).get_json()
        assert body["batch_id"] is None
        conn = clean_db.get_connection()
        assert conn.execute("SELECT batch_id FROM image_takes").fetchone()["batch_id"] is None


class TestCopiedHistory:
    """The viewer's own $ai history, which drives the gallery selection verbs.

    It must be per-viewer and per-character: this is a memory aid, not a
    popularity signal, and DECISIONS.md section 1 rejects anything aggregate.
    """

    def test_ever_and_last_batch_differ(self, client, clean_db, identity_id):
        _seed_one(clean_db, char="Rem", url="https://cdn/a.png")
        _seed_one(clean_db, char="Rem", url="https://cdn/b.png")
        a = _image_id(clean_db, "Rem", "https://cdn/a.png")
        b = _image_id(clean_db, "Rem", "https://cdn/b.png")
        _post(client, "/api/takes", {"image_ids": [a], "kind": "copy_command"})
        _post(client, "/api/takes", {"image_ids": [b], "kind": "copy_command"})
        history = clean_db.copied_image_ids("Rem", identity_id)
        assert sorted(history["ids"]) == sorted([a, b])
        assert history["last_batch"] == [b]

    def test_rows_that_predate_batches_still_count_as_ever(self, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        clean_db.log_take(image_id, identity_id, "copy_command")  # no batch_id
        history = clean_db.copied_image_ids("Rem", identity_id)
        assert history["ids"] == [image_id]
        assert history["last_batch"] == []

    def test_another_person_history_is_not_mine(self, client, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        clean_db.log_take(image_id, OTHER, "copy_command", clean_db.new_take_batch_id())
        for viewer in (identity_id, None):
            history = clean_db.copied_image_ids("Rem", viewer)
            assert history["ids"] == []
            assert history["last_batch"] == []

    def test_history_is_scoped_to_the_character(self, client, clean_db, identity_id):
        rem = _seed_one(clean_db, char="Rem", url="https://cdn/a.png")
        _seed_one(clean_db, char="Emilia", url="https://cdn/b.png")
        clean_db.log_take(rem, identity_id, "copy_command", clean_db.new_take_batch_id())
        assert clean_db.copied_image_ids("Emilia", identity_id)["ids"] == []

    def test_the_endpoint_returns_the_history(self, client, clean_db, identity_id):
        _seed_one(clean_db, url="https://cdn/a.png")
        _seed_one(clean_db, url="https://cdn/b.png")
        a = _image_id(clean_db, "Rem", "https://cdn/a.png")
        b = _image_id(clean_db, "Rem", "https://cdn/b.png")
        _post(client, "/api/takes", {"image_ids": [a], "kind": "copy_command"})
        _post(client, "/api/takes", {"image_ids": [b], "kind": "copy_command"})
        body = client.get("/api/custom-image/Rem").get_json()
        assert sorted(body["copiedIds"]) == sorted([a, b])
        assert body["lastBatchIds"] == [b]


class TestReportQueue:
    """The moderation Reports tab: reported images split by whether they were removed."""

    def _open_one(self, clean_db):
        image_id = _seed_one(clean_db, char="Rem", url="https://cdn/open.png")
        clean_db.report_image(image_id, OTHER, "nsfw")
        return image_id

    def _removed_one(self, clean_db):
        image_id = _seed_one(clean_db, char="Emilia", url="https://cdn/removed.png")
        clean_db.report_image(image_id, OTHER, "nsfw")
        clean_db.report_image(image_id, "third-identity", "wrong_character")
        return image_id

    def test_counts_split_by_state(self, clean_db):
        self._open_one(clean_db)
        self._removed_one(clean_db)
        assert clean_db.reported_image_counts() == {"reported": 1, "removed": 1}

    def test_the_reported_filter_is_still_live(self, clean_db):
        self._open_one(clean_db)
        self._removed_one(clean_db)
        items = clean_db.list_reported_images(status="reported")
        assert [item["state"] for item in items] == ["active"]
        assert items[0]["report_count"] == 1

    def test_the_removed_filter_is_what_the_threshold_took_down(self, clean_db):
        self._open_one(clean_db)
        self._removed_one(clean_db)
        items = clean_db.list_reported_images(status="removed")
        assert [item["state"] for item in items] == ["removed"]
        assert items[0]["report_count"] == 2
        assert items[0]["removed_reason"] == "reported: wrong_character"

    def test_reports_carry_their_reason_and_reporter(self, clean_db, identity_id):
        image_id = _seed_one(clean_db)
        clean_db.report_image(image_id, identity_id, "nsfw")
        report = clean_db.list_reported_images(status="reported")[0]["reports"][0]
        assert report["reason"] == "nsfw"
        assert report["reporter"]

    def test_unreported_images_are_absent(self, clean_db):
        _seed_one(clean_db)
        assert clean_db.list_reported_images() == []
        assert clean_db.reported_image_counts() == {"reported": 0, "removed": 0}

    def test_a_bad_status_is_rejected(self, clean_db):
        with pytest.raises(ValueError):
            clean_db.list_reported_images(status="nope")


class TestReportsApi:
    def test_moderators_only(self, client, clean_db, make_moderator):
        assert client.get("/api/moderation/reports").status_code == 403

        make_moderator()
        body = client.get("/api/moderation/reports").get_json()
        assert body == {
            "status": "reported",
            "counts": {"reported": 0, "removed": 0},
            "items": [],
            "total": 0,
        }

    def test_the_status_filter_reaches_the_query(self, client, clean_db, make_moderator):
        open_id = _seed_one(clean_db, char="Rem", url="https://cdn/open.png")
        clean_db.report_image(open_id, OTHER, "nsfw")
        removed_id = _seed_one(clean_db, char="Emilia", url="https://cdn/removed.png")
        clean_db.report_image(removed_id, OTHER, "nsfw")
        clean_db.report_image(removed_id, "third-identity", "wrong_character")
        make_moderator()

        removed = client.get("/api/moderation/reports?status=removed").get_json()
        assert removed["status"] == "removed"
        assert [item["state"] for item in removed["items"]] == ["removed"]
        assert removed["counts"] == {"reported": 1, "removed": 1}

    def test_an_unknown_status_is_400(self, client, clean_db, make_moderator):
        make_moderator()
        assert client.get("/api/moderation/reports?status=nope").status_code == 400
