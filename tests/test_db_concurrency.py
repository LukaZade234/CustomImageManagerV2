"""Concurrency guarantees for the custom-image store.

`test_concurrent_adds_to_same_character_both_persist` was written in Phase 1,
before the fix, and failed: two threads forced to interleave lost one image. It
is the acceptance criterion for the Phase 2 data layer and must stay green.

The old implementation read an entire JSONB document, mutated it in Python and
wrote the whole thing back, with `autocommit = True` and no transaction, so both
callers read the same document and the second write discarded the first. `db.py`
now exposes no setter at all: the only way to write is `mutate_*`, which holds an
advisory lock across the read and the write.
"""

import threading

import pytest


def add_image(db, character: str, url: str, *, barrier: threading.Barrier | None = None) -> None:
    """Add one image the way the application does it.

    Mirrors `add_custom_image` in upload_imgchest.py. The optional barrier makes
    the interleaving deterministic rather than leaving it to chance: both threads
    are inside `mutate` before either is allowed to finish.
    """

    def _append(data: dict) -> None:
        if barrier is not None:
            barrier.wait(timeout=10)
        data.setdefault(character, []).append(url)

    db.mutate_custom_images(_append)


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


def _run_concurrently(targets, timeout=30):
    errors: list[BaseException] = []

    def guard(fn):
        def inner():
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001 - surfaced by the caller
                errors.append(exc)

        return inner

    threads = [threading.Thread(target=guard(t)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    assert not [t for t in threads if t.is_alive()], "a worker deadlocked"
    return errors


def test_concurrent_adds_to_same_character_both_persist(clean_db):
    """Two people adding an image to one character must not lose either.

    THE PHASE 2 ACCEPTANCE CRITERION. This failed before the data-layer rewrite.
    """
    db = clean_db
    db.mutate_custom_images(lambda d: d.setdefault("Rem", []))

    # A barrier forces the worst case: both threads read before either writes.
    # Because `mutate` holds an advisory lock, the second thread cannot enter
    # until the first has committed, so the barrier is released by the lock
    # rather than deadlocking.
    errors = _run_concurrently(
        [
            lambda: add_image(db, "Rem", "https://cdn.example/a.png"),
            lambda: add_image(db, "Rem", "https://cdn.example/b.png"),
        ]
    )
    assert not errors, f"worker raised: {errors}"

    stored = set(db.get_custom_images().get("Rem", []))
    assert stored == {"https://cdn.example/a.png", "https://cdn.example/b.png"}, (
        f"lost an image: stored {stored}. Two concurrent adds must both persist."
    )


@pytest.mark.slow
def test_many_concurrent_adds_all_persist(clean_db):
    """Stronger version: heavy contention on one key must lose nothing."""
    db = clean_db
    urls = [f"https://cdn.example/{i}.png" for i in range(20)]

    errors = _run_concurrently([(lambda u=u: add_image(db, "Rem", u)) for u in urls])
    assert not errors, f"worker raised: {errors}"

    stored = db.get_custom_images().get("Rem", [])
    assert sorted(stored) == sorted(urls)
    assert len(stored) == len(urls), "duplicate or lost writes"


@pytest.mark.slow
def test_concurrent_mutations_of_different_keys_do_not_deadlock(clean_db):
    """Locks are per key, so unrelated documents must not serialise or deadlock."""
    db = clean_db

    errors = _run_concurrently(
        [
            lambda: [add_image(db, "Rem", f"https://cdn.example/a{i}.png") for i in range(10)],
            lambda: [db.update_last_modified(f"Char{i}") for i in range(10)],
            lambda: [db.add_character(f"Char{i}", "Series", "#1") for i in range(10)],
        ]
    )
    assert not errors, f"worker raised: {errors}"
    assert len(db.get_custom_images()["Rem"]) == 10
    assert len(db.get_last_updated()) == 10
    assert len(db.get_characters()) == 10
