"""Reports and take logging.

The report threshold is the one automated removal path in the design, so the
arithmetic matters: it must take two *distinct* people, and a single determined
reporter must not be able to reach it alone. DECISIONS.md section 1.
"""

import json

OTHER = "another-identity"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _seed_one(db, char="Rem", url="https://cdn/a.png", owner=None):
    if owner is not None:
        db.ensure_identity(owner)
    db.add_custom_images(char, [url], added_by=owner)
    return db.get_custom_image_rows(char)[0]["id"]


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
