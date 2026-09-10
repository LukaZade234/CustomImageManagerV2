"""Ownership, hide-for-me, and the removed drawer.

These pin the rule that makes griefing *unimplementable* rather than merely
discouraged: you can only remove images you added. DECISIONS.md section 1 has
the reasoning, including the six mechanisms that were rejected to get here.

Three cases matter and are easy to get wrong:

- someone else's image cannot be removed, only hidden;
- an image migrated from v1 has no owner, so no ordinary user can remove it --
  intended, since the alternative is letting anyone wipe the inherited library;
- nothing is ever hard-deleted, so every removal is restorable.
"""

import json

SOMEONE_ELSE = "another-identity"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _seed_owned_by(db, char, urls, owner):
    """Images attributed to a specific identity."""
    if owner is not None:
        db.ensure_identity(owner)
    db.add_custom_images(char, urls, added_by=owner)


def _active_urls(client, char):
    return [row["url"] for row in client.get(f"/api/custom-image/{char}").get_json()]


class TestOwnershipOnRemove:
    def test_you_can_remove_your_own_image(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/mine.png"]},
        )
        assert r.status_code == 200
        assert r.get_json()["removed"] == ["https://cdn/mine.png"]
        assert _active_urls(client, "Rem") == []

    def test_you_cannot_remove_someone_elses(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/theirs.png"]},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["removed"] == []
        assert body["denied"] == ["https://cdn/theirs.png"]
        assert _active_urls(client, "Rem") == ["https://cdn/theirs.png"]

    def test_images_migrated_from_v1_have_no_owner_and_stay_put(
        self, client, clean_db, identity_id
    ):
        """added_by IS NULL means nobody owns it, so nobody may remove it."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/legacy.png"], None)
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/legacy.png"]},
        )
        assert r.get_json()["denied"] == ["https://cdn/legacy.png"]
        assert _active_urls(client, "Rem") == ["https://cdn/legacy.png"]

    def test_a_mixed_selection_removes_only_your_own(self, client, clean_db, identity_id):
        """The normal case: the caller needs the breakdown, not a bare success."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        r = _post(
            client,
            "/api/delete-custom-images",
            {
                "character_name": "Rem",
                "image_urls": ["https://cdn/mine.png", "https://cdn/theirs.png", "https://cdn/x"],
            },
        )
        body = r.get_json()
        assert body["removed"] == ["https://cdn/mine.png"]
        assert body["denied"] == ["https://cdn/theirs.png"]
        assert body["missing"] == ["https://cdn/x"]
        assert _active_urls(client, "Rem") == ["https://cdn/theirs.png"]

    def test_single_delete_of_someone_elses_image_is_403(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        r = _post(
            client,
            "/api/delete-custom-image",
            {"character_name": "Rem", "image_url": "https://cdn/theirs.png"},
        )
        assert r.status_code == 403
        assert "only remove images you added" in r.get_json()["error"]

    def test_unknown_character_is_still_404(self, client, clean_db, identity_id):
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Nobody", "image_urls": ["x"]},
        )
        assert r.status_code == 404


class TestModeratorFallback:
    """A manual escape hatch, not the mechanism -- DECISIONS.md section 5."""

    def test_a_moderator_can_remove_anyones_image(
        self, client, clean_db, identity_id, make_moderator
    ):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        make_moderator()
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/theirs.png"]},
        )
        assert r.get_json()["removed"] == ["https://cdn/theirs.png"]

    def test_a_moderator_can_remove_an_unowned_legacy_image(
        self, client, clean_db, identity_id, make_moderator
    ):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/legacy.png"], None)
        make_moderator()
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/legacy.png"]},
        )
        assert r.get_json()["removed"] == ["https://cdn/legacy.png"]

    def test_the_owner_role_also_counts_as_a_moderator(
        self, client, clean_db, identity_id, make_moderator
    ):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        make_moderator("owner")
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/theirs.png"]},
        )
        assert r.get_json()["removed"] == ["https://cdn/theirs.png"]


class TestNothingIsEverDestroyed:
    def test_a_removed_image_moves_to_the_drawer(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/mine.png"]},
        )
        drawer = client.get("/api/removed/Rem").get_json()
        assert [row["url"] for row in drawer] == ["https://cdn/mine.png"]
        assert drawer[0]["removed_by"] is not None

    def test_anyone_can_restore(self, client, clean_db, identity_id):
        """Restoring is not destructive, so a wrong removal is cheap to undo."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        clean_db.remove_custom_images(
            "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE, is_moderator=False
        )
        assert _active_urls(client, "Rem") == []

        r = _post(
            client,
            "/api/restore-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/theirs.png"]},
        )
        assert r.get_json()["restored"] == 1
        assert _active_urls(client, "Rem") == ["https://cdn/theirs.png"]

    def test_restoring_clears_the_removal_record(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        clean_db.remove_custom_images("Rem", ["https://cdn/mine.png"], identity_id)
        clean_db.restore_custom_images("Rem", ["https://cdn/mine.png"])
        assert client.get("/api/removed/Rem").get_json() == []

    def test_removal_is_soft_so_the_row_survives(self, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        clean_db.remove_custom_images("Rem", ["https://cdn/mine.png"], identity_id)
        conn = clean_db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM custom_images").fetchone()[0]
        assert count == 1, "soft delete must keep the row; ImgChest keeps the file anyway"


class TestHideForMe:
    def test_hiding_flags_the_image_for_you_only(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()[0]["id"]

        r = _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert r.get_json()["hidden"] == 1

        rows = client.get("/api/custom-image/Rem").get_json()
        assert rows[0]["hidden"] is True

    def test_hiding_has_no_effect_on_anyone_else(self, client, clean_db, identity_id):
        """The whole point: a hide is invisible to everyone but the hider."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()[0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})

        # A different viewer, i.e. no identity supplied.
        assert clean_db.get_custom_image_rows("Rem")[0]["hidden"] is False
        assert clean_db.get_custom_image_rows("Rem", SOMEONE_ELSE)[0]["hidden"] is False

    def test_hiding_does_not_remove(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()[0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert client.get("/api/removed/Rem").get_json() == []
        assert _active_urls(client, "Rem") == ["https://cdn/theirs.png"]

    def test_hiding_twice_is_idempotent(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()[0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert (
            _post(client, "/api/hide-images", {"image_ids": [image_id]}).get_json()["hidden"] == 0
        )

    def test_unhiding_restores_it(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()[0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert (
            _post(client, "/api/unhide-images", {"image_ids": [image_id]}).get_json()["unhidden"]
            == 1
        )
        assert client.get("/api/custom-image/Rem").get_json()[0]["hidden"] is False

    def test_image_ids_must_be_a_list_of_integers(self, client, clean_db, identity_id):
        assert _post(client, "/api/hide-images", {"image_ids": "nope"}).status_code == 400
        assert _post(client, "/api/hide-images", {"image_ids": ["abc"]}).status_code == 400


class TestOwnershipInTheReadPath:
    def test_your_own_image_is_marked_is_mine(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        assert client.get("/api/custom-image/Rem").get_json()[0]["is_mine"] is True

    def test_someone_elses_is_not(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        row = client.get("/api/custom-image/Rem").get_json()[0]
        assert row["is_mine"] is False
        assert row["owner"] is not None

    def test_an_unowned_image_reports_no_owner(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/legacy.png"], None)
        row = client.get("/api/custom-image/Rem").get_json()[0]
        assert row["owner"] is None
        assert row["is_mine"] is False

    def test_the_raw_identity_id_is_never_returned(self, client, clean_db, identity_id):
        """Ownership is reported as a handle and a boolean, never as the id."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        row = client.get("/api/custom-image/Rem").get_json()[0]
        assert set(row) == {
            "id",
            "url",
            "thumb",
            "width",
            "height",
            "owner",
            "is_mine",
            "hidden",
        }
        assert identity_id not in json.dumps(row)
