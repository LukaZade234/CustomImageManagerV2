"""The hand-picked accent override.

The measured accent is usually right but not always -- a character read as
green can be out-voted by blonde hair on area -- so a staff member can point at
a pixel and have that colour win. The override is written through to
`accent_seed` so every existing read path shows it, and the extractor refuses to
recompute over it.
"""

import io

from PIL import Image

import accent_extract
import db


def _thumb(tmp_path, monkeypatch, image_id, colours):
    """A tiny WebP at the path the gallery thumbnail would occupy."""
    monkeypatch.setenv("THUMB_DIR", str(tmp_path))
    img = Image.new("RGB", (len(colours), 1))
    for x, colour in enumerate(colours):
        img.putpixel((x, 0), colour)
    path = tmp_path / f"{image_id}.webp"
    # Lossless: the test asserts the exact pixel, and lossy WebP blends a
    # two-pixel image into a mush.
    img.save(path, "WEBP", lossless=True)
    return path


def _image_id(name):
    row = db.get_connection().execute(
        "SELECT id FROM custom_images WHERE character_id ="
        " (SELECT id FROM characters WHERE name = ?) ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    return int(row["id"])


class TestStorage:
    def test_set_writes_the_seed_through(self, clean_db):
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        assert clean_db.set_accent_override("Yuno Gasai", "#ff88cc", "whoever")
        row = clean_db.get_connection().execute(
            "SELECT accent_override, accent_seed, accent_source, accent_override_by"
            "  FROM characters WHERE name = 'Yuno Gasai'"
        ).fetchone()
        assert row["accent_override"] == "#ff88cc"
        assert row["accent_seed"] == "#ff88cc"
        assert row["accent_source"] == "manual"
        assert row["accent_override_by"] == "whoever"

    def test_clear_drops_both(self, clean_db):
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        clean_db.set_accent_override("Yuno Gasai", "#ff88cc", None)
        assert clean_db.clear_accent_override("Yuno Gasai")
        row = clean_db.get_connection().execute(
            "SELECT accent_override, accent_seed, accent_updated_at"
            "  FROM characters WHERE name = 'Yuno Gasai'"
        ).fetchone()
        assert row["accent_override"] is None
        assert row["accent_seed"] is None
        assert row["accent_updated_at"] is None

    def test_unknown_character_is_false(self, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        assert not clean_db.set_accent_override("Nobody", "#ffffff", None)
        assert not clean_db.clear_accent_override("Nobody")


class TestExtractorRespectsTheOverride:
    def test_ensure_accent_returns_the_override(self, clean_db):
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        clean_db.set_accent_override("Yuno Gasai", "#ff88cc", None)
        assert accent_extract.ensure_accent("Yuno Gasai") == "#ff88cc"

    def test_recompute_does_not_overwrite_it(self, clean_db, monkeypatch):
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        clean_db.set_accent_override("Yuno Gasai", "#ff88cc", None)
        called = []
        monkeypatch.setattr(accent_extract, "extract_seed", lambda *a, **k: called.append(1))
        assert accent_extract.recompute_accent("Yuno Gasai") is None
        assert called == []
        assert clean_db.get_accent_override("Yuno Gasai") == "#ff88cc"


class TestRoute:
    def test_a_normal_user_cannot_set_it(self, client, clean_db, identity_id):
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        res = client.post(
            "/api/accent-override", json={"name": "Yuno Gasai", "seed": "#ff88cc"}
        )
        assert res.status_code == 403
        assert clean_db.get_accent_override("Yuno Gasai") is None

    def test_a_moderator_can_set_it_directly(self, client, clean_db, make_moderator):
        make_moderator()
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        res = client.post(
            "/api/accent-override", json={"name": "Yuno Gasai", "seed": "#FF88CC"}
        )
        assert res.status_code == 200
        assert res.get_json() == {"success": True, "seed": "#ff88cc", "manual": True}
        assert clean_db.get_accent_override("Yuno Gasai") == "#ff88cc"

    def test_a_bad_seed_is_refused(self, client, clean_db, make_moderator):
        make_moderator()
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        res = client.post("/api/accent-override", json={"name": "Yuno Gasai", "seed": "pink"})
        assert res.status_code == 400

    def test_a_clear_needs_no_seed(self, client, clean_db, make_moderator):
        make_moderator()
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        clean_db.set_accent_override("Yuno Gasai", "#ff88cc", None)
        res = client.post("/api/accent-override", json={"name": "Yuno Gasai", "clear": True})
        assert res.status_code == 200
        assert res.get_json()["manual"] is False
        assert clean_db.get_accent_override("Yuno Gasai") is None

    def test_a_gallery_pick_samples_the_pixel(self, client, clean_db, make_moderator, tmp_path, monkeypatch):
        make_moderator()
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        clean_db.add_custom_images("Yuno Gasai", ["https://cdn.example/yuno.png"])
        image_id = _image_id("Yuno Gasai")
        # Two pixels: red at u=0, green at u=1.
        _thumb(tmp_path, monkeypatch, image_id, [(255, 0, 0), (0, 255, 0)])

        res = client.post(
            "/api/accent-override",
            json={"name": "Yuno Gasai", "image_id": image_id, "u": 1.0, "v": 0.0},
        )
        assert res.status_code == 200
        assert res.get_json()["seed"] == "#00ff00"
        assert clean_db.get_accent_override("Yuno Gasai") == "#00ff00"

    def test_a_point_outside_the_image_is_refused(self, client, clean_db, make_moderator):
        make_moderator()
        clean_db.add_character("Yuno Gasai", "Mirai Nikki", "1", "")
        res = client.post(
            "/api/accent-override", json={"name": "Yuno Gasai", "portrait": True, "u": 2, "v": 0}
        )
        assert res.status_code == 400


class TestHexAtPoint:
    def test_reads_the_clicked_pixel(self):
        img = Image.new("RGB", (2, 2))
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((1, 0), (0, 255, 0))
        img.putpixel((0, 1), (0, 0, 255))
        img.putpixel((1, 1), (255, 255, 255))
        assert accent_extract.hex_at_point(img, 0.0, 0.0) == "#ff0000"
        assert accent_extract.hex_at_point(img, 1.0, 0.0) == "#00ff00"
        assert accent_extract.hex_at_point(img, 0.0, 1.0) == "#0000ff"

    def test_open_image_bytes_does_not_downsample(self):
        img = Image.new("RGB", (500, 500), (10, 20, 30))
        buffer = io.BytesIO()
        img.save(buffer, "PNG")
        opened = accent_extract.open_image_bytes(buffer.getvalue())
        assert opened is not None
        assert opened.size == (500, 500)
