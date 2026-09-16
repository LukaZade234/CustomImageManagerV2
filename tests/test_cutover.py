"""The owner-only cut-over preview endpoint.

The app only *reads* the preview the cleanup script wrote; the script is the
thing that deletes. These tests pin the two properties that matter: a plain
moderator cannot see it (it is operator work, not moderation), and a missing
preview is an ordinary "not generated yet" rather than an error, while an
unreadable one is surfaced as a failure rather than shown as empty.
"""

import json

import pytest


def _write_preview(path, **overrides):
    preview = {
        "generated_at": "2026-09-16T00:00:00Z",
        "account": "tester",
        "export": {"unique_urls": 2, "malformed": []},
        "counts": {"keepers": 1, "delete_candidates": 1, "recoverable": 0},
        "delete": [{"file_id": "aaa", "post_id": "p1", "image_count": 1}],
        "recover": [],
        "warnings": [],
    }
    preview.update(overrides)
    path.write_text(json.dumps(preview), encoding="utf-8")
    return preview


class TestCutoverPreviewAccess:
    def test_the_owner_sees_the_preview(self, client, make_moderator, monkeypatch, tmp_path):
        make_moderator("owner")
        _write_preview(tmp_path / "preview.json")
        monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(tmp_path / "preview.json"))
        body = client.get("/api/moderation/cutover").get_json()
        assert body["available"] is True
        assert body["preview"]["counts"]["delete_candidates"] == 1

    def test_a_plain_moderator_is_refused(self, client, make_moderator, monkeypatch, tmp_path):
        """The cut-over is operator work; a moderator has no business seeing it."""
        make_moderator()
        _write_preview(tmp_path / "preview.json")
        monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(tmp_path / "preview.json"))
        assert client.get("/api/moderation/cutover").status_code == 403

    def test_an_anonymous_visitor_is_refused(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(tmp_path / "preview.json"))
        assert client.get("/api/moderation/cutover").status_code == 403


class TestCutoverPreviewStates:
    def test_a_missing_preview_is_not_an_error(self, client, make_moderator, monkeypatch, tmp_path):
        make_moderator("owner")
        monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(tmp_path / "absent.json"))
        body = client.get("/api/moderation/cutover").get_json()
        assert body == {"available": False}

    def test_an_unreadable_preview_is_a_failure_not_an_empty_one(
        self, client, make_moderator, monkeypatch, tmp_path
    ):
        """Showing a corrupt file as "nothing to delete" would be the dangerous answer."""
        make_moderator("owner")
        path = tmp_path / "preview.json"
        path.write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(path))
        response = client.get("/api/moderation/cutover")
        assert response.status_code == 500
        assert "available" not in response.get_json()


@pytest.mark.parametrize("content", ["{ not json", '{"counts": {}}'])
def test_the_endpoint_never_writes(client, make_moderator, monkeypatch, tmp_path, content):
    """A guard on the shape of the thing: this route is a read, always."""
    make_moderator("owner")
    path = tmp_path / "preview.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setenv("IMGCHEST_CLEANUP_PREVIEW", str(path))
    client.get("/api/moderation/cutover")
    assert path.read_text(encoding="utf-8") == content
