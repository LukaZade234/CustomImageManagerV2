"""The gender and pool list picked up from a Mudae card.

A card carries both beside the series ("NieR: Automata :male:", "Game &
Animanga"). They are stored on the working row and returned by the character
APIs so the character page can show them.
"""

import mudae_discord
from routes import mudae as mudae_routes


def _info(**overrides):
    fields = {
        "name": "9S",
        "series": "NieR: Automata",
        "rank": "622",
        "image_url": "https://mudae.net/uploads/1/a~b.png",
        "is_male": True,
        "pools": "Game & Animanga",
    }
    fields.update(overrides)
    return mudae_discord.CharacterInfo(**fields)


def _row(clean_db, name):
    return next(c for c in clean_db.get_characters() if c["name"] == name)


class TestStorage:
    def test_add_character_stores_traits(self, clean_db):
        clean_db.add_character(
            "9S", "NieR: Automata", "622", "", is_male=True, pools="Game & Animanga"
        )
        row = _row(clean_db, "9S")
        assert row["is_male"] is True
        assert row["is_female"] is False
        assert row["pools"] == "Game & Animanga"

    def test_traits_default_to_empty(self, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        row = _row(clean_db, "Rem")
        assert row["is_female"] is False
        assert row["is_male"] is False
        assert row["pools"] == ""

    def test_find_character_carries_traits(self, clean_db):
        clean_db.add_character(
            "9S", "NieR: Automata", "622", "", is_male=True, pools="Game & Animanga"
        )
        found = clean_db.find_character("9S")
        assert found["is_male"] is True
        assert found["pools"] == "Game & Animanga"

    def test_set_character_traits_refreshes_but_never_clears(self, clean_db):
        clean_db.add_character(
            "9S", "NieR: Automata", "622", "", is_male=True, pools="Game & Animanga"
        )
        # A later card that came back without a gender is not evidence the
        # character stopped having one, so the stored value stands.
        assert clean_db.set_character_traits("9S", is_female=False, is_male=False, pools="")
        row = _row(clean_db, "9S")
        assert row["is_male"] is True
        assert row["pools"] == "Game & Animanga"

        # A fuller card fills the gap.
        assert clean_db.set_character_traits("9S", is_female=True, is_male=True, pools="Animanga")
        row = _row(clean_db, "9S")
        assert row["is_female"] is True
        assert row["pools"] == "Animanga"

    def test_set_character_traits_unknown_name_is_false(self, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        assert not clean_db.set_character_traits("Nobody", is_female=True, is_male=False, pools="X")

    def test_apply_character_traits_is_a_bulk_no_timestamp_update(self, clean_db):
        clean_db.add_character("9S", "NieR: Automata", "622", "")
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        changed = clean_db.apply_character_traits(
            [
                ("9S", False, True, "Game & Animanga"),
                ("Rem", True, False, "Animanga"),
                ("Nobody", True, False, "X"),
            ]
        )
        assert changed == 2
        row = _row(clean_db, "9S")
        assert row["is_male"] is True
        assert row["pools"] == "Game & Animanga"
        # Enriching from the catalog is not a user edit, so it must not stamp
        # the row into "recently updated".
        stamp = (
            clean_db.get_connection()
            .execute("SELECT updated_at FROM characters WHERE name = '9S'")
            .fetchone()[0]
        )
        assert stamp is None
        # Re-running is a no-op.
        assert clean_db.apply_character_traits([("9S", False, True, "Game & Animanga")]) == 0


class TestLookupRoute:
    def _patch_lookup(self, monkeypatch, info):
        monkeypatch.setattr(
            mudae_routes.mudae_discord,
            "lookup_character",
            lambda name: mudae_discord.LookupResult(type="character", character=info),
        )

    def test_preview_returns_traits_without_saving(self, client, clean_db, monkeypatch):
        clean_db.add_character("Seed", "S", "1", "")
        self._patch_lookup(monkeypatch, _info())
        body = client.post("/api/mudae/lookup-character", json={"name": "9S"}).get_json()
        assert body["character"]["is_male"] is True
        assert body["character"]["pools"] == "Game & Animanga"
        assert all(c["name"] != "9S" for c in clean_db.get_characters())

    def test_adding_from_a_lookup_stores_traits(self, client, clean_db, monkeypatch):
        clean_db.add_character("Seed", "S", "1", "")
        self._patch_lookup(monkeypatch, _info())
        res = client.post("/api/mudae/lookup-character", json={"name": "9S", "add": True})
        assert res.status_code == 200
        assert res.get_json()["success"] is True
        row = _row(clean_db, "9S")
        assert row["is_male"] is True
        assert row["pools"] == "Game & Animanga"
