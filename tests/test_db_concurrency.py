"""Concurrency guarantees for the custom-image store.

`test_concurrent_adds_to_same_character_both_persist` was written in Phase 1,
before any fix, and failed: two threads forced to interleave lost one image.

It has survived two rewrites of the storage underneath it, which is the point of
writing the assertion rather than the implementation:

* Phase 2 kept the JSON document but made read-modify-write atomic under an
  advisory lock.
* Phase 3 made images rows. Two people adding to one character now perform two
  INSERTs and do not contend at all -- the lock is gone because there is nothing
  left to serialise.
"""

import threading

import pytest


def add_image(db, character: str, url: str) -> None:
    """Add one image the way the application does it."""
    db.add_custom_images(character, [url])


def test_single_add_persists(clean_db):
    db = clean_db
    add_image(db, "Rem", "https://cdn.example/a.png")
    assert db.get_custom_images_for("Rem") == ["https://cdn.example/a.png"]


def test_adds_to_different_characters_do_not_interfere(clean_db):
    db = clean_db
    add_image(db, "Rem", "https://cdn.example/a.png")
    add_image(db, "Emilia", "https://cdn.example/b.png")
    assert db.get_custom_images_for("Rem") == ["https://cdn.example/a.png"]
    assert db.get_custom_images_for("Emilia") == ["https://cdn.example/b.png"]


def test_duplicate_url_is_rejected_by_the_schema(clean_db):
    """UNIQUE (character_id, url) makes de-duplication a property of the schema."""
    db = clean_db
    assert db.add_custom_images("Rem", ["https://cdn.example/a.png"]) == 1
    assert db.add_custom_images("Rem", ["https://cdn.example/a.png"]) == 0
    assert db.get_custom_images_for("Rem") == ["https://cdn.example/a.png"]


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

    The original acceptance criterion. Failed in Phase 1, green since Phase 2,
    and must stay green through every future change to the storage layer.
    """
    db = clean_db
    db.add_custom_images("Rem", [])

    errors = _run_concurrently(
        [
            lambda: add_image(db, "Rem", "https://cdn.example/a.png"),
            lambda: add_image(db, "Rem", "https://cdn.example/b.png"),
        ]
    )
    assert not errors, f"worker raised: {errors}"

    stored = set(db.get_custom_images_for("Rem"))
    assert stored == {"https://cdn.example/a.png", "https://cdn.example/b.png"}, (
        f"lost an image: stored {stored}. Two concurrent adds must both persist."
    )


@pytest.mark.slow
def test_many_concurrent_adds_all_persist(clean_db):
    db = clean_db
    urls = [f"https://cdn.example/{i}.png" for i in range(20)]

    errors = _run_concurrently([(lambda u=u: add_image(db, "Rem", u)) for u in urls])
    assert not errors, f"worker raised: {errors}"

    stored = db.get_custom_images_for("Rem")
    assert sorted(stored) == sorted(urls)
    assert len(stored) == len(urls), "duplicate or lost writes"


@pytest.mark.slow
def test_concurrent_writes_across_tables_do_not_deadlock(clean_db):
    db = clean_db

    errors = _run_concurrently(
        [
            lambda: [add_image(db, "Rem", f"https://cdn.example/a{i}.png") for i in range(10)],
            lambda: [db.update_last_modified(f"Char{i}") for i in range(10)],
            lambda: [db.add_character(f"Other{i}", "Series", "#1") for i in range(10)],
        ]
    )
    assert not errors, f"worker raised: {errors}"
    assert len(db.get_custom_images_for("Rem")) == 10
    assert len(db.get_last_updated()) >= 10
