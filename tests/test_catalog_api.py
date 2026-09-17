"""Catalog suggestions, name lookup and the catalog add endpoint.

These back the Add flow: the comboboxes read the catalog, a typed name resolves
to its series, and adding a known character needs no Discord or ImgChest call.
"""

import catalog_import


def _catalog_row(name, series, rank, image=None, **facets):
    row = {
        "name": name,
        "name_key": catalog_import.name_key(name),
        "series": series,
        "rank": rank,
        "mudae_image_url": image or f"https://mudae.net/uploads/{rank}/a~b.png",
        "pool": "wa",
        "is_waifu": True,
        "is_anime": True,
    }
    row.update(facets)
    return row


def seed_catalog(clean_db, rows):
    clean_db.upsert_catalog_characters(rows, scraped_at="2026-01-01T00:00:00Z", source_batch="test")


class TestSuggestCharacters:
    def test_empty_query_returns_best_rank_first(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("High Rank", "S", "9000"),
                _catalog_row("Top Rank", "S", "4"),
                _catalog_row("Mid Rank", "S", "300"),
            ],
        )
        names = [i["name"] for i in clean_db.suggest_characters("", limit=10)]
        assert names == ["Top Rank", "Mid Rank", "High Rank"]

    def test_prefix_matches_come_before_substring_matches(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Xen Saber", "S", "1"),
                _catalog_row("Saber Alter", "S", "2"),
            ],
        )
        names = [i["name"] for i in clean_db.suggest_characters("Saber")]
        assert names[0] == "Saber Alter"

    def test_working_row_wins_and_borrows_the_catalog_image(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Saber", "Fate/stay night", "4")])
        clean_db.add_character("Saber", "Hand Edited", "999", "")
        item = clean_db.suggest_characters("Saber", limit=5)[0]
        assert item["series"] == "Hand Edited"
        assert item["rank"] == "999"
        assert item["image"].startswith("https://mudae.net/")
        assert item["in_library"] is True

    def test_nothing_matches_returns_empty(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        assert clean_db.suggest_characters("zzzz") == []

    def test_series_filter_returns_only_that_series(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Rem", "Re:Zero", "3"),
                _catalog_row("Emilia", "Re:Zero", "2"),
                _catalog_row("Saber", "Fate/stay night", "4"),
            ],
        )
        names = [i["name"] for i in clean_db.suggest_characters("", series="Re:Zero")]
        assert names == ["Emilia", "Rem"]
        assert clean_db.suggest_characters("", series="Nope") == []

    def test_items_carry_their_pool_facets(self, clean_db):
        # So the Add form can select the character's pools the moment it is
        # picked, without a second request.
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        item = clean_db.suggest_characters("Rem", limit=1)[0]
        assert item["facets"] == ["waifu", "anime"]

    def test_a_working_row_carries_its_catalog_facets(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        item = clean_db.suggest_characters("Rem", limit=1)[0]
        assert item["in_library"] is True
        assert item["facets"] == ["waifu", "anime"]


class TestPoolFilters:
    def test_keeps_only_catalog_rows_with_the_named_facet(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Waifu", "S", "1"),
                _catalog_row(
                    "Husbando", "S", "2", is_waifu=False, is_anime=False, is_husbando=True
                ),
            ],
        )
        names = [i["name"] for i in clean_db.suggest_characters("", pools=["husbando"])]
        assert names == ["Husbando"]

    def test_every_named_facet_must_hold(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Waifu Anime", "S", "1"),
                _catalog_row("Waifu Game", "S", "2", is_anime=False, is_game=True),
            ],
        )
        names = [i["name"] for i in clean_db.suggest_characters("", pools=["waifu", "game"])]
        assert names == ["Waifu Game"]

    def test_working_rows_without_a_catalog_match_are_excluded(self, clean_db):
        clean_db.add_character("Homegrown", "S", "1", "")
        seed_catalog(clean_db, [_catalog_row("Rem", "S", "2")])
        unfiltered = {i["name"] for i in clean_db.suggest_characters("")}
        assert unfiltered == {"Homegrown", "Rem"}
        assert [i["name"] for i in clean_db.suggest_characters("", pools=["waifu"])] == ["Rem"]

    def test_a_working_row_survives_when_its_catalog_match_filters(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        clean_db.add_character("Rem", "Hand Edited", "999", "")
        items = clean_db.suggest_characters("Rem", pools=["waifu"])
        assert [i["name"] for i in items] == ["Rem"]
        assert items[0]["in_library"] is True

    def test_an_unknown_facet_is_ignored(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "S", "3")])
        assert [i["name"] for i in clean_db.suggest_characters("", pools=["nonsense"])] == ["Rem"]


class TestSuggestSeries:
    def test_unions_catalog_and_working_series(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        clean_db.add_character("Custom", "My Series", "1", "")
        series = clean_db.suggest_series("")
        assert "Re:Zero" in series
        assert "My Series" in series

    def test_filters_by_term_case_insensitively(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Rem", "Re:Zero", "3")])
        assert clean_db.suggest_series("zero") == ["Re:Zero"]
        assert clean_db.suggest_series("nope") == []

    def test_series_differing_only_in_case_collapse_to_the_catalog_spelling(self, clean_db):
        clean_db.upsert_catalog_series(
            [{"series": "Zenless Zone Zero", "listed": 1, "total": 1}], scraped_at="x"
        )
        seed_catalog(clean_db, [_catalog_row("A", "zenless zone zero", "1")])
        assert clean_db.suggest_series("zenless") == ["Zenless Zone Zero"]


class TestFindCharacter:
    def test_prefers_the_working_row(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Saber", "Fate/stay night", "4")])
        clean_db.add_character("Saber", "Edited", "1", "local.png")
        found = clean_db.find_character("Saber")
        assert found["series"] == "Edited"
        assert found["in_library"] is True

    def test_falls_back_to_the_catalog(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Artoria Pendragon", "Fate/stay night", "4")])
        found = clean_db.find_character("Artoria Pendragon")
        assert found["in_library"] is False
        assert found["image"].startswith("https://mudae.net/")

    def test_matches_accented_spellings_by_key(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Hange Zoe\u0308", "AOT", "42")])
        assert clean_db.find_character("Hange Zoë")["series"] == "AOT"

    def test_a_working_row_is_matched_by_its_stored_key(self, clean_db):
        # NFD stored, NFC looked up. The stored name_key is what makes this one
        # indexed lookup rather than a scan folding every row in Python.
        clean_db.add_character("Hange Zoe\u0308", "AOT", "42", "")
        found = clean_db.find_character("Hange Zoë")
        assert found["in_library"] is True
        assert found["name"] == "Hange Zoe\u0308"

    def test_carries_the_active_custom_count(self, clean_db):
        # The link-preview edge function reads this to say "N custom images".
        # Only active images count: a removed one is not on the page.
        clean_db.add_character("Saber", "Fate", "1", "")
        clean_db.add_custom_images(
            "Saber",
            ["https://cdn/a.png", "https://cdn/b.png", "https://cdn/c.png"],
            added_by="someone",
        )
        assert clean_db.find_character("Saber")["custom_count"] == 3
        clean_db.remove_custom_images("Saber", ["https://cdn/b.png"], "someone")
        assert clean_db.find_character("Saber")["custom_count"] == 2

    def test_a_catalog_only_character_counts_zero(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Artoria Pendragon", "Fate", "4")])
        found = clean_db.find_character("Artoria Pendragon")
        assert found["in_library"] is False
        assert found["custom_count"] == 0

    def test_a_lazily_created_row_is_findable(self, clean_db):
        # Custom images can attach to a name with no character row; that insert
        # has to write the key too.
        clean_db.add_custom_images("Lazy One", ["https://cdn/x.png"])
        assert clean_db.find_character("lazy one")["in_library"] is True

    def test_rename_updates_the_key(self, clean_db):
        clean_db.add_character("Old Name", "S", "1", "")
        assert clean_db.update_character("Old Name", "New Name", "S", "1") is True
        assert clean_db.find_character("old name") is None
        assert clean_db.find_character("new name")["in_library"] is True

    def test_backfill_fills_rows_that_predate_the_column(self, clean_db):
        conn = clean_db.get_connection()
        conn.execute("INSERT INTO characters (name, name_key) VALUES ('Late Addition', '')")
        conn.commit()
        clean_db._backfill_character_name_keys(conn)
        assert clean_db.find_character("late addition")["in_library"] is True

    def test_stored_key_is_the_folded_name(self, clean_db):
        clean_db.add_character("Hange Zoë", "AOT", "42", "")
        row = (
            clean_db.get_connection()
            .execute("SELECT name_key FROM characters WHERE name = 'Hange Zoë'")
            .fetchone()
        )
        assert row["name_key"] == catalog_import.name_key("Hange Zoë")

    def test_found_character_carries_facets(self, clean_db):
        seed_catalog(clean_db, [_catalog_row("Artoria Pendragon", "Fate/stay night", "4")])
        found = clean_db.find_character("Artoria Pendragon")
        assert found["facets"] == ["waifu", "anime"]

    def test_unknown_is_none(self, clean_db):
        assert clean_db.find_character("Nobody Here") is None


class TestSearch:
    def _seed(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Rem", "Re:Zero", "3"),
                _catalog_row("Emilia", "Re:Zero", "2"),
                _catalog_row("Saber", "Fate/stay night", "4"),
            ],
        )

    def test_blank_query_returns_nothing(self, clean_db):
        self._seed(clean_db)
        assert clean_db.search_catalog("") == {"items": [], "total": 0}

    def test_rank_sort_is_best_first_and_paginates(self, clean_db):
        self._seed(clean_db)
        result = clean_db.search_catalog("e", sort="rank", order="asc", per_page=2)
        assert result["total"] == 3
        assert [i["name"] for i in result["items"]] == ["Emilia", "Rem"]  # rank 2, 3
        page2 = clean_db.search_catalog("e", sort="rank", order="asc", page=2, per_page=2)
        assert [i["name"] for i in page2["items"]] == ["Saber"]

    def test_series_mode_and_alphabet_sort(self, clean_db):
        self._seed(clean_db)
        result = clean_db.search_catalog("re:zero", mode="series", sort="alphabet")
        assert [i["name"] for i in result["items"]] == ["Emilia", "Rem"]

    def test_marks_library_rows_and_counts_their_images(self, clean_db):
        self._seed(clean_db)
        clean_db.add_character("Rem", "Hand Edited", "3", "")
        clean_db.add_custom_images("Rem", ["https://cdn/rem-1.png", "https://cdn/rem-2.png"])
        item = clean_db.search_catalog("rem")["items"][0]
        assert item["in_library"] is True
        assert item["series"] == "Hand Edited"
        assert item["custom_count"] == 2

    def test_catalog_only_row_is_not_in_library(self, clean_db):
        self._seed(clean_db)
        item = clean_db.search_catalog("saber")["items"][0]
        assert item["in_library"] is False
        assert item["custom_count"] == 0

    def test_count_sort_puts_the_fullest_first(self, clean_db):
        self._seed(clean_db)
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        clean_db.add_character("Emilia", "Re:Zero", "2", "")
        clean_db.add_custom_images("Rem", ["https://cdn/rem-1.png", "https://cdn/rem-2.png"])
        clean_db.add_custom_images("Emilia", ["https://cdn/emilia-1.png"])
        names = [
            i["name"] for i in clean_db.search_catalog("e", sort="count", order="desc")["items"]
        ]
        assert names == ["Rem", "Emilia", "Saber"]


class TestCatalogRoutes:
    def _seed(self, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Artoria Pendragon", "Fate/stay night", "4"),
                _catalog_row("Rem", "Re:Zero", "3"),
            ],
        )

    def test_suggestions_endpoint(self, client, clean_db):
        self._seed(clean_db)
        body = client.get("/api/catalog/characters?q=art").get_json()
        assert body["items"][0]["name"] == "Artoria Pendragon"
        assert body["items"][0]["series"] == "Fate/stay night"

    def test_suggestions_endpoint_filters_by_pool(self, client, clean_db):
        seed_catalog(
            clean_db,
            [
                _catalog_row("Waifu", "S", "1"),
                _catalog_row(
                    "Husbando", "S", "2", is_waifu=False, is_anime=False, is_husbando=True
                ),
            ],
        )
        body = client.get("/api/catalog/characters?pool=husbando").get_json()
        assert [i["name"] for i in body["items"]] == ["Husbando"]

    def test_search_endpoint(self, client, clean_db):
        self._seed(clean_db)
        body = client.get("/api/catalog/search?q=r&sort=rank&order=asc").get_json()
        assert [i["name"] for i in body["items"]] == ["Rem", "Artoria Pendragon"]
        assert body["total"] == 2

    def test_series_endpoint(self, client, clean_db):
        self._seed(clean_db)
        body = client.get("/api/catalog/series").get_json()
        assert set(body["items"]) >= {"Fate/stay night", "Re:Zero"}

    def test_character_lookup_found_and_missing(self, client, clean_db):
        self._seed(clean_db)
        found = client.get("/api/catalog/character?name=Rem").get_json()
        assert found["found"] is True
        assert found["character"]["series"] == "Re:Zero"
        missing = client.get("/api/catalog/character?name=Nobody").get_json()
        assert missing == {"found": False, "character": None}

    def test_add_from_catalog_uses_the_mudae_portrait(self, client, clean_db):
        self._seed(clean_db)
        res = client.post("/api/catalog/add-character", json={"name": "Rem"})
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["source"] == "catalog"
        row = (
            clean_db.get_connection()
            .execute("SELECT series, rank, main_image_url FROM characters WHERE name = 'Rem'")
            .fetchone()
        )
        assert row["series"] == "Re:Zero"
        assert row["main_image_url"].startswith("https://mudae.net/")

    def test_add_from_catalog_rejects_a_known_working_character(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        self._seed(clean_db)
        res = client.post("/api/catalog/add-character", json={"name": "Rem"})
        assert res.status_code == 400
        assert "already exists" in res.get_json()["error"]

    def test_add_from_catalog_rejects_an_unknown_name(self, client, clean_db):
        self._seed(clean_db)
        res = client.post("/api/catalog/add-character", json={"name": "Nobody"})
        assert res.status_code == 404


class TestManualAdd:
    """The manual form can carry a catalog portrait and refuses duplicates."""

    def _seed(self, clean_db):
        clean_db.add_character("Seed", "Some Series", "1", "")

    def test_accepts_a_mudae_portrait_url(self, client, clean_db, make_signed_in):
        # A brand-new character needs an account now; this test is about the
        # portrait URL, so satisfy the gate.
        make_signed_in()
        self._seed(clean_db)
        res = client.post(
            "/api/add-character",
            data={
                "name": "Newcomer",
                "series": "Some Series",
                "rank": "500",
                "image_url": "https://mudae.net/uploads/1/a~b.png",
            },
        )
        assert res.status_code == 200
        row = (
            clean_db.get_connection()
            .execute("SELECT main_image_url FROM characters WHERE name = 'Newcomer'")
            .fetchone()
        )
        assert row["main_image_url"] == "https://mudae.net/uploads/1/a~b.png"

    def test_refuses_a_portrait_url_from_an_unexpected_host(self, client, clean_db, make_signed_in):
        make_signed_in()
        self._seed(clean_db)
        res = client.post(
            "/api/add-character",
            data={"name": "Newcomer", "image_url": "https://evil.example/x.png"},
        )
        assert res.status_code == 400

    def test_a_name_already_in_the_library_is_refused_case_insensitively(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        res = client.post("/api/add-character", data={"name": "rem", "series": "Re:Zero"})
        assert res.status_code == 400
        assert "already exists" in res.get_json()["error"]
