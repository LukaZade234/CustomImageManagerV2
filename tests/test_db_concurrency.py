"""Concurrency guarantees for the custom-image store.

`test_concurrent_adds_to_same_character_both_persist` is the acceptance
criterion for the Phase 2 data-layer rewrite. It is written before that rewrite
on purpose: it fails against the current implementation, and that failure is the
evidence the data-loss bug is real. When Phase 2 lands it must turn green.

The current implementation reads an entire JSONB document, mutates it in Python
and writes the whole thing back, with `autocommit = True` and no transaction
anywhere. Two concurrent adds therefore both read the old document, and the
second write silently discards the first.
"""

import threading

import pytest


def add_image(db, character: str, url: str, *, barrier: threading.Barrier | None = None) -> None:
    """Add one image the way the application does it.

    Mirrors `add_custom_image` in upload_imgchest.py: read the whole map, append,
    write the whole map back. The optional barrier makes the interleaving
    deterministic instead of relying on chance.
    """
    data = db.get_custom_images()
    if barrier is not None:
        barrier.wait(timeout=10)  # both threads have now read the same state
    data.setdefault(character, []).append(url)
    db.set_custom_images(data)


def test_single_add_persists(clean_db):
    """Baseline: the harness works and a lone write survives."""
    db = clean_db
    add_image(db, "Rem", "https://cdn.example/a.png")
    assert db.get_custom_images()["Rem"] == ["https://cdn.example/a.png"]


def test_adds_to_different_characters_do_not_interfere(clean_db):
    db = clean_db
    add_image(db, "Rem", "https://cdn.example/a.png")
    add_image(db, "Emilia", "https://cdn.example/b.png")
    data = db.get_custom_images()
    assert data["Rem"] == ["https://cdn.example/a.png"]
    assert data["Emilia"] == ["https://cdn.example/b.png"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known data-loss bug: read-modify-write of the whole JSONB document with no "
        "transaction. Fixed by the Phase 2 data layer. strict=True means that once the "
        "fix lands this test XPASSes and FAILS the suite, forcing this marker to be "
        "removed - the bug cannot be quietly fixed and forgotten."
    ),
)
def test_concurrent_adds_to_same_character_both_persist(clean_db):
    """Two people adding an image to one character must not lose either.

    THIS IS THE PHASE 2 ACCEPTANCE CRITERION. It fails today. The fix is a real
    transaction around the read-modify-write (or, after Phase 3, one row per
    image so the two inserts never contend at all).
    """
    db = clean_db
    db.set_custom_images({"Rem": []})

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(url: str) -> None:
        try:
            add_image(db, "Rem", url, barrier=barrier)
        except BaseException as exc:  # noqa: BLE001 - surfaced in the assertion below
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("https://cdn.example/a.png",)),
        threading.Thread(target=worker, args=("https://cdn.example/b.png",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"worker raised: {errors}"

    stored = set(db.get_custom_images().get("Rem", []))
    assert stored == {"https://cdn.example/a.png", "https://cdn.example/b.png"}, (
        f"lost an image: stored {stored}. Two concurrent adds must both persist."
    )
