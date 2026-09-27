"""The one-off repairs for 2026-09-27: noted names, and GIFs stored as `.png`."""

import pytest

import catalog_import
from scripts import relink_gifs, strip_name_notes


def _catalog(db, *names):
    db.upsert_catalog_characters(
        [{"name": n, "name_key": catalog_import.name_key(n)} for n in names],
        scraped_at="2026-09-01T00:00:00Z",
    )


def _catalog_names(db):
    rows = db.get_connection().execute("SELECT name, name_key FROM character_catalog")
    return {row["name"]: row["name_key"] for row in rows}


class TestStripNameNotes:
    def test_renames_a_noted_name_and_its_key(self, clean_db):
        _catalog(clean_db, "Sora (HCLW) | wish later")
        with clean_db.transaction() as conn:
            strip_name_notes.apply(conn, strip_name_notes.plan(conn))
        assert _catalog_names(clean_db) == {"Sora (HCLW)": "sora (hclw)"}

    def test_deletes_a_noted_duplicate_of_a_clean_row(self, clean_db):
        _catalog(clean_db, "Suzuha Amane", "Suzuha Amane | wish later")
        with clean_db.transaction() as conn:
            steps = strip_name_notes.plan(conn)
            strip_name_notes.apply(conn, steps)
        assert [s[1] for s in steps] == ["delete"]
        assert list(_catalog_names(clean_db)) == ["Suzuha Amane"]

    def test_never_touches_a_real_name_with_a_pipe(self, clean_db):
        _catalog(clean_db, "●●|●●●●●|●●|●")
        with clean_db.transaction() as conn:
            assert strip_name_notes.plan(conn) == []

    def test_a_working_duplicate_is_reported_not_merged(self, clean_db):
        clean_db.add_custom_images("Mi-Ra Yu", ["https://cdn/a.png"])
        clean_db.add_custom_images("Mi-Ra Yu | wish later", ["https://cdn/b.png"])
        with clean_db.transaction() as conn:
            steps = strip_name_notes.plan(conn)
            strip_name_notes.apply(conn, steps)
        assert [(s[0], s[1]) for s in steps] == [("characters", "skip")]
        names = {
            r["name"] for r in clean_db.get_connection().execute("SELECT name FROM characters")
        }
        assert names == {"Mi-Ra Yu", "Mi-Ra Yu | wish later"}


class TestRelinkGifs:
    def _row(self, clean_db, url="https://cdn.imgchest.com/files/old.png"):
        clean_db.add_custom_images("Still in Love", [url])
        with clean_db.transaction() as conn:
            conn.execute("UPDATE custom_images SET thumb_key = 'thumbs/1-abc.webp'")
        [row] = relink_gifs._candidates("2000-01-01")
        return row

    class _Session:
        def get(self, url, timeout):
            class _Response:
                content = b"GIF89a" + b"\0" * 32

                def raise_for_status(self):
                    pass

            return _Response()

    def test_points_the_row_at_the_new_gif_and_drops_the_still_thumbnail(
        self, clean_db, monkeypatch
    ):
        row = self._row(clean_db)
        uploaded, dropped = {}, []

        def fake_upload(path, upload_name):
            uploaded["name"] = upload_name
            return "https://imgchest.com/p/new", "https://cdn.imgchest.com/files/new.gif", "new"

        monkeypatch.setattr(relink_gifs.imgchest_utils, "upload_to_imgchest", fake_upload)
        monkeypatch.setattr(relink_gifs.thumbnails, "delete_mirror", dropped.append)
        url = relink_gifs._relink(self._Session(), row, delete_old=False)

        assert url == "https://cdn.imgchest.com/files/new.gif"
        stored = (
            clean_db.get_connection()
            .execute("SELECT url, thumb_key, imgchest_post_id FROM custom_images")
            .fetchone()
        )
        assert dict(stored) == {"url": url, "thumb_key": None, "imgchest_post_id": "new"}
        assert dropped == ["thumbs/1-abc.webp"]
        assert uploaded["name"].startswith("still-in-love-")

    def test_refuses_a_link_that_did_not_come_back_as_gif(self, clean_db, monkeypatch):
        row = self._row(clean_db)
        monkeypatch.setattr(
            relink_gifs.imgchest_utils,
            "upload_to_imgchest",
            lambda path, upload_name: ("p", "https://cdn.imgchest.com/files/new.png", "new"),
        )
        with pytest.raises(RuntimeError):
            relink_gifs._relink(self._Session(), row, delete_old=False)
        stored = clean_db.get_connection().execute("SELECT url FROM custom_images").fetchone()
        assert stored["url"] == row["url"]
