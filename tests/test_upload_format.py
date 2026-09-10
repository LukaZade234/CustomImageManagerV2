"""Upload normalisation and ImgChest naming.

Two rules, both learned the hard way from what is already in the library:

- Decide by the file's **bytes**, never its name. Deciding by extension is how
  WebP files ended up stored under `.png` names, and how uploads skipped the
  dimension cap entirely — there is an 11,036px image in there because of it.
- Keep the `.png` extension regardless. Mudae's $ai command will not accept a
  URL that does not end in .png, but it renders whatever bytes arrive.
"""

import io

import pytest
from PIL import Image

import image_utils
from upload_imgchest import imgchest_filename


def _write(tmp_path, name, fmt, size=(800, 1200), mode="RGB", **kw):
    path = tmp_path / name
    Image.new(mode, size, "red").save(path, fmt, **kw)
    return str(path)


class TestFormatDetection:
    @pytest.mark.parametrize(
        ("fmt", "expected"), [("PNG", "PNG"), ("WEBP", "WEBP"), ("GIF", "GIF"), ("JPEG", "JPEG")]
    )
    def test_reads_the_bytes(self, tmp_path, fmt, expected):
        assert image_utils.detect_format(_write(tmp_path, f"x.{fmt}", fmt)) == expected

    def test_a_lying_extension_does_not_fool_it(self, tmp_path):
        """The exact case already in the library: WebP bytes, .png name."""
        assert image_utils.detect_format(_write(tmp_path, "actually_webp.png", "WEBP")) == "WEBP"

    def test_unrecognised_is_none(self, tmp_path):
        path = tmp_path / "notes.png"
        path.write_bytes(b"this is not an image")
        assert image_utils.detect_format(str(path)) is None


class TestPrepareForUpload:
    def test_output_is_webp_under_a_png_name(self, tmp_path):
        out, err = image_utils.prepare_for_upload(_write(tmp_path, "in.jpg", "JPEG"))
        assert err is None
        assert out.endswith(".png")
        assert image_utils.detect_format(out) == "WEBP"

    def test_a_png_is_converted_too(self, tmp_path):
        """The old fast path skipped .png entirely, which is how uncapped images
        and unstripped metadata got in."""
        out, err = image_utils.prepare_for_upload(_write(tmp_path, "in.png", "PNG"))
        assert err is None
        assert image_utils.detect_format(out) == "WEBP"

    def test_oversized_images_are_capped(self, tmp_path):
        out, _ = image_utils.prepare_for_upload(
            _write(tmp_path, "big.png", "PNG", size=(5000, 3000))
        )
        with Image.open(out) as img:
            assert max(img.size) == image_utils.MAX_DIMENSION

    def test_a_normal_image_keeps_its_resolution(self, tmp_path):
        out, _ = image_utils.prepare_for_upload(_write(tmp_path, "ok.png", "PNG", size=(900, 1400)))
        with Image.open(out) as img:
            assert img.size == (900, 1400)

    def test_it_is_much_smaller_than_the_png_it_replaces(self, tmp_path):
        source = _write(tmp_path, "in.png", "PNG", size=(1500, 2000))
        import os

        before = os.path.getsize(source)
        out, _ = image_utils.prepare_for_upload(source)
        assert os.path.getsize(out) < before

    def test_an_existing_still_webp_is_not_re_encoded(self, tmp_path):
        """Lossy to lossy compounds artefacts for no gain."""
        source = _write(tmp_path, "in.webp", "WEBP", size=(900, 1200), quality=90)
        import os

        before = os.path.getsize(source)
        out, err = image_utils.prepare_for_upload(source)
        assert err is None
        assert os.path.getsize(out) == before

    def test_transparency_is_preserved(self, tmp_path):
        source = _write(tmp_path, "in.png", "PNG", mode="RGBA", size=(400, 400))
        out, _ = image_utils.prepare_for_upload(source)
        with Image.open(out) as img:
            assert img.convert("RGBA").getpixel((0, 0))[3] == 255

    def test_junk_is_refused_rather_than_uploaded(self, tmp_path):
        path = tmp_path / "junk.png"
        path.write_bytes(b"nope")
        out, err = image_utils.prepare_for_upload(str(path))
        assert out is None and err


class TestNaming:
    def test_carries_the_character_and_the_index(self):
        name = imgchest_filename("Lucy", 13)
        assert name.startswith("lucy-013-")
        assert name.endswith(".png")

    def test_pads_so_names_sort(self):
        names = sorted(imgchest_filename("Lucy", i) for i in (2, 13, 104))
        assert [n.split("-")[1] for n in names] == ["002", "013", "104"]

    def test_spaces_and_punctuation_become_hyphens(self):
        assert imgchest_filename("Re:Zero Rem", 1).startswith("re-zero-rem-001-")

    def test_accents_are_folded_not_dropped(self):
        assert imgchest_filename("Frédérica", 1).startswith("frederica-001-")

    def test_a_main_image_is_labelled_instead_of_numbered(self):
        assert imgchest_filename("Lucy", kind="main").startswith("lucy-main-")

    def test_an_empty_name_still_produces_something_usable(self):
        assert imgchest_filename("", 2).startswith("unknown-002-")

    def test_a_very_long_name_is_trimmed(self):
        name = imgchest_filename("A" * 200, 1)
        assert len(name.split("-")[0]) <= 40

    def test_the_extension_is_always_png(self):
        """Mudae rejects a URL that does not end in .png, whatever the bytes are."""
        for args in [("Lucy", 1), ("Lucy", None, "main"), ("", 999)]:
            assert imgchest_filename(*args).endswith(".png")


class TestIndexNeverRepeats:
    """An ImgChest name is fixed at upload time and can never be corrected, so a
    number that gets reused is worse than useless."""

    def test_removing_an_image_does_not_free_its_number(self, clean_db, identity_id):
        clean_db.ensure_identity(identity_id)
        clean_db.add_custom_images("Lucy", ["https://cdn/1.png"], added_by=identity_id)
        assert clean_db.count_custom_images_ever("Lucy") == 1

        clean_db.remove_custom_images("Lucy", ["https://cdn/1.png"], identity_id)
        assert clean_db.count_custom_images_ever("Lucy") == 1, (
            "the next upload would otherwise reuse index 1"
        )

        clean_db.add_custom_images("Lucy", ["https://cdn/2.png"], added_by=identity_id)
        assert clean_db.count_custom_images_ever("Lucy") == 2

    def test_it_climbs_across_an_upload_remove_upload_cycle(self, clean_db, identity_id):
        """Exactly the sequence that produced three files called lucy-118."""
        clean_db.ensure_identity(identity_id)
        seen = []
        for n in range(3):
            url = f"https://cdn/{n}.png"
            seen.append(clean_db.count_custom_images_ever("Lucy") + 1)
            clean_db.add_custom_images("Lucy", [url], added_by=identity_id)
            clean_db.remove_custom_images("Lucy", [url], identity_id)
        assert seen == [1, 2, 3]

    def test_reordering_does_not_disturb_it(self, clean_db):
        urls = [f"https://cdn/{n}.png" for n in range(3)]
        clean_db.add_custom_images("Lucy", urls)
        clean_db.reorder_custom_images("Lucy", list(reversed(urls)))
        assert clean_db.count_custom_images_ever("Lucy") == 3
