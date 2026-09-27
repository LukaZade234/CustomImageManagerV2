"""The V43 accent: decision layer, stored model data, queueing and the worker.

The decision layer is pinned two ways. Synthetic images check the rules directly
(a background does not vote, hair counts twice, a colourless character goes
monochrome, a missed cut-out is dropped, a character is never left empty).
`TestMatchesTheLab` checks it against the lab's recorded V43 seeds for characters
the owner reviewed -- byte-identical -- when the lab's data is present (it is
gitignored, so a fresh clone and CI skip that class; `python -m
scripts.accent_lab.portcheck` runs the full 599-character comparison).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import accent_extract as ax
import accent_models
import accent_v43 as V
import thumbnails

RED, BLUE, GREEN = (205, 40, 55), (40, 70, 200), (60, 170, 80)
WHITE = (255, 255, 255)


def _figure(colour, background=WHITE, size=(150, 200), box=(30, 20, 120, 190)):
    """A measurement copy with a character-shaped block, and its mask."""
    w, h = size
    rgb = np.empty((h, w, 3), np.uint8)
    rgb[:] = background
    x0, y0, x1, y1 = box
    rgb[y0:y1, x0:x1] = colour
    mask = np.zeros((h, w), bool)
    mask[y0:y1, x0:x1] = True
    return rgb, mask


def _prepared(colour, background=WHITE, **kw):
    rgb, mask = _figure(colour, background, **kw)
    labels = np.zeros(mask.shape, np.uint8)
    return V.Prepared(rgb=rgb, mask=mask, labels=labels, faces=labels.copy())


def _hue_gap(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


RED_HUE = V.describe("#cd2837")["hue"]
BLUE_HUE = V.describe("#2846c8")["hue"]


class TestDecision:
    def test_a_single_colour_character_takes_its_colour(self):
        r = V.decide(None, [_prepared(RED) for _ in range(5)])
        assert r.path == "standard"
        assert r.seed is not None
        assert _hue_gap(r.seed["hue"], RED_HUE) < 20

    def test_the_background_does_not_vote(self):
        # A red character on a big blue background: the cut-out leaves only red.
        r = V.decide(None, [_prepared(RED, background=BLUE, box=(55, 60, 95, 140))] * 5)
        assert _hue_gap(r.seed["hue"], RED_HUE) < 20

    def test_a_colourless_character_is_monochrome(self):
        grey = [_prepared((235, 235, 235), box=(30, 20, 120, 190)) for _ in range(4)]
        for p in grey:  # dark line work over a white figure
            p.rgb[40:50, 30:120] = (20, 20, 22)
        r = V.decide(None, grey)
        assert r.path == "monochrome"
        assert r.seed is not None and r.seed["chroma"] < 0.05

    def test_a_missed_cutout_drops_the_image(self):
        red = [_prepared(RED) for _ in range(4)]
        missed = []
        for _ in range(4):  # all green, and the model found no character in them
            rgb, _ = _figure(GREEN, background=GREEN)
            missed.append(V.Prepared(rgb=rgb, mask=np.zeros(rgb.shape[:2], bool)))
        r = V.decide(None, red + missed)
        assert _hue_gap(r.seed["hue"], RED_HUE) < 20

    def test_hair_counts_twice(self):
        def half_and_half(hair_labelled):
            rgb, mask = _figure(BLUE)
            rgb[20:95, 30:120] = RED  # the top 40% is red hair
            labels = np.zeros(mask.shape, np.uint8)
            faces = np.zeros(mask.shape, np.uint8)
            if hair_labelled:
                labels[20:95, 30:120] = V.HAIR
                faces[20:95, 30:120] = 1
            return V.Prepared(rgb=rgb, mask=mask, labels=labels, faces=faces, n_faces=1)

        plain = V.decide(None, [half_and_half(False) for _ in range(5)])
        with_hair = V.decide(None, [half_and_half(True) for _ in range(5)])
        assert _hue_gap(plain.seed["hue"], BLUE_HUE) < 25
        assert _hue_gap(with_hair.seed["hue"], RED_HUE) < 25

    def test_never_empty_when_the_main_image_has_a_colour(self):
        r = V.decide(_prepared(RED), [])
        assert r.seed is not None
        assert _hue_gap(r.seed["hue"], RED_HUE) < 25

    def test_nothing_in_nothing_out(self):
        r = V.decide(None, [])
        assert r.seed is None


class TestOwnFaces:
    @staticmethod
    def _face(hair_by_face):
        p = _prepared(RED)
        p.n_faces = len(hair_by_face)
        p.face_hair = {k: np.array(v) for k, v in hair_by_face.items()}
        return p

    def test_the_matching_face_is_the_characters(self):
        blonde, brown = [0.85, 0.0, 0.08], [0.45, 0.04, 0.06]
        images = [
            self._face({1: blonde}),
            self._face({1: blonde}),
            self._face({1: brown, 2: blonde}),
        ]
        owners, package = V.own_faces(images)
        assert not package
        assert owners == {2: {2}}

    def test_a_gallery_of_pairs_is_a_package_deal(self):
        a, b = [0.8, 0.0, 0.1], [0.3, 0.0, -0.1]
        images = [self._face({1: a, 2: b}) for _ in range(6)] + [self._face({1: a})]
        owners, package = V.own_faces(images)
        assert package and owners == {}


class TestImageData:
    def test_the_stored_form_round_trips(self):
        rgb, mask = _figure(RED)
        labels = np.zeros(mask.shape, np.uint8)
        labels[20:60, 40:100] = V.HAIR
        faces = (labels > 0).astype(np.uint8)
        data = accent_models.ImageData(mask, labels, faces, {1: [0.5, 0.1, 0.02]}, 1)
        back = accent_models.ImageData.from_row(
            data.to_blob(), data.hair_json(), data.n_faces, data.version
        )
        assert np.array_equal(back.mask, mask)
        assert np.array_equal(back.labels, labels)
        assert np.array_equal(back.faces, faces)
        assert back.face_hair == {1: [0.5, 0.1, 0.02]}
        assert len(data.to_blob()) < 4000  # a few KB per image, not megabytes

    def test_prepared_refuses_a_mismatched_measurement_copy(self):
        rgb, mask = _figure(RED)
        data = accent_models.ImageData(
            mask, np.zeros_like(mask, np.uint8), np.zeros_like(mask, np.uint8)
        )
        with pytest.raises(ValueError):
            data.prepared(rgb[:100])


def _png_bytes(colour, size=(300, 400), box=(60, 40, 240, 380)):
    img = Image.new("RGB", size, WHITE)
    img.paste(colour, box)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def v43_engine(monkeypatch):
    monkeypatch.setenv("ACCENT_ENGINE", "v43")


class TestEngineSwitch:
    def test_a_stale_seed_is_queued_and_the_stored_one_served(self, clean_db, v43_engine):
        clean_db.add_character("Rem", "Re:Zero", "S", "")
        clean_db.add_custom_images("Rem", ["https://cdn/img.png"])
        assert ax.ensure_accent("Rem") is None  # nothing measured yet
        assert clean_db.accent_queue_size() == 1
        ax.ensure_accent("Rem")
        assert clean_db.accent_queue_size() == 1  # queued once, not twice

    def test_a_fresh_v43_seed_is_served_without_queueing(self, clean_db, v43_engine):
        clean_db.add_character("Rem", "Re:Zero", "S", "")
        ax._store_accent(
            "Rem", {"seed": "#1cb0b6", "hue": 183.0, "source": "gallery"},
            ax.gallery_fingerprint("Rem"), None, partial=False, version=ax.V43,
        )  # fmt: skip
        assert ax.ensure_accent("Rem") == "#1cb0b6"
        assert clean_db.accent_queue_size() == 0

    def test_a_seed_from_the_original_extractor_is_stale(self, clean_db, v43_engine):
        clean_db.add_character("Rem", "Re:Zero", "S", "")
        ax._store_accent(
            "Rem", {"seed": "#1cb0b6", "hue": 183.0, "source": "gallery"},
            ax.gallery_fingerprint("Rem"), None, partial=False, version=None,
        )  # fmt: skip
        assert ax.ensure_accent("Rem") == "#1cb0b6"  # still shown meanwhile
        assert clean_db.accent_queue_size() == 1

    def test_an_override_is_never_queued(self, clean_db, v43_engine):
        clean_db.add_character("Rem", "Re:Zero", "S", "")
        clean_db.set_accent_override("Rem", "#abcdef", None)
        assert ax.ensure_accent("Rem") == "#abcdef"
        assert clean_db.accent_queue_size() == 0

    def test_the_legacy_engine_never_queues(self, clean_db, monkeypatch):
        monkeypatch.delenv("ACCENT_ENGINE", raising=False)
        monkeypatch.setattr(ax, "extract_seed", lambda *a, **k: None)
        clean_db.add_character("Rem", "Re:Zero", "S", "")
        ax.ensure_accent("Rem")
        assert clean_db.accent_queue_size() == 0


class _FakeModels:
    """Stands in for the onnxruntime models: the whole non-white area is the character."""

    def __init__(self):
        self.calls = 0

    def cutout(self, full):
        self.calls += 1
        arr = np.asarray(full.convert("RGB"))
        return np.where((arr != 255).any(axis=2), 255, 0).astype(np.uint8)

    def parse(self, full):
        z = np.zeros(full.size[::-1], np.uint8)
        return z, z.copy()


class TestRecompute:
    def _setup(self, db, tmp_path, monkeypatch, n=3, colour=RED):
        monkeypatch.setenv("THUMB_DIR", str(tmp_path / "thumbs"))
        db.add_character("Rem", "Re:Zero", "S", "")
        db.add_custom_images("Rem", [f"https://cdn/{i}.png" for i in range(n)])
        for image_id in range(1, n + 1):
            thumbnails.store(image_id, thumbnails.render(_png_bytes(colour)))

    def test_measures_stores_and_reuses(self, clean_db, tmp_path, monkeypatch):
        self._setup(clean_db, tmp_path, monkeypatch)
        models = _FakeModels()
        r = ax.recompute_accent_v43("Rem", models)
        assert r is not None and r.seed is not None
        assert _hue_gap(r.seed["hue"], RED_HUE) < 20
        state = ax.accent_state("Rem")
        assert state["accent_version"] == ax.V43
        assert state["accent_seed"] == r.seed["seed"]
        assert state["accent_partial"] == 0
        assert models.calls == 3
        assert len(clean_db.get_accent_image_data([1, 2, 3])) == 3
        ax.recompute_accent_v43("Rem", models)
        assert models.calls == 3  # stored data reused; the models do not run again

    def test_a_missing_thumbnail_marks_the_seed_partial(self, clean_db, tmp_path, monkeypatch):
        self._setup(clean_db, tmp_path, monkeypatch)
        clean_db.add_custom_images("Rem", ["https://cdn/never-rendered.png"])
        monkeypatch.setattr(ax, "_materialise_thumbnail", lambda image_id: None)
        ax.recompute_accent_v43("Rem", _FakeModels())
        assert ax.accent_state("Rem")["accent_partial"] == 1

    def test_an_override_is_left_alone(self, clean_db, tmp_path, monkeypatch):
        self._setup(clean_db, tmp_path, monkeypatch)
        clean_db.set_accent_override("Rem", "#abcdef", None)
        assert ax.recompute_accent_v43("Rem", _FakeModels()) is None
        assert ax.accent_state("Rem")["accent_seed"] == "#abcdef"

    def test_deleting_an_image_deletes_its_data(self, clean_db, tmp_path, monkeypatch):
        self._setup(clean_db, tmp_path, monkeypatch)
        ax.recompute_accent_v43("Rem", _FakeModels())
        with clean_db.transaction() as conn:
            conn.execute("DELETE FROM custom_images WHERE id = 1")
        assert set(clean_db.get_accent_image_data([1, 2, 3])) == {2, 3}


class TestWorker:
    def test_a_job_is_done_and_removed(self, clean_db, monkeypatch):
        import accent_worker

        clean_db.add_character("Rem", "Re:Zero", "S", "")
        clean_db.enqueue_accent("Rem")
        seen = []
        monkeypatch.setattr(ax, "recompute_accent_v43", lambda name, models: seen.append(name))
        assert accent_worker.run_once(object()) is True
        assert seen == ["Rem"]
        assert clean_db.accent_queue_size() == 0
        assert accent_worker.run_once(object()) is False

    def test_a_failure_is_retried_later(self, clean_db, monkeypatch):
        import accent_worker

        clean_db.add_character("Rem", "Re:Zero", "S", "")
        clean_db.enqueue_accent("Rem")

        def boom(name, models):
            raise RuntimeError("thumbnail fetch failed")

        monkeypatch.setattr(ax, "recompute_accent_v43", boom)
        assert accent_worker.run_once(object()) is True
        assert clean_db.accent_queue_size() == 1
        assert clean_db.next_accent_job() is None  # not due again yet
        row = (
            clean_db.get_connection()
            .execute("SELECT attempts, last_error FROM accent_queue")
            .fetchone()
        )
        assert row["attempts"] == 1 and "thumbnail fetch failed" in row["last_error"]


LAB = Path(__file__).resolve().parent.parent / "scripts" / "accent_lab" / ".data"
# Characters the owner reviewed, one per behaviour: standard, ties broken by the main
# image, hair counted twice, own hair in pair images, a package deal, monochrome with
# a highlight, monochrome white, the recurring tint, the pale-pink path, greens.
REVIEWED = [
    "Lynae", "Reze", "Kyouka Jirou", "Anya Forger", "Himiko Toga", "Popola",
    "Ken Kaneki", "Kaine", "Gon Freecss", "Mitsuri Kanroji", "Panty Anarchy", "Roronoa Zoro",
]  # fmt: skip


@pytest.mark.skipif(not (LAB / "full_v43").is_dir(), reason="the accent lab's data is not present")
class TestMatchesTheLab:
    @pytest.mark.parametrize("name", REVIEWED)
    def test_seed_is_byte_identical(self, name):
        from scripts.accent_lab import lab, portcheck

        ref = LAB / "full_v43" / f"{lab.slug(name)}.json"
        if not ref.is_file():
            pytest.skip(f"{name} was not in the lab's full run")
        _, want, got, why = portcheck._one(name)
        assert got == json.loads(ref.read_text())["seed"] == want, why


class TestBackfillImport:
    """scripts/accent_backfill.py import: a seed only where nothing changed since the
    snapshot; everything else queued; hand-picked colours untouched; dry run by default."""

    @staticmethod
    def _bundle(tmp_path, seeds, image_rows=()):
        import sqlite3

        from scripts import accent_backfill as bf

        path = tmp_path / "bundle.db"
        conn = sqlite3.connect(path)
        conn.executescript(bf.BUNDLE_SCHEMA)
        conn.execute("INSERT INTO meta VALUES ('data_version', ?)", (accent_models.DATA_VERSION,))
        conn.executemany("INSERT INTO image_data VALUES (?, ?, ?, ?, ?)", image_rows)
        for name, seed, ids, main in seeds:
            conn.execute(
                "INSERT INTO seeds VALUES (?, ?, ?, 'gallery', 'standard', '', ?, ?, 0, '')",
                (name, seed, 183.0 if seed else None, json.dumps(ids), main),
            )
        conn.commit()
        conn.close()
        return path

    def test_dry_run_writes_nothing(self, clean_db, tmp_path):
        from scripts import accent_backfill as bf

        clean_db.add_character("Rem", "Re:Zero", "S", "")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])
        bundle = self._bundle(tmp_path, [("Rem", "#1cb0b6", [1], None)])
        bf.import_bundle(bundle, apply=False, queue_rest=True)
        assert ax.accent_state("Rem")["accent_seed"] is None
        assert clean_db.accent_queue_size() == 0

    def test_unchanged_gets_the_seed_changed_is_queued_override_kept(self, clean_db, tmp_path):
        from scripts import accent_backfill as bf

        for name in ("Rem", "Ram", "Emilia", "Subaru"):
            clean_db.add_character(name, "Re:Zero", "S", "")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"])  # id 1
        clean_db.add_custom_images("Ram", ["https://cdn/b.png"])  # id 2
        clean_db.add_custom_images("Emilia", ["https://cdn/c.png"])  # id 3
        clean_db.set_accent_override("Emilia", "#abcdef", None)
        rgb, mask = _figure(RED)
        data = accent_models.ImageData(
            mask, np.zeros_like(mask, np.uint8), np.zeros_like(mask, np.uint8)
        )
        rows = [
            (1, data.version, data.to_blob(), data.hair_json(), 0),
            (99, data.version, b"", "{}", 0),
        ]
        bundle = self._bundle(
            tmp_path,
            [
                ("Rem", "#1cb0b6", [1], None),  # unchanged
                ("Ram", "#d23c46", [], None),  # an image was added since the snapshot
                ("Emilia", "#78c850", [3], None),  # hand-picked: kept
            ],
            rows,
        )
        bf.import_bundle(bundle, apply=True, queue_rest=True)
        rem = ax.accent_state("Rem")
        assert rem["accent_seed"] == "#1cb0b6" and rem["accent_version"] == ax.V43
        assert ax.accent_state("Ram")["accent_seed"] is None
        assert ax.accent_state("Emilia")["accent_seed"] == "#abcdef"
        queued = {r[0] for r in clean_db.get_connection().execute(
            "SELECT c.name FROM accent_queue q JOIN characters c ON c.id = q.character_id")}  # fmt: skip
        assert queued == {"Ram", "Subaru"}  # Subaru: not in the bundle, queued by --queue-rest
        assert set(clean_db.get_accent_image_data([1, 99])) == {1}  # a deleted image is skipped
