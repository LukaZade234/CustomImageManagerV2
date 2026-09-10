"""Server-side stats, search, sort and pagination for the customs list.

These replace work the browser used to do after downloading the entire library.
Two things are worth pinning: the sort key is whitelisted rather than
interpolated, and LIKE wildcards in a search term are escaped -- otherwise
searching for "%" matches everything, which looks like a broken filter and is
the shape of an injection bug.
"""

import json


def _seed(db, spec, owner=None):
    """spec: {character: (series, rank, image_count)}"""
    if owner is not None:
        db.ensure_identity(owner)
    for name, (series, rank, count) in spec.items():
        db.add_character(name, series, rank, f"{name}.png")
        db.add_custom_images(
            name, [f"https://cdn/{name}-{i}.png" for i in range(count)], added_by=owner
        )


class TestStats:
    def test_counts_images_and_characters(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 3), "Emilia": ("Re:Zero", "2", 2)})
        body = client.get("/api/stats").get_json()
        assert body["custom_images"] == 5
        assert body["characters_with_customs"] == 2

    def test_an_empty_library_reports_zero(self, client, clean_db):
        body = client.get("/api/stats").get_json()
        assert body["custom_images"] == 0
        assert body["characters_with_customs"] == 0

    def test_removed_images_do_not_count(self, client, clean_db, identity_id):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 2)}, owner=identity_id)
        clean_db.remove_custom_images("Rem", ["https://cdn/Rem-0.png"], identity_id)
        assert client.get("/api/stats").get_json()["custom_images"] == 1

    def test_the_payload_does_not_grow_with_the_library(self, client, clean_db):
        """The whole point: a fixed summary, not the library.

        The page carries highlights now as well as the two totals, so this is no
        longer "a couple of hundred bytes". What still has to hold is that the
        size is bounded by the number of items shown rather than by how much is
        in the database -- the original bug was downloading every image URL for
        every character, about 475 KB, to display two integers.
        """
        # Enough to fill every capped list, so the first measurement is already
        # at the ceiling rather than still growing into it.
        _seed(clean_db, {f"Char{i:03d}": ("S", "1", 5) for i in range(40)})
        small = len(client.get("/api/stats").data)

        _seed(clean_db, {f"More{i:03d}": ("S", "1", 5) for i in range(200)})
        large = len(client.get("/api/stats").data)

        assert large - small < 200, f"payload grew {large - small} bytes for 6x the library"
        assert large < 8000


class TestListing:
    def test_returns_counts_and_previews(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 5)})
        item = client.get("/api/customs").get_json()["items"][0]
        assert item["name"] == "Rem"
        assert item["series"] == "Re:Zero"
        assert item["count"] == 5
        assert len(item["previews"]) == 3, "previews are capped so the page stays small"

    def test_characters_without_customs_are_absent(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1)})
        clean_db.add_character("Nobody", "None", "9", "")
        names = [i["name"] for i in client.get("/api/customs").get_json()["items"]]
        assert names == ["Rem"]

    def test_pagination_splits_and_reports_totals(self, client, clean_db):
        _seed(clean_db, {f"Char{i:02d}": ("S", "1", 1) for i in range(25)})
        first = client.get("/api/customs?per_page=10&sort=name_asc").get_json()
        assert first["total"] == 25
        assert first["total_pages"] == 3
        assert len(first["items"]) == 10

        last = client.get("/api/customs?per_page=10&page=3&sort=name_asc").get_json()
        assert len(last["items"]) == 5
        assert last["items"][0]["name"] == "Char20"

    def test_per_page_is_capped(self, client, clean_db):
        """An unbounded per_page would put the full-map fetch straight back."""
        _seed(clean_db, {f"Char{i:03d}": ("S", "1", 1) for i in range(120)})
        body = client.get("/api/customs?per_page=100000").get_json()
        assert body["per_page"] == 100


class TestSearch:
    def test_by_name(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1), "Emilia": ("Re:Zero", "2", 1)})
        body = client.get("/api/customs?q=rem").get_json()
        assert [i["name"] for i in body["items"]] == ["Rem"]

    def test_by_series(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1), "Rei": ("Evangelion", "2", 1)})
        body = client.get("/api/customs?q=evangelion&by=series").get_json()
        assert [i["name"] for i in body["items"]] == ["Rei"]

    def test_is_case_insensitive(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1)})
        assert client.get("/api/customs?q=REM").get_json()["total"] == 1

    def test_like_wildcards_in_the_term_are_escaped(self, client, clean_db):
        """Otherwise "%" silently matches everything and the filter looks broken."""
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1), "Emilia": ("Re:Zero", "2", 1)})
        assert client.get("/api/customs?q=%25").get_json()["total"] == 0
        assert client.get("/api/customs?q=_").get_json()["total"] == 0

    def test_total_reflects_the_filter_not_the_library(self, client, clean_db):
        _seed(clean_db, {f"Char{i:02d}": ("S", "1", 1) for i in range(30)})
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 1)})
        assert client.get("/api/customs?q=rem").get_json()["total"] == 1


class TestSort:
    def test_by_image_count(self, client, clean_db):
        _seed(clean_db, {"Few": ("S", "1", 1), "Many": ("S", "2", 9)})
        desc = [i["name"] for i in client.get("/api/customs?sort=count_desc").get_json()["items"]]
        assert desc == ["Many", "Few"]
        asc = [i["name"] for i in client.get("/api/customs?sort=count_asc").get_json()["items"]]
        assert asc == ["Few", "Many"]

    def test_by_name_both_ways(self, client, clean_db):
        _seed(clean_db, {"Alpha": ("S", "1", 1), "Zeta": ("S", "2", 1)})
        asc = [i["name"] for i in client.get("/api/customs?sort=name_asc").get_json()["items"]]
        assert asc == ["Alpha", "Zeta"]
        desc = [i["name"] for i in client.get("/api/customs?sort=name_desc").get_json()["items"]]
        assert desc == ["Zeta", "Alpha"]

    def test_unranked_characters_sort_last_not_first(self, client, clean_db):
        """rank is TEXT and often empty; treating '' as 0 would put them on top."""
        _seed(clean_db, {"Ranked": ("S", "5", 1), "Unranked": ("S", "", 1)})
        names = [i["name"] for i in client.get("/api/customs?sort=rank_asc").get_json()["items"]]
        assert names == ["Ranked", "Unranked"]

    def test_an_unknown_sort_is_rejected_rather_than_interpolated(self, client, clean_db):
        _seed(clean_db, {"Rem": ("S", "1", 1)})
        r = client.get("/api/customs?sort=name;DROP TABLE characters")
        assert r.status_code == 400
        # And the table is still there.
        assert client.get("/api/customs").get_json()["total"] == 1

    def test_non_integer_paging_is_rejected(self, client, clean_db):
        assert client.get("/api/customs?page=abc").status_code == 400


class TestPayloadSize:
    def test_a_page_does_not_grow_with_the_library(self, client, clean_db):
        """The regression this whole change exists to prevent.

        The old endpoint returned every URL for every character, so the response
        grew without bound. A page must cost the same whether the library holds
        twenty characters or two hundred.
        """
        _seed(clean_db, {f"Char{i:03d}": ("Series", "1", 12) for i in range(20)})
        small = len(client.get("/api/customs?per_page=20").data)
        _seed(clean_db, {f"More{i:03d}": ("Series", "1", 12) for i in range(180)})
        large = len(client.get("/api/customs?per_page=20").data)
        assert client.get("/api/customs").get_json()["total"] == 200
        assert abs(large - small) < small * 0.2, (
            f"a page went from {small} to {large} bytes as the library grew 10x"
        )

    def test_previews_are_capped_regardless_of_library_size(self, client, clean_db):
        _seed(clean_db, {"Hoarder": ("S", "1", 300)})
        item = client.get("/api/customs").get_json()["items"][0]
        assert item["count"] == 300
        assert len(item["previews"]) == 3
        assert len(json.dumps(item)) < 600


class TestHomeHighlights:
    """The landing page's content, which /api/stats returns alongside the totals.

    What is absent matters as much as what is present. There is no visitor count
    because an identity row is created per cookie, and no most-visited section
    because nothing records page views yet -- `image_takes` counts copy and
    download actions, which measure something else entirely.
    """

    def test_best_covered_characters_are_ranked_by_image_count(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 5), "Emilia": ("Re:Zero", "2", 2)})
        best = client.get("/api/stats").get_json()["best_covered"]
        assert [(c["name"], c["images"]) for c in best] == [("Rem", 5), ("Emilia", 2)]

    def test_series_are_ranked_and_count_their_characters(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 3), "Emilia": ("Re:Zero", "2", 2)})
        _seed(clean_db, {"Lucy": ("Edgerunners", "1", 4)})
        body = client.get("/api/stats").get_json()
        assert body["top_series"][0] == {"series": "Re:Zero", "images": 5, "characters": 2}
        assert body["series_count"] == 2

    def test_a_character_with_no_series_is_not_a_series(self, client, clean_db):
        _seed(clean_db, {"Nobody": ("", "1", 2)})
        body = client.get("/api/stats").get_json()
        assert body["series_count"] == 0
        assert body["top_series"] == []

    def test_recent_images_are_newest_first_and_carry_a_thumbnail(self, client, clean_db):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 3)})
        recent = client.get("/api/stats").get_json()["recent"]
        assert recent[0]["character"] == "Rem"
        assert recent[0]["thumb"] == f"/thumbs/{recent[0]['id']}.webp"
        assert [r["id"] for r in recent] == sorted((r["id"] for r in recent), reverse=True)

    def test_recent_shows_each_character_once(self, client, clean_db):
        """Images arrive in batches, so the raw newest-first list is one face
        repeated across the whole strip, which reads as a bug."""
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 6), "Emilia": ("Re:Zero", "2", 4)})
        recent = client.get("/api/stats").get_json()["recent"]
        names = [r["character"] for r in recent]
        assert sorted(names) == ["Emilia", "Rem"], names

    def test_removed_images_are_excluded_everywhere(self, client, clean_db, identity_id):
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 3)}, owner=identity_id)
        clean_db.remove_custom_images("Rem", ["https://cdn/Rem-0.png"], identity_id)
        body = client.get("/api/stats").get_json()
        assert body["best_covered"][0]["images"] == 2
        assert body["top_series"][0]["images"] == 2
        # One entry per character, and it must not be the removed image.
        assert len(body["recent"]) == 1
        assert body["recent"][0]["url"] != "https://cdn/Rem-0.png"

    def test_only_discord_users_appear_as_contributors(self, client, clean_db, identity_id):
        """Anonymity has to be real, not merely unlabelled.

        A cookie pseudonym never chose to be named, so it is never ranked. Only
        someone who signed in with Discord can appear here.
        """
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 3)}, owner=identity_id)
        assert client.get("/api/stats").get_json()["contributors"] == []

        clean_db.bind_discord_identity(identity_id, "discord-123", display_name="Someone")
        contributors = client.get("/api/stats").get_json()["contributors"]
        assert [(c["handle"], c["images"]) for c in contributors] == [("Someone", 3)]

    def test_images_with_no_owner_are_nobody_s(self, client, clean_db):
        """8,547 of the library predates ownership and must not inflate anyone."""
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 4)}, owner=None)
        assert client.get("/api/stats").get_json()["contributors"] == []

    def test_the_totals_survive_a_broken_highlights_query(self, client, clean_db, monkeypatch):
        """A landing page showing two numbers beats one showing an error."""
        _seed(clean_db, {"Rem": ("Re:Zero", "1", 2)})
        monkeypatch.setattr(clean_db, "get_home_highlights", lambda *a, **kw: 1 / 0)
        body = client.get("/api/stats").get_json()
        assert body["custom_images"] == 2
        assert body["best_covered"] == []
        assert body["series_count"] == 0
