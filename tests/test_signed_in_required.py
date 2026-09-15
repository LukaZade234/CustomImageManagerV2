"""Adding an image requires a linked Discord account.

A cookie-only visitor may browse and curate their own view freely, but uploading
bytes to ImgChest is tied to a real account on purpose: it can be held to, and it
is what makes a ban mean something — clearing a cookie mints a fresh pseudonym
for free, so a rule that ignored the account would be no rule at all.

Browsing, saving, hiding, reporting, restoring and editing metadata stay open.
"""

import io

from PIL import Image


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buf, "PNG")
    buf.seek(0)
    return buf


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

    def test_catalog_add_without_a_file_needs_no_account(self, client, clean_db):
        # A catalog portrait is a link, not an upload, so the gate does not apply.
        clean_db.add_character("Seed", "S", "1", "")
        res = client.post(
            "/api/add-character",
            data={"name": "Newcomer", "series": "S", "image_url": "https://mudae.net/x.png"},
        )
        assert res.status_code == 200
