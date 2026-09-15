"""Adding an image requires a linked Discord account.

A cookie-only visitor may browse and curate their own view freely, but uploading
bytes to ImgChest is tied to a real account on purpose: it can be held to, and it
is what makes a ban mean something — clearing a cookie mints a fresh pseudonym
for free, so a rule that ignored the account would be no rule at all.

Browsing, saving, hiding, reporting, restoring and editing metadata stay open.
"""

import io

from PIL import Image

import catalog_import


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buf, "PNG")
    buf.seek(0)
    return buf


def _catalog_row(name, series, rank):
    return {
        "name": name,
        "name_key": catalog_import.name_key(name),
        "series": series,
        "rank": rank,
        "mudae_image_url": f"https://mudae.net/uploads/{rank}/a~b.png",
        "pool": "wa",
        "is_waifu": True,
        "is_anime": True,
    }


class TestCookieOnlyIsRefused:
    def test_custom_image_upload(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        res = client.post(
            "/api/custom-image",
            data={"character_name": "Rem", "files": (_png(), "a.png")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 403
        assert res.get_json()["code"] == "discord_required"

    def test_import_from_urls(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        res = client.post(
            "/api/import-custom-images-from-urls",
            json={"character_name": "Rem", "urls": ["https://i.pinimg.com/x.png"]},
        )
        assert res.status_code == 403

    def test_set_main_image(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        res = client.post(
            "/api/set-main-image",
            data={"character_name": "Rem", "file": (_png(), "m.png")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 403

    def test_legacy_upload(self, client, clean_db):
        res = client.post(
            "/upload", data={"file": (_png(), "a.png")}, content_type="multipart/form-data"
        )
        assert res.status_code == 403

    def test_add_character_with_a_file(self, client, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        res = client.post(
            "/api/add-character",
            data={"name": "Newcomer", "series": "S", "image": (_png(), "n.png")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 403


class TestSignedInIsAllowed:
    def test_custom_image_upload(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        clean_db.add_character("Rem", "Re:Zero", "1", "")
        monkeypatch.setattr(
            "routes.customs.upload_to_imgchest",
            lambda path, upload_name=None: ("post", "https://cdn.imgchest.com/files/a.png"),
        )
        res = client.post(
            "/api/custom-image",
            data={"character_name": "Rem", "files": (_png(), "a.png")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        assert res.get_json()["success"] is True

    def test_add_character_with_a_file(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        clean_db.add_character("Seed", "S", "1", "")
        monkeypatch.setattr(
            "routes.characters.upload_to_imgchest",
            lambda path, upload_name=None: ("post", "https://cdn.imgchest.com/files/a.png"),
        )
        res = client.post(
            "/api/add-character",
            data={"name": "Newcomer", "series": "S", "image": (_png(), "n.png")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200


class TestAddingACharacter:
    """A cookie-only visitor may add a catalog character, not invent one."""

    def test_a_cookie_only_visitor_cannot_add_a_brand_new_character(self, client, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        res = client.post("/api/add-character", data={"name": "Brand New", "series": "S"})
        assert res.status_code == 403
        assert res.get_json()["code"] == "discord_required"

    def test_a_cookie_only_visitor_can_add_one_from_the_catalog(self, client, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        clean_db.upsert_catalog_characters(
            [_catalog_row("Known One", "S", "10")],
            scraped_at="2026-01-01T00:00:00Z",
            source_batch="test",
        )
        res = client.post(
            "/api/add-character",
            data={"name": "Known One", "series": "S", "image_url": "https://mudae.net/x.png"},
        )
        assert res.status_code == 200, res.get_json()

    def test_a_signed_in_visitor_can_add_a_brand_new_character(self, client, clean_db, make_signed_in):
        make_signed_in()
        clean_db.add_character("Seed", "S", "1", "")
        res = client.post("/api/add-character", data={"name": "Brand New", "series": "S"})
        assert res.status_code == 200, res.get_json()
