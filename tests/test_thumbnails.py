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
        with pytest.raises(Image.UnidentifiedImageError):
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

    def test_a_mirrored_row_returns_its_r2_key(self):
        """No leading slash: that is how the client knows to use the image origin."""
        assert thumbnails.thumb_url(7, "https://cdn/x.png", "thumbs/7-abcd.webp") == (
            "thumbs/7-abcd.webp"
        )

    def test_a_gif_has_no_thumbnail_even_with_a_key(self):
        assert thumbnails.thumb_url(7, "https://cdn/x.gif", "thumbs/7-abcd.webp") is None


class TestMirrorKey:
    def test_is_deterministic_and_carries_the_row_id(self):
        key = thumbnails.object_key(42, b"webp-bytes")
        assert key.startswith("thumbs/42-")
        assert key.endswith(".webp")
        assert key == thumbnails.object_key(42, b"webp-bytes")

    def test_changes_when_the_bytes_change(self):
        """A re-render must be a new object, or the edge serves the old one for a year."""
        assert thumbnails.object_key(42, b"a") != thumbnails.object_key(42, b"b")


class TestStore:
    def test_writes_and_leaves_no_partial_files(self, thumb_dir):
        thumbnails.store(5, b"data")
        assert thumbnails.cache_path(5).read_bytes() == b"data"
        assert list(thumb_dir.glob("*.part")) == []

    def test_creates_the_directory(self, thumb_dir):
        assert not thumb_dir.exists()
        thumbnails.store(1, b"x")
        assert thumb_dir.is_dir()


class TestThumbKeyStorage:
    def test_recording_a_key_changes_what_the_row_reports(self, clean_db):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])
        image_id = clean_db.get_custom_image_rows("Rem")[0]["id"]

        assert clean_db.set_thumb_key(image_id, "thumbs/1-abc.webp") is True
        assert clean_db.get_custom_image_rows("Rem")[0]["thumb"] == "thumbs/1-abc.webp"
        assert clean_db.images_missing_thumb_key() == []

    def test_missing_lists_only_unmirrored_rows(self, clean_db):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png", "https://cdn/b.png"])
        rows = clean_db.images_missing_thumb_key()
        assert len(rows) == 2

        clean_db.set_thumb_key(rows[0]["id"], "thumbs/1-abc.webp")
        remaining = clean_db.images_missing_thumb_key()
        assert [r["id"] for r in remaining] == [rows[1]["id"]]


class TestEndpoint:
    """The route calls `_get_with_validated_redirects` as a name in its own
    module's namespace, so the patch goes on routes.media rather than on
    remote_images, where the function is defined."""

    def _seed(self, db, url="https://cdn/a.png"):
        db.add_custom_images("Rem", [url])
        return db.get_custom_image_rows("Rem")[0]["id"]

    def test_a_cached_thumbnail_is_not_marked_immutable(self, client, clean_db):
        """Short cache only: the URL is keyed by a row id, which a cut-over reuses.

        This used to assert `immutable`, on the reasoning that a row id never
        changes its URL. It does not hold across a database rebuild. Stale
        thumbnails from the pre-cut-over database were served as immutable from
        the edge and rendered other characters' images for URLs that were even
        dead, and clearing the origin's files changed nothing.
        """
        image_id = self._seed(clean_db)
        thumbnails.store(image_id, thumbnails.render(_png(800, 1200)))
        response = client.get(f"/thumbs/{image_id}.webp")
        assert response.status_code == 200
        assert response.mimetype == "image/webp"
        cache_control = response.headers["Cache-Control"]
        assert "immutable" not in cache_control
        assert "max-age=300" in cache_control

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

    def test_it_mirrors_and_records_the_key_on_generation(self, client, clean_db, monkeypatch):
        """The grid only moves to the CDN once the key is on the row."""
        image_id = self._seed(clean_db)

        class _Response:
            status_code = 200
            content = _png(1000, 1500)

        monkeypatch.setattr(
            "routes.media._get_with_validated_redirects", lambda url, **kw: _Response()
        )
        monkeypatch.setattr(
            thumbnails, "mirror", lambda image_id, data: f"thumbs/{image_id}-deadbeef.webp"
        )

        assert client.get(f"/thumbs/{image_id}.webp").status_code == 200
        row = clean_db.get_custom_image_rows("Rem")[0]
        assert row["thumb"] == f"thumbs/{image_id}-deadbeef.webp"

    def test_a_missing_mirror_leaves_it_on_the_api_path(self, client, clean_db, monkeypatch):
        """No rclone (or a failed upload) must not cost the thumbnail, only the CDN."""
        image_id = self._seed(clean_db)

        class _Response:
            status_code = 200
            content = _png(1000, 1500)

        monkeypatch.setattr(
            "routes.media._get_with_validated_redirects", lambda url, **kw: _Response()
        )
        monkeypatch.setattr(thumbnails, "mirror", lambda image_id, data: None)

        assert client.get(f"/thumbs/{image_id}.webp").status_code == 200
        assert clean_db.get_custom_image_rows("Rem")[0]["thumb"] == f"/thumbs/{image_id}.webp"

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
