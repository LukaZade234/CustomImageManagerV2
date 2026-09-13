"""The `$imartsmi-` series flow: DM parsing, the preview, and applying it.

Mudae answers `$imartsmi- <series>` with a DM (split across messages) that looks
nothing like the pasted extracts: a header without the " - " separator, then
alias lines, pool totals and value stats around the character lines. The parser
has to keep only the header and the `#rank - Name · ($pools) - url` lines, and
the apply has to create or refresh working rows without touching fields that
already match.
"""

import asyncio
import time
from datetime import UTC, datetime

import catalog_import
import mudae_discord
from routes import mudae as mudae_routes

EXTRACT = """-----
**Lord of the Mysteries   0/3**

*LoM*
*LotM*
*Lord of Mysteries*
*诡秘之主*

*2 $wa, 1 $ha, 0 $wg, 0 $hg*

**AVG:** 54,050
**Top 10 value:** 133,624

**#4,252** - Klein Moretti · *($ha)* - <https://mudae.net/uploads/1688294/V40OZzn~uUp4hS7.png>
**#8,123** - Audrey Hall · *($wa)* - <https://mudae.net/uploads/2957218/7yRes_J~Wldc5XX.png>
**#10,320** - Trissy · *($wa, $ha)* - <https://mudae.net/uploads/1200477/3CG-zLv~xTFOJNL.png>
"""


class TestParseSeriesExtract:
    def test_it_reads_the_header_and_characters(self):
        result = catalog_import.parse_series_extract(EXTRACT)

        assert result.series == "Lord of the Mysteries"
        assert result.listed == 0
        assert result.total == 3
        assert [c.name for c in result.characters] == [
            "Klein Moretti",
            "Audrey Hall",
            "Trissy",
        ]
        assert [c.rank for c in result.characters] == ["4252", "8123", "10320"]
        # The header's series is stamped onto every character.
        assert all(c.series == "Lord of the Mysteries" for c in result.characters)
        assert result.characters[2].pool == "ha,wa"
        # The `~` in a mudae.net filename must survive markdown stripping.
        assert (
            result.characters[0].image_url
            == "https://mudae.net/uploads/1688294/V40OZzn~uUp4hS7.png"
        )
        assert result.issues == []

    def test_alias_pool_and_stat_lines_are_not_issues(self):
        result = catalog_import.parse_series_extract(EXTRACT)
        assert result.issues == []

    def test_a_dashed_header_still_parses(self):
        header = catalog_import.parse_series_header("【OSHI NO KO】 - 9/27")
        assert header is not None
        assert header.series == "【OSHI NO KO】"
        assert header.listed == 9
        assert header.total == 27

    def test_a_character_seen_twice_is_collapsed(self):
        text = (
            "S   0/2\n"
            "#900 - Rem · ($wa) - https://mudae.net/uploads/1/a.png\n"
            "#3 - Rem · ($wa) - https://mudae.net/uploads/2/b.png\n"
        )
        result = catalog_import.parse_series_extract(text)
        assert len(result.characters) == 1
        assert result.characters[0].rank == "3"


class _FakeAuthor:
    def __init__(self, author_id):
        self.id = author_id


class _FakeMessage:
    def __init__(self, content="", *, author_id=0, guild=None, created_at=None, embeds=None):
        self.content = content
        self.author = _FakeAuthor(author_id)
        self.guild = guild
        self.embeds = embeds or []
        self.id = 1
        stamp = created_at if created_at is not None else time.time()
        self.created_at = datetime.fromtimestamp(stamp, tz=UTC)


def _dm_session():
    session = object.__new__(mudae_discord._MudaeSession)
    session._mudae_id = 999
    session._dm_parts = []
    session._dm_event = asyncio.Event()
    session._dm_active = True
    session._dm_not_before = 0.0
    return session


class TestCaptureDmParts:
    def test_a_mudae_dm_is_collected(self):
        session = _dm_session()
        message = _FakeMessage("Lord of the Mysteries   0/3", author_id=999)

        asyncio.run(session._maybe_capture_dm(message))

        assert session._dm_parts == ["Lord of the Mysteries   0/3"]
        assert session._dm_event.is_set()

    def test_a_guild_message_is_not_collected(self):
        session = _dm_session()
        message = _FakeMessage("noise", author_id=999, guild=object())

        asyncio.run(session._maybe_capture_dm(message))

        assert session._dm_parts == []

    def test_another_author_is_not_collected(self):
        session = _dm_session()
        message = _FakeMessage("noise", author_id=5)

        asyncio.run(session._maybe_capture_dm(message))

        assert session._dm_parts == []

    def test_it_stops_once_the_header_total_is_reached(self):
        session = _dm_session()
        session._dm_parts = [EXTRACT]
        session._dm_event.set()

        text = asyncio.run(session._collect_series_dm())

        assert text == EXTRACT


class TestSeriesExtractRoute:
    def test_preview_marks_new_and_changed_characters(self, client, clean_db, monkeypatch):
        clean_db.add_character(
            "Audrey Hall", "Old Series", "9", "https://mudae.net/uploads/2957218/old.png"
        )
        monkeypatch.setattr(
            mudae_routes.mudae_discord, "fetch_series_extract", lambda series: EXTRACT
        )

        res = client.post("/api/mudae/series-extract", json={"series": "Lord of the Mysteries"})
        assert res.status_code == 200
        body = res.get_json()

        assert body["series"] == "Lord of the Mysteries"
        assert body["total"] == 3
        assert body["new_count"] == 2
        by_name = {item["name"]: item for item in body["items"]}
        assert by_name["Klein Moretti"]["in_library"] is False
        assert by_name["Trissy"]["in_library"] is False
        assert by_name["Audrey Hall"]["in_library"] is True
        assert set(by_name["Audrey Hall"]["changes"]) == {"series", "rank", "image"}

    def test_an_empty_dm_is_reported(self, client, clean_db, monkeypatch):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        monkeypatch.setattr(
            mudae_routes.mudae_discord, "fetch_series_extract", lambda series: "just noise"
        )

        res = client.post("/api/mudae/series-extract", json={"series": "Nowhere"})

        assert res.status_code == 502
        assert "no characters" in res.get_json()["error"]


class TestSeriesExtractApply:
    def test_it_creates_new_and_updates_only_changed_fields(self, client, clean_db):
        clean_db.add_character(
            "Audrey Hall", "Old Series", "9", "https://mudae.net/uploads/2/old.png"
        )
        items = [
            {
                "name": "Klein Moretti",
                "rank": "4252",
                "image_url": "https://mudae.net/uploads/1688294/a.png",
            },
            {
                "name": "Audrey Hall",
                "rank": "8123",
                "image_url": "https://mudae.net/uploads/2957218/b.png",
            },
        ]

        res = client.post(
            "/api/mudae/series-extract/apply",
            json={"series": "Lord of the Mysteries", "items": items},
        )

        assert res.status_code == 200
        body = res.get_json()
        assert body["created"] == 1
        assert body["updated"] == 1
        assert body["unchanged"] == 0

        rows = {c["name"]: c for c in clean_db.get_characters()}
        assert rows["Klein Moretti"]["series"] == "Lord of the Mysteries"
        assert rows["Audrey Hall"]["series"] == "Lord of the Mysteries"
        assert rows["Audrey Hall"]["rank"] == "8123"
        assert rows["Audrey Hall"]["image"].endswith("/b.png")

    def test_reapplying_the_same_list_is_a_no_op(self, client, clean_db):
        clean_db.add_character("Seed", "S", "1", "")
        items = [
            {"name": "Klein Moretti", "rank": "4252", "image_url": ""},
            {"name": "Audrey Hall", "rank": "8123", "image_url": ""},
        ]
        client.post(
            "/api/mudae/series-extract/apply",
            json={"series": "S", "items": items},
        )

        res = client.post(
            "/api/mudae/series-extract/apply",
            json={"series": "S", "items": items},
        )

        body = res.get_json()
        assert body["created"] == 0
        assert body["updated"] == 0
        assert body["unchanged"] == 2

    def test_a_non_portrait_image_url_is_rejected(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        res = client.post(
            "/api/mudae/series-extract/apply",
            json={
                "series": "S",
                "items": [{"name": "Rem", "rank": "3", "image_url": "https://evil.example/x.png"}],
            },
        )
        assert res.status_code == 400
        assert res.get_json()["error"] == "No valid characters to add"

    def test_an_empty_list_is_rejected(self, client, clean_db):
        clean_db.add_character("Rem", "Re:Zero", "3", "")
        res = client.post("/api/mudae/series-extract/apply", json={"series": "S", "items": []})
        assert res.status_code == 400
