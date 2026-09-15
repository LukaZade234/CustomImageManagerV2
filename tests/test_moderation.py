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

import identity as identity_module

SOMEONE_ELSE = "another-identity"


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _seed_owned_by(db, char, urls, owner):
    """Images attributed to a specific identity."""
    if owner is not None:
        db.ensure_identity(owner)
    db.add_custom_images(char, urls, added_by=owner)


def _active_urls(client, char):
    return [row["url"] for row in client.get(f"/api/custom-image/{char}").get_json()["rows"]]


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
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]

        r = _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert r.get_json()["hidden"] == 1

        rows = client.get("/api/custom-image/Rem").get_json()["rows"]
        assert rows[0]["hidden"] is True

    def test_hiding_has_no_effect_on_anyone_else(self, client, clean_db, identity_id):
        """The whole point: a hide is invisible to everyone but the hider."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})

        # A different viewer, i.e. no identity supplied.
        assert clean_db.get_custom_image_rows("Rem")[0]["hidden"] is False
        assert clean_db.get_custom_image_rows("Rem", SOMEONE_ELSE)[0]["hidden"] is False

    def test_hiding_does_not_remove(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert client.get("/api/removed/Rem").get_json() == []
        assert _active_urls(client, "Rem") == ["https://cdn/theirs.png"]

    def test_hiding_twice_is_idempotent(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert (
            _post(client, "/api/hide-images", {"image_ids": [image_id]}).get_json()["hidden"] == 0
        )

    def test_unhiding_restores_it(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]
        _post(client, "/api/hide-images", {"image_ids": [image_id]})
        assert (
            _post(client, "/api/unhide-images", {"image_ids": [image_id]}).get_json()["unhidden"]
            == 1
        )
        assert client.get("/api/custom-image/Rem").get_json()["rows"][0]["hidden"] is False

    def test_image_ids_must_be_a_list_of_integers(self, client, clean_db, identity_id):
        assert _post(client, "/api/hide-images", {"image_ids": "nope"}).status_code == 400
        assert _post(client, "/api/hide-images", {"image_ids": ["abc"]}).status_code == 400


class TestOwnershipInTheReadPath:
    def test_your_own_image_is_marked_is_mine(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        assert client.get("/api/custom-image/Rem").get_json()["rows"][0]["is_mine"] is True

    def test_someone_elses_is_not(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/theirs.png"], SOMEONE_ELSE)
        row = client.get("/api/custom-image/Rem").get_json()["rows"][0]
        assert row["is_mine"] is False
        assert row["owner"] is not None

    def test_an_unowned_image_reports_no_owner(self, client, clean_db, identity_id):
        _seed_owned_by(clean_db, "Rem", ["https://cdn/legacy.png"], None)
        row = client.get("/api/custom-image/Rem").get_json()["rows"][0]
        assert row["owner"] is None
        assert row["is_mine"] is False

    def test_the_raw_identity_id_is_never_returned(self, client, clean_db, identity_id):
        """Ownership is reported as a handle and a boolean, never as the id."""
        _seed_owned_by(clean_db, "Rem", ["https://cdn/mine.png"], identity_id)
        row = client.get("/api/custom-image/Rem").get_json()["rows"][0]
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


class TestHidingUnknownImages:
    """An id that no longer exists must not be a server error.

    Hiding used to insert the id straight into `user_hidden`, so an unknown one
    tripped a foreign-key constraint that escaped as a 500. Any stale id would do
    it -- a page left open while somebody else removed the image is enough.
    """

    def test_an_unknown_id_is_ignored_not_rejected(self, client, clean_db):
        response = client.post("/api/hide-images", json={"image_ids": [999999]})
        assert response.status_code == 200
        assert response.get_json()["hidden"] == 0

    def test_a_mixed_request_hides_what_it_can(self, client, clean_db, identity_id):
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by=identity_id)
        real = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]

        response = client.post("/api/hide-images", json={"image_ids": [real, 999999]})
        assert response.get_json()["hidden"] == 1
        assert [h["id"] for h in client.get("/api/me/hidden").get_json()] == [real]

    def test_an_image_removed_underneath_you_is_still_not_an_error(
        self, client, clean_db, identity_id
    ):
        """The race the in-statement filter exists for."""
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by=identity_id)
        image_id = client.get("/api/custom-image/Rem").get_json()["rows"][0]["id"]

        with clean_db.transaction() as conn:
            conn.execute("DELETE FROM custom_images WHERE id = ?", (image_id,))

        response = client.post("/api/hide-images", json={"image_ids": [image_id]})
        assert response.status_code == 200
        assert response.get_json()["hidden"] == 0


class TestModerationReadSurface:
    """The staff-only inspection surface — read-only, no acting verbs.

    It answers "what has this person been doing?" without becoming a queue:
    nothing here is pending, and owner/handle/ref are all it ever returns.
    """

    def _owned(self, db, char, urls, owner):
        db.ensure_identity(owner)
        db.add_custom_images(char, urls, added_by=owner)

    def test_a_plain_user_is_refused_by_both_endpoints(self, client, clean_db, identity_id):
        ref = identity_module.public_ref(identity_id)
        assert client.get("/api/moderation/users").status_code == 403
        assert client.get(f"/api/moderation/users/{ref}/images").status_code == 403

    def test_a_moderator_sees_the_contributors(self, client, clean_db, identity_id, make_moderator):
        self._owned(clean_db, "Rem", ["https://cdn/a.png"], identity_id)
        make_moderator()

        body = client.get("/api/moderation/users").get_json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["ref"] == identity_module.public_ref(identity_id)
        assert item["added"] == 1
        assert item["removed"] == 0

    def test_someone_who_only_removed_something_still_appears(self, client, clean_db, make_moderator):
        # They added one image and later removed it, so they have no *active*
        # additions — but the actor set is a union, so they still show up.
        clean_db.ensure_identity("remover")
        clean_db.add_custom_images("Rem", ["https://cdn/x.png"], added_by="remover")
        clean_db.remove_custom_images("Rem", ["https://cdn/x.png"], "remover")
        make_moderator()

        items = {item["ref"]: item for item in client.get("/api/moderation/users").get_json()["items"]}
        remover = items[identity_module.public_ref("remover")]
        assert remover["added"] == 0
        assert remover["removed"] == 1

    def test_the_detail_splits_additions_and_removals(self, client, clean_db, identity_id, make_moderator):
        self._owned(clean_db, "Rem", ["https://cdn/kept.png"], identity_id)
        self._owned(clean_db, "Rem", ["https://cdn/gone.png"], identity_id)
        clean_db.remove_custom_images("Rem", ["https://cdn/gone.png"], identity_id)
        make_moderator()
        ref = identity_module.public_ref(identity_id)

        added = client.get(f"/api/moderation/users/{ref}/images?state=active").get_json()
        assert [i["url"] for i in added["items"]] == ["https://cdn/kept.png"]
        assert added["added"] == 1
        assert added["removed"] == 1

        removed = client.get(f"/api/moderation/users/{ref}/images?state=removed").get_json()
        assert [i["url"] for i in removed["items"]] == ["https://cdn/gone.png"]
        assert removed["added"] == 1
        assert removed["removed"] == 1

    def test_the_character_filter_trims_the_list(self, client, clean_db, identity_id, make_moderator):
        self._owned(clean_db, "Rem", ["https://cdn/rem.png"], identity_id)
        self._owned(clean_db, "Emilia", ["https://cdn/emilia.png"], identity_id)
        make_moderator()
        ref = identity_module.public_ref(identity_id)

        body = client.get(f"/api/moderation/users/{ref}/images?char=Rem").get_json()
        assert [i["url"] for i in body["items"]] == ["https://cdn/rem.png"]

    def test_an_unknown_ref_is_404(self, client, clean_db, make_moderator):
        make_moderator()
        assert client.get("/api/moderation/users/notthere/images").status_code == 404

    def test_an_invalid_state_is_400(self, client, clean_db, identity_id, make_moderator):
        make_moderator()
        ref = identity_module.public_ref(identity_id)
        assert client.get(f"/api/moderation/users/{ref}/images?state=bogus").status_code == 400

    def test_the_raw_identity_id_never_appears(self, client, clean_db, identity_id, make_moderator):
        """The ref exists precisely so the id stays server-side."""
        self._owned(clean_db, "Rem", ["https://cdn/a.png"], identity_id)
        make_moderator()
        ref = identity_module.public_ref(identity_id)

        users = client.get("/api/moderation/users").get_json()
        detail = client.get(f"/api/moderation/users/{ref}/images").get_json()
        assert identity_id not in json.dumps(users)
        assert identity_id not in json.dumps(detail)

    def test_public_ref_round_trips(self, clean_db, identity_id):
        clean_db.ensure_identity(identity_id)
        ref = identity_module.public_ref(identity_id)
        assert clean_db.identity_by_ref(ref) == identity_id
        assert clean_db.identity_by_ref("0" * 16) is None


class TestModerationCharacterView:
    """The character-level view: the same work grouped by character.

    It exists to answer "where is their work concentrated", which the image grid
    cannot, and it sorts with the Browse Customs vocabulary.
    """

    def _owned(self, db, char, urls, owner):
        db.ensure_identity(owner)
        db.add_custom_images(char, urls, added_by=owner)

    def _ref(self, identity_id):
        return identity_module.public_ref(identity_id)

    def test_a_plain_user_is_refused(self, client, clean_db, identity_id):
        assert client.get(f"/api/moderation/users/{self._ref(identity_id)}/characters").status_code == 403

    def test_it_groups_by_character_with_counts(self, client, clean_db, identity_id, make_moderator):
        self._owned(clean_db, "Rem", ["https://cdn/a.png", "https://cdn/b.png"], identity_id)
        self._owned(clean_db, "Emilia", ["https://cdn/c.png"], identity_id)
        make_moderator()

        body = client.get(f"/api/moderation/users/{self._ref(identity_id)}/characters").get_json()
        by_name = {row["name"]: row for row in body["items"]}
        assert by_name["Rem"]["count"] == 2
        assert by_name["Emilia"]["count"] == 1
        # Default sort is most images first.
        assert body["items"][0]["name"] == "Rem"
        assert body["total"] == 2

    def test_an_unknown_sort_is_400(self, client, clean_db, identity_id, make_moderator):
        make_moderator()
        res = client.get(f"/api/moderation/users/{self._ref(identity_id)}/characters?sort=bogus")
        assert res.status_code == 400

    def test_an_unknown_ref_is_404(self, client, clean_db, make_moderator):
        make_moderator()
        assert client.get("/api/moderation/users/notthere/characters").status_code == 404

    def test_created_at_is_carried_on_the_contributor(self, client, clean_db, identity_id, make_moderator):
        self._owned(clean_db, "Rem", ["https://cdn/a.png"], identity_id)
        make_moderator()
        item = client.get("/api/moderation/users").get_json()["items"][0]
        assert item["created_at"], "the account's age drives the profile stat"
