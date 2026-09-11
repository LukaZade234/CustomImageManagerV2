"""The profile page's API: display preferences, and the things only it can reach.

The preferences are the interesting part. Both hide a name at *render* time and
neither changes what is stored, because the moderation model rests on
`custom_images.added_by`: removal is ownership-scoped, so an uploader who could
not be identified could not manage their own uploads, and the image would fall
into the same unowned bucket as the 8,547 migrated from v1. So the tests below
check that ownership survives being hidden, that the owner and staff can still
see it, and that flipping the switch back restores it everywhere.
"""


def _seed(db, char="Rem", count=2, owner=None):
    if owner is not None:
        db.ensure_identity(owner)
    db.add_character(char, "Re:Zero", "1", f"{char}.png")
    db.add_custom_images(
        char, [f"https://cdn/{char}-{i}.png" for i in range(count)], added_by=owner
    )


class TestSettings:
    def test_they_all_default_to_off(self, client, clean_db):
        assert client.get("/api/me").get_json()["settings"] == {
            "hide_from_leaderboard": False,
            "hide_attribution": False,
            # Recorded but not yet read: nothing carries a rating to filter on.
            # Defaulting to off means the filter, when it arrives, is not
            # switched on for people who never asked for it.
            "show_nsfw": False,
        }

    def test_each_toggles_independently(self, client, clean_db):
        """Separate because they hide different things from different audiences.

        Someone may be happy to be on the ranking while not wanting individual
        images traced back to them.
        """
        r = client.patch("/api/me/settings", json={"hide_attribution": True})
        assert r.get_json()["settings"] == {
            "hide_from_leaderboard": False,
            "hide_attribution": True,
            "show_nsfw": False,
        }

        r = client.patch("/api/me/settings", json={"hide_from_leaderboard": True})
        assert r.get_json()["settings"] == {
            "hide_from_leaderboard": True,
            "hide_attribution": True,
            "show_nsfw": False,
        }

    def test_an_omitted_field_is_left_alone(self, client, clean_db):
        client.patch("/api/me/settings", json={"hide_attribution": True})
        client.patch("/api/me/settings", json={"hide_from_leaderboard": True})
        assert client.get("/api/me").get_json()["settings"]["hide_attribution"] is True

    def test_unknown_fields_are_ignored(self, client, clean_db):
        client.patch("/api/me/settings", json={"role": "owner", "hide_attribution": True})
        me = client.get("/api/me").get_json()
        assert me["role"] == "user"
        assert me["settings"]["hide_attribution"] is True

    def test_the_nsfw_preference_is_stored_though_nothing_reads_it(self, client, clean_db):
        """Future-proofing: the choice predates the filter, so people are not all
        defaulted on the day it ships."""
        client.patch("/api/me/settings", json={"show_nsfw": True})
        assert client.get("/api/me").get_json()["settings"]["show_nsfw"] is True

    def test_the_preference_survives_a_reload(self, client, clean_db):
        client.patch("/api/me/settings", json={"hide_attribution": True})
        assert client.get("/api/me").get_json()["settings"]["hide_attribution"] is True


class TestHiddenAttribution:
    def test_ownership_is_still_recorded_when_the_name_is_hidden(
        self, client, clean_db, identity_id
    ):
        """The whole point. Hiding is rendering; removal still needs the owner."""
        _seed(clean_db, owner=identity_id)
        client.patch("/api/me/settings", json={"hide_attribution": True})

        rows = client.get("/api/custom-image/Rem").get_json()
        assert all(r["is_mine"] for r in rows), "the owner must still own them"

        removed = client.post(
            "/api/delete-custom-images",
            json={"character_name": "Rem", "image_urls": ["https://cdn/Rem-0.png"]},
        )
        assert removed.status_code == 200

    def test_you_can_always_see_your_own_name(self, client, clean_db, identity_id):
        _seed(clean_db, owner=identity_id)
        client.patch("/api/me/settings", json={"hide_attribution": True})
        rows = client.get("/api/custom-image/Rem").get_json()
        assert all(r["owner"] for r in rows)

    def test_a_stranger_sees_no_owner(self, client, clean_db, identity_id):
        _seed(clean_db, owner=identity_id)
        client.patch("/api/me/settings", json={"hide_attribution": True})

        stranger = client.application.test_client()
        rows = stranger.get("/api/custom-image/Rem").get_json()
        assert [r["owner"] for r in rows] == [None, None]
        assert not any(r["is_mine"] for r in rows)

    def test_turning_it_back_off_restores_the_name_everywhere(self, client, clean_db, identity_id):
        """Applied at render time, so it is retroactive in both directions."""
        _seed(clean_db, owner=identity_id)
        stranger = client.application.test_client()

        client.patch("/api/me/settings", json={"hide_attribution": True})
        assert stranger.get("/api/custom-image/Rem").get_json()[0]["owner"] is None

        client.patch("/api/me/settings", json={"hide_attribution": False})
        assert stranger.get("/api/custom-image/Rem").get_json()[0]["owner"] is not None


class TestHiddenFromLeaderboard:
    def test_it_removes_you_from_the_ranking_but_not_from_the_data(
        self, client, clean_db, identity_id
    ):
        _seed(clean_db, count=3, owner=identity_id)
        clean_db.bind_discord_identity(identity_id, "discord-1", display_name="Someone")
        assert client.get("/api/stats").get_json()["contributors"] != []

        client.patch("/api/me/settings", json={"hide_from_leaderboard": True})
        assert client.get("/api/stats").get_json()["contributors"] == []
        assert clean_db.count_images_added_by(identity_id) == 3

    def test_it_is_independent_of_attribution(self, client, clean_db, identity_id):
        """Off the ranking, still named on the images -- the case that motivated
        splitting the two switches."""
        _seed(clean_db, owner=identity_id)
        clean_db.bind_discord_identity(identity_id, "discord-1", display_name="Someone")
        client.patch("/api/me/settings", json={"hide_from_leaderboard": True})

        stranger = client.application.test_client()
        assert stranger.get("/api/custom-image/Rem").get_json()[0]["owner"] == "Someone"


class TestGlobalLists:
    def test_hidden_images_are_findable_without_knowing_the_character(
        self, client, clean_db, identity_id
    ):
        """Hiding is otherwise reachable only from the page holding the image."""
        _seed(clean_db, char="Rem", owner=identity_id)
        _seed(clean_db, char="Emilia", owner=identity_id)
        ids = [r["id"] for r in client.get("/api/custom-image/Emilia").get_json()]
        client.post("/api/hide-images", json={"image_ids": ids[:1]})

        hidden = client.get("/api/me/hidden").get_json()
        assert [h["character"] for h in hidden] == ["Emilia"]
        assert hidden[0]["thumb"] == f"/thumbs/{ids[0]}.webp"

    def test_removed_images_are_listed_with_their_character(self, client, clean_db, identity_id):
        _seed(clean_db, char="Rem", owner=identity_id)
        client.post(
            "/api/delete-custom-images",
            json={"character_name": "Rem", "image_urls": ["https://cdn/Rem-0.png"]},
        )
        removed = client.get("/api/me/removed").get_json()
        assert [r["character"] for r in removed] == ["Rem"]

    def test_someone_else_s_hidden_images_are_not_yours(self, client, clean_db, identity_id):
        _seed(clean_db, owner=identity_id)
        ids = [r["id"] for r in client.get("/api/custom-image/Rem").get_json()]
        client.post("/api/hide-images", json={"image_ids": ids})

        stranger = client.application.test_client()
        assert stranger.get("/api/me/hidden").get_json() == []

    def test_contributions_counts_only_your_active_images(self, client, clean_db, identity_id):
        _seed(clean_db, count=3, owner=identity_id)
        assert client.get("/api/me/contributions").get_json() == {"images": 3}

        client.post(
            "/api/delete-custom-images",
            json={"character_name": "Rem", "image_urls": ["https://cdn/Rem-0.png"]},
        )
        assert client.get("/api/me/contributions").get_json() == {"images": 2}
