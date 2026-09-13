"""Uploading an image Mudae supplied.

Both Mudae paths — adding a character from a card, and refreshing an existing
character's portrait — funnel through one helper that downloads the card image
and pushes it to ImgChest. That helper referenced a `character_name` that was
never a parameter, so every call raised NameError. Nothing exercised it, so the
break shipped: these tests exist so it cannot happen again silently.

The network is not touched. The fetch and the ImgChest call are both replaced,
and what is asserted is the wiring between them.
"""

import pytest
from PIL import Image

import mudae_discord
from imgchest_utils import ImgChestError
from routes import mudae as mudae_routes


def _fake_download(tmp_path):
    """Stands in for the remote fetch, returning a real image on disk."""
    path = tmp_path / "card.png"
    Image.new("RGB", (400, 600), "red").save(path, "PNG")

    def fetch(url):
        return str(path), "card.png"

    return fetch


class TestUploadRemoteImage:
    def test_it_names_the_file_after_the_character(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            mudae_routes, "_fetch_image_from_url_for_import", _fake_download(tmp_path)
        )
        seen = {}

        def fake_upload(path, upload_name=None):
            seen["name"] = upload_name
            return ("post-id", "https://cdn.imgchest.com/files/abc.png")

        monkeypatch.setattr(mudae_routes, "upload_to_imgchest", fake_upload)

        link = mudae_routes._upload_remote_image_to_imgchest(
            "https://cdn.discordapp.com/x.png", "Ayanami Rei"
        )

        assert link == "https://cdn.imgchest.com/files/abc.png"
        assert seen["name"].startswith("ayanami-rei-main-mudae-")
        assert seen["name"].endswith(".png")

    def test_an_empty_url_is_rejected_before_any_fetch(self):
        with pytest.raises(ValueError, match="No image URL"):
            mudae_routes._upload_remote_image_to_imgchest("", "Ayanami Rei")

    def test_the_temp_file_is_removed_even_when_the_upload_fails(self, tmp_path, monkeypatch):
        card = tmp_path / "card.png"
        Image.new("RGB", (400, 600), "red").save(card, "PNG")
        monkeypatch.setattr(
            mudae_routes,
            "_fetch_image_from_url_for_import",
            lambda url: (str(card), "card.png"),
        )
        monkeypatch.setattr(mudae_routes, "upload_to_imgchest", lambda *a, **kw: None)

        with pytest.raises(ImgChestError):
            mudae_routes._upload_remote_image_to_imgchest("https://x/y.png", "Rei")
        assert not card.exists()


class TestPersistMudaeCharacterImage:
    """A card from $im must keep Mudae's host, not be re-hosted needlessly."""

    def test_a_mudae_portrait_is_stored_without_an_upload(self, clean_db, monkeypatch):
        clean_db.add_character("Seed", "S", "1", "")
        uploads = []
        monkeypatch.setattr(
            mudae_routes,
            "_upload_remote_image_to_imgchest",
            lambda url, name: uploads.append(url) or "https://cdn.imgchest.com/x.png",
        )
        info = mudae_discord.CharacterInfo(
            name="Rem",
            series="Re:Zero",
            rank="3",
            image_url="https://mudae.net/uploads/1/x.png",
        )

        action, image_url = mudae_routes._persist_mudae_character(info)

        assert action == "added"
        assert image_url == "https://mudae.net/uploads/1/x.png"
        assert uploads == []
        row = next(c for c in clean_db.get_characters() if c["name"] == "Rem")
        assert row["image"] == "https://mudae.net/uploads/1/x.png"

    def test_a_non_portrait_host_is_re_hosted(self, clean_db, monkeypatch):
        clean_db.add_character("Seed", "S", "1", "")
        monkeypatch.setattr(
            mudae_routes,
            "_upload_remote_image_to_imgchest",
            lambda url, name: "https://cdn.imgchest.com/x.png",
        )
        info = mudae_discord.CharacterInfo(
            name="Rem",
            series="Re:Zero",
            rank="3",
            image_url="https://cdn.discordapp.com/attachments/1/x.png",
        )

        action, image_url = mudae_routes._persist_mudae_character(info)

        assert action == "added"
        assert image_url == "https://cdn.imgchest.com/x.png"
