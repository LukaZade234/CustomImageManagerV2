"""Gallery thumbnails.

The invariant that matters most: the ImgChest URL stays canonical. Mudae's `$ai`
command accepts nothing else, so a thumbnail may only ever be what the grid
*renders* — never what the app stores, hands out, or builds a command from.
"""

import io

import pytest
from PIL import Image

import thumbnails


def _png(width, height, mode="RGB"):
    buffer = io.BytesIO()
    # A half-transparent fill for RGBA: a fully opaque one lets the WebP encoder
    # drop the alpha channel, which would make the transparency test pass for
    # the wrong reason.
    colour = (255, 0, 0, 128) if mode == "RGBA" else "red"
    Image.new(mode, (width, height), colour).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def thumb_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("THUMB_DIR", str(tmp_path / "thumbs"))
    return tmp_path / "thumbs"


class TestRendering:
    def test_scales_the_longest_edge_down(self):
        out = thumbnails.render(_png(2000, 1000))
        with Image.open(io.BytesIO(out)) as img:
            assert max(img.size) == thumbnails.MAX_EDGE
            assert img.format == "WEBP"

    def test_keeps_the_aspect_ratio(self):
        out = thumbnails.render(_png(1200, 800))
        with Image.open(io.BytesIO(out)) as img:
            assert img.size[0] / img.size[1] == pytest.approx(1.5, abs=0.01)

    def test_a_small_image_is_not_enlarged(self):
        out = thumbnails.render(_png(120, 90))
        with Image.open(io.BytesIO(out)) as img:
            assert img.size == (120, 90)

    def test_transparency_survives(self):
        """Character art is often cut out with a transparent background."""
        out = thumbnails.render(_png(400, 400, mode="RGBA"))
        with Image.open(io.BytesIO(out)) as img:
            assert img.convert("RGBA").getpixel((0, 0))[3] < 255

    def test_it_is_much_smaller_than_the_source(self):
        """The entire justification: 1.9 MB PNGs were being sent to draw a grid."""
        source = _png(1600, 2400)
        assert len(thumbnails.render(source)) < len(source) / 2

    def test_junk_raises_rather_than_producing_a_broken_file(self):
        with pytest.raises(Exception):
            thumbnails.render(b"not an image")


class TestNaming:
    def test_a_png_gets_a_thumbnail(self):
        assert thumbnails.thumb_url(7, "https://cdn/x.png") == "/thumbs/7.webp"

    def test_a_gif_does_not(self):
        """Animation is usually why the image was chosen; a still would lose it."""
        assert thumbnails.thumb_url(7, "https://cdn/x.gif") is None

    def test_a_query_string_does_not_hide_the_extension(self):
        assert thumbnails.thumb_url(7, "https://cdn/x.gif?v=2") is None

    def test_the_key_is_the_row_id_not_the_url(self):
        """So the endpoint can only be asked for images already in the database."""
        assert thumbnails.thumb_url(42, "https://anything/at/all.png") == "/thumbs/42.webp"


class TestStore:
    def test_writes_and_leaves_no_partial_files(self, thumb_dir):
        thumbnails.store(5, b"data")
        assert thumbnails.cache_path(5).read_bytes() == b"data"
        assert list(thumb_dir.glob("*.part")) == []

    def test_creates_the_directory(self, thumb_dir):
        assert not thumb_dir.exists()
        thumbnails.store(1, b"x")
        assert thumb_dir.is_dir()


class TestEndpoint:
    """The route calls `_get_with_validated_redirects` as a name in its own
    module's namespace, so the patch goes on routes.media rather than on
    remote_images, where the function is defined."""

    def _seed(self, db, url="https://cdn/a.png"):
        db.add_custom_images("Rem", [url])
        return db.get_custom_image_rows("Rem")[0]["id"]

    def test_a_cached_thumbnail_is_served_with_immutable_caching(self, client, clean_db):
        image_id = self._seed(clean_db)
        thumbnails.store(image_id, thumbnails.render(_png(800, 1200)))
        response = client.get(f"/thumbs/{image_id}.webp")
        assert response.status_code == 200
        assert response.mimetype == "image/webp"
        assert "immutable" in response.headers["Cache-Control"]

    def test_an_unknown_image_is_404(self, client, clean_db):
        assert client.get("/thumbs/999999.webp").status_code == 404

    def test_it_generates_on_first_request(self, client, clean_db, monkeypatch):
        image_id = self._seed(clean_db)

        class _Response:
            status_code = 200
            content = _png(1000, 1500)

        monkeypatch.setattr(
            "routes.media._get_with_validated_redirects", lambda url, **kw: _Response()
        )
        assert not thumbnails.cache_path(image_id).exists()
        assert client.get(f"/thumbs/{image_id}.webp").status_code == 200
        assert thumbnails.cache_path(image_id).is_file()

    def test_a_gif_redirects_to_the_original(self, client, clean_db):
        image_id = self._seed(clean_db, "https://cdn/a.gif")
        response = client.get(f"/thumbs/{image_id}.webp")
        assert response.status_code == 302
        assert response.headers["Location"] == "https://cdn/a.gif"

    def test_a_failed_fetch_redirects_rather_than_erroring(self, client, clean_db, monkeypatch):
        """A thumbnail is an optimisation; losing one should cost bandwidth, not
        leave a broken image on the page."""
        image_id = self._seed(clean_db)

        def _boom(url, **kwargs):
            raise ValueError("upstream is down")

        monkeypatch.setattr("routes.media._get_with_validated_redirects", _boom)
        response = client.get(f"/thumbs/{image_id}.webp")
        assert response.status_code == 302
        assert response.headers["Location"] == "https://cdn/a.png"

    def test_removed_images_still_thumbnail(self, client, clean_db, identity_id):
        """The Removed drawer shows them, so they need to render."""
        clean_db.ensure_identity(identity_id)
        clean_db.add_custom_images("Rem", ["https://cdn/gone.png"], added_by=identity_id)
        image_id = clean_db.get_custom_image_rows("Rem")[0]["id"]
        clean_db.remove_custom_images("Rem", ["https://cdn/gone.png"], identity_id)
        assert clean_db.get_image_url(image_id) == "https://cdn/gone.png"


class TestCanonicalUrlIsUntouched:
    def test_the_stored_url_is_still_the_imgchest_png(self, clean_db):
        """A thumbnail must never become what the app stores or hands out."""
        clean_db.add_custom_images("Rem", ["https://cdn.imgchest.com/files/abc.png"])
        row = clean_db.get_custom_image_rows("Rem")[0]
        assert row["url"] == "https://cdn.imgchest.com/files/abc.png"
        assert row["thumb"] != row["url"]

    def test_the_url_list_used_for_commands_holds_no_thumbnails(self, clean_db):
        """get_custom_images_for feeds the $ai command builder."""
        clean_db.add_custom_images("Rem", ["https://cdn.imgchest.com/files/abc.png"])
        assert clean_db.get_custom_images_for("Rem") == ["https://cdn.imgchest.com/files/abc.png"]
