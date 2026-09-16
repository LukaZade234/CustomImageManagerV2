"""Adding the same file twice.

The rule: the fingerprint is the file's bytes, checked **before** the ImgChest
upload. A match on the same character is skipped and reported so the client can
show the two side by side; the caller can override with `allow_duplicates`. A
match on another character is only a note, because the same art on a second
character is usually deliberate.

Post-upload detection would be worse than useless: ImgChest cannot delete the
only image in a post, so a duplicate that reached it would be permanently
orphaned. Every upload in this file goes through a faked ImgChest, and the
assertion that matters most is that the *second* upload never calls it.
"""

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

import tempfiles


def _png_bytes(color="red", size=(48, 48)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _buf(payload):
    return BytesIO(payload)


def _fake_imgchest(monkeypatch):
    """A counting stand-in for the upload.

    Records each (name, sha256) so a test can prove the row's fingerprint is of
    the bytes actually stored on ImgChest, not the raw upload.
    """
    calls = []

    def upload(path, upload_name=None):
        calls.append((upload_name, hashlib.sha256(Path(path).read_bytes()).hexdigest()))
        n = len(calls)
        return ("post", f"https://cdn.imgchest.com/files/{n}.png", f"post-{n}")

    monkeypatch.setattr("routes.customs.upload_to_imgchest", upload)
    return calls


def _add(client, char, payload, *, filename="picture.png", allow=False):
    data = {"character_name": char, "files": (_buf(payload), filename)}
    if allow:
        data["allow_duplicates"] = "1"
    return client.post("/api/custom-image", data=data, content_type="multipart/form-data")


class TestAddingTheSameFile:
    def test_the_second_copy_is_skipped_and_reported(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        make_signed_in()
        calls = _fake_imgchest(monkeypatch)
        payload = _png_bytes()

        first = _add(client, "Rem", payload)
        assert first.status_code == 200
        assert len(first.get_json()["links"]) == 1

        second = _add(client, "Rem", payload)
        body = second.get_json()
        assert second.status_code == 200
        assert body["links"] == [], "the duplicate was not uploaded"
        assert len(body["duplicates"]) == 1
        assert body["duplicates"][0]["existing"]["url"] == first.get_json()["links"][0]
        assert calls and len(calls) == 1, "ImgChest was called for the duplicate"

    def test_the_fingerprint_is_of_the_stored_file(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        """Not of the raw upload: the backfill can only ever see the stored
        file, so hashing anything else would be unmatchable."""
        make_signed_in()
        calls = _fake_imgchest(monkeypatch)
        payload = _png_bytes()

        _add(client, "Rem", payload)
        row = (
            clean_db.get_connection()
            .execute("SELECT content_hash FROM custom_images LIMIT 1")
            .fetchone()
        )
        assert row["content_hash"] == calls[0][1]
        assert row["content_hash"] != hashlib.sha256(payload).hexdigest()

    def test_the_override_uploads_it_anyway(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        calls = _fake_imgchest(monkeypatch)
        payload = _png_bytes()

        _add(client, "Rem", payload)
        again = _add(client, "Rem", payload, allow=True)
        body = again.get_json()
        assert len(body["links"]) == 1
        assert body["duplicates"] == []
        assert len(calls) == 2

    def test_a_different_file_is_not_a_duplicate(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        make_signed_in()
        _fake_imgchest(monkeypatch)

        _add(client, "Rem", _png_bytes("red"))
        other = _add(client, "Rem", _png_bytes("blue"))
        body = other.get_json()
        assert len(body["links"]) == 1
        assert body["duplicates"] == []

    def test_a_batch_reports_only_the_duplicate(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        """One file already here, one new: add the new one, skip the other."""
        make_signed_in()
        _fake_imgchest(monkeypatch)
        known = _png_bytes("red")
        _add(client, "Rem", known)

        fresh = _png_bytes("blue")
        response = client.post(
            "/api/custom-image",
            data={
                "character_name": "Rem",
                "files": [(_buf(known), "known.png"), (_buf(fresh), "fresh.png")],
            },
            content_type="multipart/form-data",
        )
        body = response.get_json()
        assert len(body["links"]) == 1
        assert len(body["duplicates"]) == 1
        assert body["duplicates"][0]["filename"] == "known.png"

    def test_all_duplicates_is_a_success_not_a_500(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()
        _add(client, "Rem", payload)

        response = _add(client, "Rem", payload)
        assert response.status_code == 200
        assert "already in this gallery" in response.get_json()["message"]


class TestCharacterScope:
    def test_the_same_picture_on_another_character_is_allowed_but_noted(
        self, client, clean_db, make_signed_in, monkeypatch
    ):
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()

        _add(client, "Rem", payload)
        elsewhere = _add(client, "Emilia", payload)
        body = elsewhere.get_json()
        assert len(body["links"]) == 1, "a match on another character does not block"
        assert body["duplicates"] == []
        assert [m["character"] for m in body["also_on"]] == ["Rem"]


class TestState:
    def test_a_removed_copy_is_reported_as_removed(
        self, client, clean_db, make_signed_in, identity_id, monkeypatch
    ):
        """It still exists and can be restored, so say so rather than block blindly."""
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()
        url = _add(client, "Rem", payload).get_json()["links"][0]
        clean_db.remove_custom_images("Rem", [url], identity_id)

        body = _add(client, "Rem", payload).get_json()
        assert body["links"] == []
        assert body["duplicates"][0]["existing"]["state"] == "removed"

    def test_a_purged_copy_does_not_block(self, client, clean_db, make_signed_in, monkeypatch):
        """The source is gone from ImgChest; blocking would make the picture
        impossible to re-add."""
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()
        _add(client, "Rem", payload)
        with clean_db.transaction() as conn:
            conn.execute("UPDATE custom_images SET purged_at = '2026-01-01T00:00:00Z'")

        body = _add(client, "Rem", payload).get_json()
        assert len(body["links"]) == 1
        assert body["duplicates"] == []


class TestImportFromUrl:
    def _fake_fetch(self, monkeypatch, payload):
        def fetch(url):
            path = tempfiles.reserve("custom", "web.png")
            Path(path).write_bytes(payload)
            return path, "web.png"

        monkeypatch.setattr("routes.customs._fetch_image_from_url_for_import", fetch)

    def _import(self, client, char, allow=False):
        body = {"character_name": char, "urls": ["https://example.test/a.png"]}
        if allow:
            body["allow_duplicates"] = True
        return client.post("/api/import-custom-images-from-urls", json=body)

    def test_the_same_fetched_file_is_skipped(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()
        self._fake_fetch(monkeypatch, payload)

        first = self._import(client, "Rem")
        assert len(first.get_json()["links"]) == 1

        second = self._import(client, "Rem")
        body = second.get_json()
        assert body["links"] == []
        assert len(body["duplicates"]) == 1
        assert body["duplicates"][0]["url"] == "https://example.test/a.png"

    def test_the_override_imports_it_anyway(self, client, clean_db, make_signed_in, monkeypatch):
        make_signed_in()
        _fake_imgchest(monkeypatch)
        payload = _png_bytes()
        self._fake_fetch(monkeypatch, payload)

        self._import(client, "Rem")
        again = self._import(client, "Rem", allow=True)
        assert len(again.get_json()["links"]) == 1


class TestBackfillHelpers:
    def test_missing_then_set_round_trips(self, clean_db):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])
        clean_db.add_custom_images("Emilia", ["https://cdn/b.png"])

        missing = clean_db.images_missing_content_hash()
        assert len(missing) == 2
        assert clean_db.set_content_hash(missing[0]["id"], "deadbeef")

        still = {row["id"] for row in clean_db.images_missing_content_hash()}
        assert missing[0]["id"] not in still
        assert missing[1]["id"] in still

    def test_rows_are_walked_by_id(self, clean_db):
        clean_db.add_custom_images("Rem", [f"https://cdn/{i}.png" for i in range(5)])
        first = clean_db.images_missing_content_hash(limit=2)
        assert len(first) == 2
        second = clean_db.images_missing_content_hash(limit=2, after_id=first[-1]["id"])
        assert second[0]["id"] > first[-1]["id"]

    def test_purged_rows_are_not_worth_downloading(self, clean_db):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])
        with clean_db.transaction() as conn:
            conn.execute("UPDATE custom_images SET purged_at = '2026-01-01T00:00:00Z'")
        assert clean_db.images_missing_content_hash() == []

    def test_set_content_hash_on_a_missing_row_is_false(self, clean_db):
        assert clean_db.set_content_hash(99999, "x") is False


class TestDuplicateClusters:
    def _seed(self, clean_db):
        clean_db.add_custom_images(
            "Rem", ["https://cdn/a.png"], content_hashes={"https://cdn/a.png": "same"}
        )
        clean_db.add_custom_images(
            "Emilia", ["https://cdn/b.png"], content_hashes={"https://cdn/b.png": "same"}
        )

    def test_a_shared_fingerprint_is_one_cluster(self, clean_db):
        self._seed(clean_db)
        clusters = clean_db.list_duplicate_clusters()
        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["hash"] == "same"
        assert cluster["count"] == 2
        assert sorted(image["character"] for image in cluster["images"]) == ["Emilia", "Rem"]

    def test_unique_fingerprints_do_not_cluster(self, clean_db):
        clean_db.add_custom_images(
            "Rem", ["https://cdn/a.png"], content_hashes={"https://cdn/a.png": "one"}
        )
        clean_db.add_custom_images(
            "Rem", ["https://cdn/b.png"], content_hashes={"https://cdn/b.png": "two"}
        )
        assert clean_db.list_duplicate_clusters() == []

    def test_a_purged_copy_leaves_the_cluster(self, clean_db):
        self._seed(clean_db)
        with clean_db.transaction() as conn:
            conn.execute(
                "UPDATE custom_images SET purged_at = '2026-01-01T00:00:00Z'"
                " WHERE url = 'https://cdn/b.png'"
            )
        assert clean_db.list_duplicate_clusters() == []

    def test_rows_without_a_fingerprint_are_ignored(self, clean_db):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png", "https://cdn/b.png"])
        assert clean_db.list_duplicate_clusters() == []


class TestDuplicatesApi:
    def test_moderators_only(self, client, clean_db, make_moderator):
        assert client.get("/api/moderation/duplicates").status_code == 403

        make_moderator()
        response = client.get("/api/moderation/duplicates")
        assert response.status_code == 200
        assert response.get_json() == {"clusters": [], "total": 0}

    def test_it_returns_the_clusters(self, client, clean_db, make_moderator):
        clean_db.add_custom_images(
            "Rem", ["https://cdn/a.png"], content_hashes={"https://cdn/a.png": "same"}
        )
        clean_db.add_custom_images(
            "Emilia", ["https://cdn/b.png"], content_hashes={"https://cdn/b.png": "same"}
        )
        make_moderator()

        body = client.get("/api/moderation/duplicates").get_json()
        assert body["total"] == 2
        assert body["clusters"][0]["count"] == 2


class TestBackfillScript:
    """The script's own paths, with the network replaced by a local write."""

    def _run(self, monkeypatch, argv=("backfill",)):
        import sys

        import scripts.backfill_content_hashes as script

        monkeypatch.setattr(sys, "argv", list(argv))
        return script

    def test_it_fingerprints_each_missing_row(self, clean_db, monkeypatch):
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])

        script = self._run(monkeypatch)

        def fetch(url):
            path = tempfiles.reserve("import", "stored.bin")
            Path(path).write_bytes(b"a stored file")
            return path, "stored.bin"

        monkeypatch.setattr(script, "_fetch_image_from_url_for_import", fetch)

        assert script.main() == 0
        row = clean_db.get_connection().execute("SELECT content_hash FROM custom_images").fetchone()
        assert row["content_hash"] == hashlib.sha256(b"a stored file").hexdigest()

    def test_a_dead_link_leaves_the_row_null_and_the_run_succeeds(self, clean_db, monkeypatch):
        clean_db.add_custom_images("Rem", ["https://cdn/dead.png"])
        script = self._run(monkeypatch)

        def fetch(url):
            raise ValueError("Image server returned HTTP 404")

        monkeypatch.setattr(script, "_fetch_image_from_url_for_import", fetch)

        assert script.main() == 0
        row = clean_db.get_connection().execute("SELECT content_hash FROM custom_images").fetchone()
        assert row["content_hash"] is None
