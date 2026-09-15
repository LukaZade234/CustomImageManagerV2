"""The accent extractor, against synthetic art and against the real library.

The synthetic tests pin the rules: what gets rejected, what a pale identity
looks like, how the fingerprint keeps a stored seed honest. The calibration
panel pins the answers that matter to people — it reads the working library's
cached thumbnails and portraits, and skips itself anywhere those assets do not
exist (CI, a fresh clone), where the synthetic half still runs.

The panel is the reason this module exists. Every threshold in
accent_extract.py was set by watching these characters move; a threshold
change that nobody re-runs against them is a regression waiting for the next
visit to a character page.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

import accent_extract as ax
import thumbnails

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKING_DB = REPO_ROOT / "data" / "imgmanager.db"


def _png(*colours, size=40):
    """A solid or cycling-colour test image."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    assert px is not None
    for y in range(size):
        for x in range(size):
            px[x, y] = colours[(y * size + x) % len(colours)]
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    return buffer.getvalue()


def _grids(raw):
    img = ax.load_image_bytes(raw)
    assert img is not None
    return ax.measure_image(img)


def _grids_of(raw):
    """Grids for art the test asserts is measurable, not merely parsed."""
    grids = _grids(raw)
    assert grids is not None
    return grids


def _hue(result):
    return result["hue"] % 360


def _hue_gap(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


class TestMeasurement:
    def test_a_flat_colour_survives_as_its_own_hue(self):
        g = _grids(_png((28, 177, 182)))
        assert g is not None
        assert sum(g.saturated.values()) == pytest.approx(1.0)

    def test_greyscale_art_carries_no_signal(self):
        assert _grids(_png((20, 20, 20), (128, 128, 128), (240, 240, 240))) is None

    def test_white_background_and_skin_are_rejected(self):
        g = _grids(_png((255, 255, 255), (252, 219, 189), (248, 210, 180)))
        assert g is None or (not g.saturated and not g.pale)

    def test_pale_tints_land_in_the_pale_class_not_the_saturated_one(self):
        g = _grids(_png((174, 183, 210)))  # a bluey-white
        assert g is not None
        assert not g.saturated
        assert g.pale

    def test_transparency_is_composited_onto_white(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (40, 40), (0, 255, 0, 0)).save(buffer, "PNG")
        img = ax.load_image_bytes(buffer.getvalue())
        assert img is not None
        g = ax.measure_image(img)
        assert g is None or (not g.saturated and not g.pale)


class TestDecision:
    def test_a_confident_pool_seeds_its_hue(self):
        teal = _grids_of(_png((28, 177, 182)))
        result = ax.decide(None, [teal] * 5)
        assert result is not None
        assert _hue_gap(_hue(result), 183) < 25
        assert result["source"] == "gallery"

    def test_an_honest_two_colour_pool_declines(self):
        tie = _grids_of(_png((40, 70, 200), (220, 110, 40)))
        assert ax.decide(None, [tie] * 5) is None

    def test_the_portrait_is_the_fallback_when_the_gallery_declines(self):
        tie = _grids_of(_png((40, 70, 200), (220, 110, 40)))
        teal = _grids_of(_png((28, 177, 182)))
        result = ax.decide(teal, [tie] * 5)
        assert result is not None
        assert result["source"] == "portrait"
        assert _hue_gap(_hue(result), 183) < 25

    def test_nothing_in_nothing_out(self):
        assert ax.decide(None, []) is None

    def test_a_pale_identity_wins_a_weak_saturated_decision(self):
        # Lucy's shape: every image carries the same pale blue tint (her hair)
        # while the saturated content is scattered neon -- enough different
        # hues that no pool bin clears the confidence floor. The seed must
        # come out pale, not loud.
        pale = (174, 183, 210)
        neons = [
            (230, 40, 60),
            (40, 220, 90),
            (250, 200, 40),
            (200, 60, 220),
            (60, 200, 220),
            (220, 120, 40),
        ]
        grids = []
        for offset in range(4):
            colours = [pale, pale, pale] + neons[offset:] + neons[:offset]
            grids.append(_grids_of(_png(*colours)))
        result = ax.decide(None, grids)
        assert result is not None
        assert result["lightness"] > 0.7
        assert result["chroma"] < 0.06

    def test_a_confident_saturated_decision_keeps_its_seed(self):
        # Miku's shape: the saturated teal is unambiguous, and the pale tint
        # beside it must not wash it out.
        teal = (28, 177, 182)
        grids = [_grids_of(_png(teal, teal, teal, (200, 214, 235)))] * 5
        result = ax.decide(None, grids)
        assert result is not None
        assert result["lightness"] < 0.7


class TestFingerprint:
    def test_a_stored_seed_is_not_remeasured_while_inputs_match(self, clean_db, monkeypatch):
        import db

        db.add_character("Rem", "Re:Zero", "S", "")
        calls = []
        monkeypatch.setattr(ax, "extract_seed", lambda *a, **k: calls.append(1) or None)
        ax.ensure_accent("Rem")
        first = len(calls)
        assert first == 1
        ax.ensure_accent("Rem")
        assert len(calls) == first  # fingerprint matched; no re-measure

    def test_adding_an_image_invalidates_the_seed(self, clean_db, monkeypatch):
        import db

        db.add_character("Rem", "Re:Zero", "S", "")
        ax.ensure_accent("Rem")
        calls = []
        monkeypatch.setattr(ax, "extract_seed", lambda *a, **k: calls.append(1) or None)
        db.add_custom_images("Rem", ["https://cdn/img.png"])
        ax.ensure_accent("Rem")
        assert calls == [1]

    def test_a_partial_accent_is_retried_once_thumbnails_land(self, clean_db, tmp_path, monkeypatch):
        import db

        monkeypatch.setenv("THUMB_DIR", str(tmp_path / "thumbs"))
        db.add_character("Rem", "Re:Zero", "S", "")
        db.add_custom_images("Rem", ["https://cdn/img.png"])
        monkeypatch.setattr(ax, "extract_seed", lambda *a, **k: None)
        ax.recompute_accent("Rem")  # no thumbnail on disk -> stored partial
        state = ax.accent_state("Rem")
        assert state is not None and state["accent_partial"] == 1

        thumbnails.store(1, thumbnails.render(_png((28, 177, 182))))
        seen = []
        monkeypatch.setattr(
            ax, "extract_seed", lambda *a, **k: seen.append(a) or {"seed": "#1cb0b6", "hue": 183.0}
        )
        ax.ensure_accent("Rem")
        assert seen  # retried now that the sampled thumbnail exists
        refreshed = ax.accent_state("Rem")
        assert refreshed is not None and refreshed["accent_partial"] == 0


class TestViewerPreference:
    """Turning character accents off must save the server the work, not just
    hide the result: the gallery route is the only thing that ever measures on
    a visitor's behalf, and it must not reach the extractor at all."""

    def test_off_means_the_gallery_route_never_measures(self, client, clean_db, monkeypatch):
        import db

        db.add_character("Rem", "Re:Zero", "S", "")
        db.add_custom_images("Rem", ["https://cdn/img.png"])
        client.patch("/api/me/settings", json={"character_accents": False})

        def refuse(*args, **kwargs):
            raise AssertionError("measured an accent for a viewer who opted out")

        monkeypatch.setattr(ax, "ensure_accent", refuse)
        payload = client.get("/api/custom-image/Rem").get_json()
        assert payload["accentSeed"] is None
        assert payload["rows"]  # the gallery itself still loads

    def test_on_means_the_gallery_route_measures(self, client, clean_db, monkeypatch):
        import db

        db.add_character("Rem", "Re:Zero", "S", "")
        seen = []
        monkeypatch.setattr(ax, "ensure_accent", lambda name: seen.append(name) or "#1cb0b6")
        payload = client.get("/api/custom-image/Rem").get_json()
        assert seen == ["Rem"]
        assert payload["accentSeed"] == "#1cb0b6"


# ---- calibration panel -------------------------------------------------------
# Real characters, real cached art. Character ids are stable primary keys from
# the v1 migration, which is what makes them safe to name here.

PANEL = {
    1001: ("Audrey Hall", lambda r: r is not None and r["source"] == "gallery"),
    445: ("Tsumugi Kotobuki", lambda r: r is not None),
    92: (
        "Lucy (Cyberpunk: Edgerunners)",
        lambda r: r is not None
        and 240 <= _hue(r) <= 290
        and r["lightness"] >= 0.7
        and r["chroma"] <= 0.06,
    ),
    2: ("Hatsune Miku", lambda r: r is not None and 170 <= _hue(r) <= 240),
    592: ("Reimu Hakurei", lambda r: r is not None and _hue_gap(_hue(r), 10) < 40),
    13: ("2B", lambda r: r is None or r["chroma"] < 0.06),
    59: ("Reze", lambda r: r is not None and 270 <= _hue(r) <= 320),
    6: ("Saber", lambda r: r is not None and 240 <= _hue(r) <= 290 and r["lightness"] < 0.6),
    156: ("Madoka Kaname", lambda r: r is not None and _hue_gap(_hue(r), 350) < 30),
}

_has_assets = WORKING_DB.is_file() and (REPO_ROOT / "data" / "thumbs").is_dir()
needs_library = pytest.mark.skipif(
    not _has_assets, reason="working library assets (data/) not present"
)


def _panel_portrait_fetch(character_id, _main_image_url):
    """Portrait bytes without touching the network: the cached sample from the
    old proxy if it survives, otherwise nothing. The committed PNGs the library
    used to name are gone, so a local fallback no longer exists."""
    cached = REPO_ROOT / "data" / "portrait_samples" / f"{character_id}.webp"
    if cached.is_file():
        return cached.read_bytes()
    return None


@needs_library
class TestCalibrationPanel:
    @pytest.mark.parametrize("character_id", sorted(PANEL))
    def test_character(self, character_id, monkeypatch):
        name, expectation = PANEL[character_id]
        conn = sqlite3.connect(f"file:{WORKING_DB}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT main_image_url FROM characters WHERE id = ?", (character_id,)
            ).fetchone()
            assert row is not None, f"{name} is not in the working library"
            main_image_url = row["main_image_url"]
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id, url FROM custom_images WHERE character_id = ?"
                    " AND state = 'active' ORDER BY position, id",
                    (character_id,),
                )
                if thumbnails.is_thumbnailable(r["url"])
            ]
        finally:
            conn.close()

        monkeypatch.setattr(
            ax, "fetch_portrait_bytes", lambda url: _panel_portrait_fetch(character_id, url)
        )
        paths = [p for p in (thumbnails.cache_path(i) for i in ax.evenly_sample(ids, 60)) if p.is_file()]
        result = ax.extract_seed(main_image_url, paths)
        assert expectation(result), f"{name}: {result}"
