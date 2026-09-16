"""Endpoint behaviour for the custom-image routes.

These pin the status codes across two storage rewrites: Phase 2 replaced
read-modify-write with atomic mutation, and Phase 3 replaced JSON documents with
rows. Both changed the control flow underneath these routes while the responses
had to stay identical, which is exactly what these assertions protect.
"""

import json

import pytest

import ratelimit


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _seed(db, mapping: dict, owner: str | None = None) -> None:
    """Seed images, optionally attributed to an owner.

    Phase 6 made removal ownership-scoped, so a test that expects a delete to
    succeed has to seed images the caller actually owns. Unowned images (the
    v1-migrated case) are covered in test_moderation.py.
    """
    if owner is not None:
        db.ensure_identity(owner)
    for name, urls in mapping.items():
        db.add_custom_images(name, urls, added_by=owner)


class TestDeleteOne:
    def test_unknown_character_is_404(self, client, clean_db):
        r = _post(
            client, "/api/delete-custom-image", {"character_name": "Nobody", "image_url": "x"}
        )
        assert r.status_code == 404
        assert r.get_json()["error"] == "Character not found"

    def test_unknown_image_is_404(self, client, clean_db, identity_id):
        _seed(clean_db, {"Rem": ["https://cdn/a.png"]}, identity_id)
        r = _post(
            client,
            "/api/delete-custom-image",
            {"character_name": "Rem", "image_url": "https://cdn/zz.png"},
        )
        assert r.status_code == 404
        assert r.get_json()["error"] == "Image not found"

    def test_deletes_only_the_named_image(self, client, clean_db, identity_id):
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]}, identity_id)
        r = _post(
            client,
            "/api/delete-custom-image",
            {"character_name": "Rem", "image_url": "https://cdn/a.png"},
        )
        assert r.status_code == 200
        assert clean_db.get_custom_images_for("Rem") == ["https://cdn/b.png"]


class TestDeleteMany:
    def test_unknown_character_is_404(self, client, clean_db):
        r = _post(
            client, "/api/delete-custom-images", {"character_name": "Nobody", "image_urls": ["x"]}
        )
        assert r.status_code == 404

    def test_no_match_reports_the_breakdown_rather_than_an_error(
        self, client, clean_db, identity_id
    ):
        """Still 200. Phase 6 replaced the message with a per-URL breakdown so a
        partial refusal can be explained instead of silently dropped."""
        _seed(clean_db, {"Rem": ["https://cdn/a.png"]}, identity_id)
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/zz.png"]},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["removed"] == []
        assert body["missing"] == ["https://cdn/zz.png"]
        assert clean_db.get_custom_images_for("Rem") == ["https://cdn/a.png"]

    def test_deletes_the_named_subset_and_keeps_order(self, client, clean_db, identity_id):
        _seed(clean_db, {"Rem": [f"https://cdn/{c}.png" for c in "abcd"]}, identity_id)
        r = _post(
            client,
            "/api/delete-custom-images",
            {"character_name": "Rem", "image_urls": ["https://cdn/b.png", "https://cdn/d.png"]},
        )
        assert r.status_code == 200
        assert clean_db.get_custom_images_for("Rem") == ["https://cdn/a.png", "https://cdn/c.png"]


class TestReorder:
    @pytest.fixture(autouse=True)
    def _signed_in(self, make_signed_in):
        """Reordering requires a Discord account; the tests here are about order."""
        make_signed_in()

    def test_unknown_character_is_404(self, client, clean_db):
        r = _post(
            client, "/api/reorder-custom-images", {"character_name": "Nobody", "new_order": ["x"]}
        )
        assert r.status_code == 404

    def test_applies_the_requested_order(self, client, clean_db):
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png", "https://cdn/c.png"]})
        r = _post(
            client,
            "/api/reorder-custom-images",
            {
                "character_name": "Rem",
                "new_order": ["https://cdn/c.png", "https://cdn/a.png", "https://cdn/b.png"],
            },
        )
        assert r.status_code == 200
        assert clean_db.get_custom_images_for("Rem") == [
            "https://cdn/c.png",
            "https://cdn/a.png",
            "https://cdn/b.png",
        ]

    def test_keeps_images_added_after_the_client_loaded_the_page(self, client, clean_db):
        """A stale reorder must not delete someone else's upload.

        Assigning `new_order` wholesale -- what the code did before Phase 2 --
        silently dropped any image added between page load and submit.
        """
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]})
        # Someone else uploads while the reorder dialog is open.
        clean_db.add_custom_images("Rem", ["https://cdn/new.png"])

        r = _post(
            client,
            "/api/reorder-custom-images",
            {"character_name": "Rem", "new_order": ["https://cdn/b.png", "https://cdn/a.png"]},
        )
        assert r.status_code == 200
        stored = clean_db.get_custom_images_for("Rem")
        assert stored[:2] == ["https://cdn/b.png", "https://cdn/a.png"], (
            "requested order not applied"
        )
        assert "https://cdn/new.png" in stored, "a concurrently added image was lost"

    def test_ignores_images_that_no_longer_exist(self, client, clean_db):
        _seed(clean_db, {"Rem": ["https://cdn/a.png"]})
        r = _post(
            client,
            "/api/reorder-custom-images",
            {
                "character_name": "Rem",
                "new_order": ["https://cdn/deleted.png", "https://cdn/a.png"],
            },
        )
        assert r.status_code == 200
        assert clean_db.get_custom_images_for("Rem") == ["https://cdn/a.png"]


class TestReorderRequiresAnAccount:
    """A reorder changes what everyone sees, so it is tied to an account.

    `DECISIONS.md` §1 treats prominence as removal's equal, and a cookie can be
    cleared for free -- so the rule has to hang on the Discord link, not the
    cookie. A suspended or banned account is refused by the write gate before
    the route is ever reached.
    """

    def test_a_cookie_only_visitor_is_refused(self, client, clean_db):
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]})

        r = _post(
            client,
            "/api/reorder-custom-images",
            {"character_name": "Rem", "new_order": ["https://cdn/b.png", "https://cdn/a.png"]},
        )

        assert r.status_code == 403
        assert r.get_json()["code"] == "discord_required"
        # The order is untouched.
        assert clean_db.get_custom_images_for("Rem") == [
            "https://cdn/a.png",
            "https://cdn/b.png",
        ]

    def test_a_signed_in_visitor_may_reorder(self, client, clean_db, make_signed_in):
        make_signed_in()
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]})

        r = _post(
            client,
            "/api/reorder-custom-images",
            {"character_name": "Rem", "new_order": ["https://cdn/b.png", "https://cdn/a.png"]},
        )

        assert r.status_code == 200

    def test_a_banned_account_cannot_reorder(self, client, clean_db, identity_id, make_signed_in):
        make_signed_in()
        clean_db.set_moderation_status(identity_id, "banned", reason="spam")
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]})

        r = _post(
            client,
            "/api/reorder-custom-images",
            {"character_name": "Rem", "new_order": ["https://cdn/b.png", "https://cdn/a.png"]},
        )

        assert r.status_code == 403
        assert "banned" in r.get_json()["error"].lower()

    def test_reordering_is_rate_limited(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        _seed(clean_db, {"Rem": ["https://cdn/a.png", "https://cdn/b.png"]})
        monkeypatch.setitem(ratelimit.RATE_LIMITS, "reorder", [(1, 60)])

        payload = {
            "character_name": "Rem",
            "new_order": ["https://cdn/b.png", "https://cdn/a.png"],
        }
        assert _post(client, "/api/reorder-custom-images", payload).status_code == 200
        assert _post(client, "/api/reorder-custom-images", payload).status_code == 429

    def test_a_server_error_does_not_leak_internals(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        make_signed_in()
        _seed(clean_db, {"Rem": ["https://cdn/a.png"]})

        def boom(*_args, **_kwargs):
            raise RuntimeError("SECRET-INTERNAL-DETAIL")

        monkeypatch.setattr(clean_db, "reorder_custom_images", boom)

        r = _post(
            client,
            "/api/reorder-custom-images",
            {"character_name": "Rem", "new_order": ["https://cdn/a.png"]},
        )

        assert r.status_code == 500
        assert r.get_json()["error"] == "Could not save the new order."
        assert "SECRET-INTERNAL-DETAIL" not in r.get_data(as_text=True)


class TestSaved:
    def test_saving_twice_is_rejected(self, client, clean_db, identity_id):
        payload = {"name": "Rem", "series": "Re:Zero", "rank": "#1"}
        assert _post(client, "/api/saved", payload).status_code == 200
        r = _post(client, "/api/saved", payload)
        assert r.status_code == 400
        assert r.get_json()["error"] == "Character already saved"
        assert len(clean_db.get_saved_characters(identity_id)) == 1

    def test_removing_an_unsaved_character_is_404(self, client, clean_db):
        assert client.delete("/api/saved/Nobody").status_code == 404

    def test_remove_deletes_only_that_character(self, client, clean_db, identity_id):
        _post(client, "/api/saved", {"name": "Rem"})
        _post(client, "/api/saved", {"name": "Emilia"})
        assert client.delete("/api/saved/Rem").status_code == 200
        assert [c["name"] for c in clean_db.get_saved_characters(identity_id)] == ["Emilia"]

    def test_saved_follows_the_identity(self, client, clean_db, identity_id):
        """The regression: signing out must not leave the previous list behind."""
        _post(client, "/api/saved", {"name": "Rem"})
        assert [c["name"] for c in client.get("/api/saved").get_json()] == ["Rem"]

        # Signing out hands out a fresh anonymous identity.
        client.post("/api/auth/logout")
        assert client.get("/api/saved").get_json() == []
