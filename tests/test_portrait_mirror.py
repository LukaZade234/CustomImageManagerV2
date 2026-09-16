"""Mirroring the catalog portraits to our own CDN.

Portraits come from `mudae.net` and are display-only, so they are mirrored to R2
as WebP and the recorded key is preferred over the hotlink. These tests cover the
two halves that can be tested without a network or an R2 bucket: which rows are
candidates, and that recording a key reaches both the catalog and the working
row that shares the portrait.
"""

import importlib.util
from pathlib import Path

import catalog_import

_REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "mirror_portraits_to_r2", _REPO_ROOT / "scripts" / "mirror_portraits_to_r2.py"
)
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)


def _catalog_row(name, image, **facets):
    row = {
        "name": name,
        "name_key": catalog_import.name_key(name),
        "series": "S",
        "rank": "1",
        "mudae_image_url": image,
        "pool": "wa",
        "is_waifu": True,
    }
    row.update(facets)
    return row


def _seed_catalog(clean_db, rows):
    clean_db.upsert_catalog_characters(rows, scraped_at="2026-01-01T00:00:00Z", source_batch="test")


class TestSelection:
    def test_only_mudae_portraits_without_a_mirror(self, clean_db):
        _seed_catalog(
            clean_db,
            [
                _catalog_row("Rem", "https://mudae.net/uploads/1/a.png"),
                # Already on our own CDN: not a hotlink, nothing to mirror.
                _catalog_row("Hosted", "https://cdn.imgchest.com/files/x.png"),
                _catalog_row("Done", "https://mudae.net/uploads/2/b.png"),
            ],
        )
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Done"), "portraits/2-x.webp")]
        )

        remaining = [r["name"] for r in clean_db.catalog_portraits_to_mirror()]
        assert remaining == ["Rem"]

    def test_redo_includes_already_mirrored_rows(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-x.webp")]
        )

        assert clean_db.catalog_portraits_to_mirror() == []
        redone = clean_db.catalog_portraits_to_mirror(redo=True)
        assert [r["name"] for r in redone] == ["Rem"]

    def test_limit_caps_the_batch(self, clean_db):
        _seed_catalog(
            clean_db,
            [
                _catalog_row("A", "https://mudae.net/uploads/1/a.png"),
                _catalog_row("B", "https://mudae.net/uploads/2/b.png"),
            ],
        )
        assert len(clean_db.catalog_portraits_to_mirror(limit=1)) == 1


class TestRecording:
    def test_reaches_the_catalog_and_a_working_row_sharing_the_portrait(self, clean_db):
        url = "https://mudae.net/uploads/1/a.png"
        _seed_catalog(clean_db, [_catalog_row("Rem", url)])
        clean_db.add_character("Rem", "S", "1", url)

        written = clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )

        assert written == 1
        assert clean_db.find_character("Rem")["image_thumb"] == "portraits/1-abcdef12.webp"

    def test_a_hand_uploaded_main_image_still_shows_the_catalog_portrait(self, clean_db):
        # The main image is display-only, so the catalog's Mudae art wins even
        # when the working row carries an ImgChest main image.
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.add_character("Rem", "S", "1", "https://cdn.imgchest.com/files/mine.png")

        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )

        assert clean_db.find_character("Rem")["image_thumb"] == "portraits/1-abcdef12.webp"


class TestAutoSyncOnWrite:
    def test_adding_a_row_picks_up_an_existing_mirror(self, clean_db):
        # The guard in add_character: a row created after the catalog was
        # mirrored is wired to the mirror immediately, no batch sync required.
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )
        clean_db.add_character("Rem", "S", "1", "https://cdn.imgchest.com/files/mine.png")

        assert clean_db.find_character("Rem")["image_thumb"] == "portraits/1-abcdef12.webp"

    def test_setting_a_main_image_reapplies_the_catalog_mirror(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.add_character("Rem", "S", "1", "")
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )
        # A custom main image is stored, but display keeps preferring the mirror.
        clean_db.set_main_image("Rem", "https://cdn.imgchest.com/files/mine.png")

        row = clean_db.find_character("Rem")
        assert row["image"] == "https://cdn.imgchest.com/files/mine.png"
        assert row["image_thumb"] == "portraits/1-abcdef12.webp"


class TestSyncThumbs:
    def test_sync_reaches_rows_the_mirror_run_preceded(self, clean_db):
        # A catalog mirror recorded behind a working row's back (bypassing the
        # per-row sync) is caught by the bulk sync.
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.add_character("Rem", "S", "1", "https://cdn.imgchest.com/files/mine.png")
        assert clean_db.find_character("Rem")["image_thumb"] == ""
        with clean_db.transaction() as conn:
            conn.execute(
                "UPDATE character_catalog SET mudae_image_thumb = 'portraits/1-abcdef12.webp'"
                " WHERE name_key = ?",
                (catalog_import.name_key("Rem"),),
            )

        assert clean_db.sync_character_thumbs_from_catalog() == 1
        assert clean_db.find_character("Rem")["image_thumb"] == "portraits/1-abcdef12.webp"

    def test_sync_is_idempotent(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )
        clean_db.add_character("Rem", "S", "1", "https://cdn.imgchest.com/files/mine.png")

        # Already wired by add_character, so a sync changes nothing.
        assert clean_db.sync_character_thumbs_from_catalog() == 0

    def test_sync_leaves_rows_the_catalog_has_no_mirror_for(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.add_character("Rem", "S", "1", "https://cdn.imgchest.com/files/mine.png")

        assert clean_db.sync_character_thumbs_from_catalog() == 0
        assert clean_db.find_character("Rem")["image_thumb"] == ""


class TestRefreshCatalogPortrait:
    def _thumb(self, clean_db, key):
        return (
            clean_db.get_connection()
            .execute("SELECT mudae_image_thumb FROM character_catalog WHERE name_key = ?", (key,))
            .fetchone()[0]
        )

    def test_creates_a_row_for_an_unknown_name(self, clean_db):
        result = clean_db.refresh_catalog_portrait(
            "Newchar", "Series", "50", "https://mudae.net/uploads/9/x.png"
        )
        assert result is not None
        catalog_id, key = result
        assert self._thumb(clean_db, key) == ""

    def test_changing_the_url_clears_the_mirror(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        key = catalog_import.name_key("Rem")
        clean_db.record_catalog_portrait_mirrors([(key, "portraits/1-abc.webp")])
        assert self._thumb(clean_db, key) == "portraits/1-abc.webp"

        clean_db.refresh_catalog_portrait("Rem", "S", "1", "https://mudae.net/uploads/1/NEW.png")
        assert self._thumb(clean_db, key) == ""

    def test_the_same_url_keeps_the_existing_mirror(self, clean_db):
        url = "https://mudae.net/uploads/1/a.png"
        _seed_catalog(clean_db, [_catalog_row("Rem", url)])
        key = catalog_import.name_key("Rem")
        clean_db.record_catalog_portrait_mirrors([(key, "portraits/1-abc.webp")])

        clean_db.refresh_catalog_portrait("Rem", "S", "1", url)
        assert self._thumb(clean_db, key) == "portraits/1-abc.webp"

    def test_returns_none_without_a_name_or_url(self, clean_db):
        assert clean_db.refresh_catalog_portrait("", "S", "1", "https://mudae.net/x.png") is None
        assert clean_db.refresh_catalog_portrait("Rem", "S", "1", "") is None


class TestUploadObject:
    def test_reports_failure_without_rclone(self, clean_db, monkeypatch):
        import portrait_mirror
        import r2_storage

        monkeypatch.setattr(r2_storage.shutil, "which", lambda _name: None)
        assert portrait_mirror.upload_object(b"bytes", "portraits/1-x.webp") is False


class TestSuggestionsCarryTheMirror:
    def test_a_mirrored_catalog_row_exposes_image_thumb(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])
        clean_db.record_catalog_portrait_mirrors(
            [(catalog_import.name_key("Rem"), "portraits/1-abcdef12.webp")]
        )

        item = clean_db.suggest_characters("Rem", limit=1)[0]
        assert item["image_thumb"] == "portraits/1-abcdef12.webp"

    def test_an_unmirrored_result_carries_an_empty_thumb(self, clean_db):
        _seed_catalog(clean_db, [_catalog_row("Rem", "https://mudae.net/uploads/1/a.png")])

        item = clean_db.suggest_characters("Rem", limit=1)[0]
        assert item["image_thumb"] == ""


class TestObjectKey:
    def test_is_deterministic_and_url_safe(self):
        key = mirror.object_key(42, b"portrait-bytes")
        assert key.startswith("portraits/42-")
        assert key.endswith(".webp")
        assert key == mirror.object_key(42, b"portrait-bytes")

    def test_changes_when_the_bytes_change(self):
        assert mirror.object_key(42, b"a") != mirror.object_key(42, b"b")


class TestRenderPortrait:
    def _png(self):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (20, 30), (10, 20, 30)).save(buf, "PNG")
        return buf.getvalue()

    def test_encodes_a_webp(self):
        out = mirror.render_portrait(self._png())
        assert out[:4] == b"RIFF"
        assert out[8:12] == b"WEBP"

    def test_undecodable_bytes_return_none(self):
        assert mirror.render_portrait(b"definitely not an image") is None
