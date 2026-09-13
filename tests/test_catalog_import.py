"""Mudae catalog parsing, merging and enrichment.

The extracts are arbitrary Unicode and overlap heavily: the same character is
re-captured by many sources, series names are emoji or CJK brackets, and names
carry accents, fullwidth characters and middle dots. These tests pin that a
single odd line is reported rather than fatal, and that the merge collapses
overlap by a Unicode-folded key instead of SQLite's ASCII-only NOCASE.
"""

import importlib

import catalog_import as ci
import remote_images

SAMPLE = """{ tákt op. } - 3/45
#369 - Destiny · ($wa, $wg) - https://mudae.net/uploads/9986421/-QzxG80~0H9iPfL.png
#4,184 - Heaven · ($wa) - https://mudae.net/uploads/7318575/YMJZtNi~hAMn4ZM.png
#6,102 - Anna Schneider · ($wa) - https://mudae.net/uploads/3558806/i6gZbFI~nb2W88F.png

【OSHI NO KO】 - 9/27
#54 - Ai Hoshino · ($wa) - https://mudae.net/uploads/5711403/mwfbqTN~w5sjhP3.png
#180 - Ruby Hoshino · ($wa) - https://mudae.net/uploads/2786228/MM9vINr~JfvEsXP.png
#547 - MEM-Cho · ($wa) - https://mudae.net/uploads/4907088/Yu3FSII~9WuNo45.png

🤔 - 15/87
#75 - Truck-kun · ($wa, $ha) - https://mudae.net/uploads/8324657/meO9RPS~qToHNt4.png
#170 - Trollface · ($wa, $ha) - https://mudae.net/uploads/7427875/pJidCh0~YYUlPcy.png
#419 - Wise Mystical Tree · ($wa, $ha) - https://mudae.net/uploads/8807266/PwE7fts~eeC14dY.png\x20
"""


class TestParsing:
    def test_parses_emoji_and_bracket_series(self):
        result = ci.parse_text(SAMPLE)
        assert result.characters[ci.name_key("Ai Hoshino")].series == "【OSHI NO KO】"
        assert result.characters[ci.name_key("Truck-kun")].series == "🤔"
        assert result.characters[ci.name_key("Destiny")].series == "{ tákt op. }"
        assert len(result.characters) == 9
        assert len(result.series) == 3

    def test_strips_rank_commas_and_records_pools(self):
        truck = ci.parse_text(SAMPLE).characters[ci.name_key("Truck-kun")]
        assert truck.rank == "75"
        assert truck.pool == "ha,wa"
        assert truck.is_waifu and truck.is_husbando
        assert truck.is_anime and not truck.is_game
        heaven = ci.parse_text(SAMPLE).characters[ci.name_key("Heaven")]
        assert heaven.rank == "4184"

    def test_a_middle_dot_inside_a_name_is_not_the_separator(self):
        result = ci.parse_text("#1 - A · B · ($wa) - https://mudae.net/uploads/1/aa~bb.png")
        character = result.characters[ci.name_key("A · B")]
        assert character.name == "A · B"
        assert character.pool == "wa"

    def test_fullwidth_name_folds_to_the_same_key(self):
        result = ci.parse_text(
            "#3 - ＭＥＭ-Ｃｈｏ · ($wa) - https://mudae.net/uploads/3/ee~ff.png"
        )
        assert ci.name_key("MEM-Cho") in result.characters

    def test_trailing_whitespace_and_crlf_and_bom_are_tolerated(self):
        text = "\ufeff【OSHI NO KO】 - 1/2\r\n#54 - Ai Hoshino · ($wa) - https://mudae.net/uploads/1/a.png   \r\n"
        result = ci.parse_text(text)
        assert result.issues == []
        assert result.series[ci.name_key("【OSHI NO KO】")].total == 2
        assert result.characters[ci.name_key("Ai Hoshino")].name == "Ai Hoshino"

    def test_a_malformed_line_is_an_issue_not_a_crash(self):
        result = ci.parse_text("🤔 - 1/1\nthis is not a line\n#1 - Rem - https://x\n")
        assert len(result.characters) == 0
        assert len(result.issues) == 2
        assert all(issue.line_no in (2, 3) for issue in result.issues)

    def test_an_unknown_pool_keeps_the_character(self):
        result = ci.parse_text(
            "#1 - Rem · ($zz) - https://mudae.net/uploads/1/aa~bb.png"
        )
        character = result.characters[ci.name_key("Rem")]
        assert character.pool == ""
        assert len(result.issues) == 1
        assert "unknown pool" in result.issues[0].reason

    def test_duplicate_lines_within_one_source_collapse(self):
        line = "#1 - Rem · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        result = ci.parse_text(f"{line}\n{line}\n")
        assert len(result.characters) == 1
        assert result.duplicates == 1

    def test_validate_character_name_rejects_path_traversal(self):
        result = ci.parse_text(
            "#1 - ../etc/passwd · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        )
        assert not result.characters
        assert result.issues


ACCOUNT_MARKER_SAMPLE = """【OSHI NO KO】 - 2/27
#11,203 - Yoriko Kichijouji  🚫  $wa  DISABLED · ($wa) - https://mudae.net/uploads/6785771/VuJlTLR~3Txc1Sb.png
#11,321 - Koyuki Yoshidomi  🚫  $wa  DISABLED · ($wa) - https://mudae.net/uploads/7979188/-xj7UCg~l4necpbkw94.png

100% Personal - 2/4
#11,093 - Yi-Seul Choi  🚫  $wa  DISABLED · ($wa) - https://mudae.net/uploads/4893428/75e0yai~xBMd9qS.png
#11,626 - Su-Ah Kang  🚫  $wa  DISABLED · ($wa) - https://mudae.net/uploads/6645446/fpTUccr~324nQO3.png

3-gatsu no Lion - 1/34
#10,543 - Hinata Kawamoto  🚫  $wa  DISABLED · ($wa) - https://mudae.net/uploads/7060800/zsE4Nyw~eybajea.png
"""


class TestAccountMarkers:
    def test_disabled_marker_is_stripped_from_the_name(self):
        result = ci.parse_text(ACCOUNT_MARKER_SAMPLE)
        assert result.issues == []
        yoriko = result.characters[ci.name_key("Yoriko Kichijouji")]
        assert yoriko.name == "Yoriko Kichijouji"
        assert yoriko.rank == "11203"
        assert yoriko.pool == "wa"
        assert yoriko.series == "【OSHI NO KO】"

    def test_every_marked_line_parses_and_percent_series_works(self):
        result = ci.parse_text(ACCOUNT_MARKER_SAMPLE)
        assert len(result.characters) == 5
        assert result.series[ci.name_key("100% Personal")].total == 4
        assert result.characters[ci.name_key("Hinata Kawamoto")].series == "3-gatsu no Lion"

    def test_marker_stripper_leaves_ordinary_names_alone(self):
        assert ci.strip_account_marker("Ai Hoshino") == "Ai Hoshino"
        assert ci.strip_account_marker("C.C.") == "C.C."
        assert ci.strip_account_marker("Sung Jin-Woo") == "Sung Jin-Woo"

    def test_marker_stripper_handles_marker_without_an_emoji(self):
        assert ci.strip_account_marker("Rem  $wg  DISABLED") == "Rem"

    def test_the_real_pool_comes_from_the_parentheses_not_the_marker(self):
        # The marker's own "$wg" is account noise; the pool in "( )" is the data.
        result = ci.parse_text(
            "#1 - Rem  🚫  $wg  DISABLED · ($wa, $ha) - https://mudae.net/uploads/1/aa~bb.png"
        )
        rem = result.characters[ci.name_key("Rem")]
        assert rem.name == "Rem"
        assert rem.pool == "ha,wa"
        assert rem.is_waifu and rem.is_husbando and rem.is_anime and not rem.is_game

    def test_serverdisable_marker_is_stripped(self):
        result = ci.parse_text(
            "#1,395 - Louise Françoise Le Blanc de La Vallière 🚫  "
            "($serverdisable) · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        )
        louise = result.characters[ci.name_key("Louise Françoise Le Blanc de La Vallière")]
        assert louise.name == "Louise Françoise Le Blanc de La Vallière"
        assert louise.rank == "1395"
        assert louise.pool == "wa"
        assert result.issues == []

    def test_serverdisable_marker_on_a_two_letter_name(self):
        result = ci.parse_text(
            "#3,250 - Ca 🚫  ($serverdisable) · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        )
        assert result.characters[ci.name_key("Ca")].name == "Ca"

    def test_marker_stripper_handles_serverdisable_variants(self):
        assert ci.strip_account_marker("Rem  ($serverdisable)") == "Rem"
        assert ci.strip_account_marker("Rem  $serverdisable") == "Rem"
        assert ci.strip_account_marker("Rem 🚫  (serverdisable)") == "Rem"


class TestNameKey:
    def test_folds_nfd_nfc_fullwidth_and_nbsp(self):
        assert ci.name_key("Pokémon") == ci.name_key("Poke\u0301mon")
        assert ci.name_key("Hange Zoë") == ci.name_key("Hange Zoe\u0308")
        assert ci.name_key("MEM-Cho") == ci.name_key("ＭＥＭ-Ｃｈｏ")
        assert ci.name_key("Seo  Eun-hyun") == ci.name_key("Seo\u00a0Eun-hyun")

    def test_curly_apostrophe_matches_straight(self):
        assert ci.name_key("Jeanne d’Arc") == ci.name_key("Jeanne d'Arc")


class TestMerge:
    def test_repeated_character_across_sources_is_dropped(self):
        line = "#1 - Rem · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        result = ci.parse_sources([("a.txt", line), ("b.txt", line)])
        assert len(result.characters) == 1
        assert result.duplicates == 1
        assert result.sources == ["a.txt", "b.txt"]

    def test_conflicting_capture_keeps_the_better_rank(self):
        first = "#900 - Rem · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        second = "#3 - Rem · ($wa) - https://mudae.net/uploads/2/cc~dd.png"
        result = ci.parse_sources([("a.txt", first), ("b.txt", second)])
        assert result.characters[ci.name_key("Rem")].rank == "3"
        assert result.characters[ci.name_key("Rem")].image_url.endswith("cc~dd.png")
        assert result.conflicts == 1

    def test_unranked_never_beats_a_ranked_duplicate(self):
        ranked = "#5 - Rem · ($wa) - https://mudae.net/uploads/1/aa~bb.png"
        unranked = "#5,000 - Rem · ($wa) - https://mudae.net/uploads/2/cc~dd.png"
        result = ci.parse_sources([("a.txt", unranked), ("b.txt", ranked)])
        assert result.characters[ci.name_key("Rem")].rank == "5"

    def test_series_coverage_keeps_the_widest(self):
        a = "Rem - 2/20\n#1 - Rem · ($wa) - https://mudae.net/uploads/1/a.png"
        b = "Rem - 5/20\n#2 - Emi · ($wa) - https://mudae.net/uploads/2/b.png"
        result = ci.parse_sources([("a.txt", a), ("b.txt", b)])
        series = result.series[ci.name_key("Rem")]
        assert (series.listed, series.total) == (5, 20)

    def test_row_shapes_for_the_database(self):
        result = ci.parse_text(SAMPLE)
        rows = ci.as_catalog_rows(result)
        assert len(rows) == len(result.characters)
        assert {"name", "name_key", "series", "rank", "mudae_image_url"} <= set(rows[0])
        preview = ci.as_catalog_map(result)
        assert set(preview) == set(result.characters)


class TestPortraitAllowlist:
    def test_accepts_mudae_and_imgchest(self):
        assert remote_images._allowed_portrait_url("https://mudae.net/uploads/1/a.png")
        assert remote_images._allowed_portrait_url("https://cdn.imgchest.com/files/a.png")
        assert remote_images._allowed_portrait_url("https://sub.mudae.net/a.png")

    def test_rejects_other_hosts(self):
        assert not remote_images._allowed_portrait_url("https://evil.example/a.png")
        assert not remote_images._allowed_portrait_url("https://mudae.net.evil.example/a.png")
        assert not remote_images._allowed_portrait_url("file:///etc/passwd")

    def test_the_user_download_proxy_stays_imgchest_only(self):
        assert remote_images._allowed_image_proxy_url("https://cdn.imgchest.com/files/a.png")
        assert not remote_images._allowed_image_proxy_url("https://mudae.net/uploads/1/a.png")


class TestCatalogDatabase:
    def _rows(self, text=SAMPLE):
        return ci.as_catalog_rows(ci.parse_text(text))

    def test_upsert_is_idempotent_and_reports_counts(self, clean_db):
        rows = self._rows()
        inserted, updated = clean_db.upsert_catalog_characters(
            rows, scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )
        assert inserted == len(rows)
        assert updated == 0

        inserted, updated = clean_db.upsert_catalog_characters(
            rows, scraped_at="2026-01-02T00:00:00Z", source_batch="test"
        )
        assert (inserted, updated) == (0, len(rows))

        stored = {row["name_key"]: row for row in clean_db.get_catalog_characters()}
        ai = stored[ci.name_key("Ai Hoshino")]
        assert ai["series"] == "【OSHI NO KO】"
        assert ai["is_waifu"] == 1
        assert ai["mudae_image_url"].startswith("https://mudae.net/")

    def test_series_upsert_keeps_the_widest(self, clean_db):
        clean_db.upsert_catalog_series([{"series": "Rem", "listed": 2, "total": 20}], scraped_at="a")
        clean_db.upsert_catalog_series([{"series": "Rem", "listed": 5, "total": 20}], scraped_at="b")
        conn = clean_db.get_connection()
        row = conn.execute("SELECT listed, total FROM catalog_series WHERE series = 'Rem'").fetchone()
        assert (row["listed"], row["total"]) == (5, 20)

    def test_enrichment_updates_rank_series_and_portrait(self, clean_db):
        clean_db.add_character("Ai Hoshino", "Old Series", "", "")
        clean_db.upsert_catalog_characters(
            self._rows(), scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )

        result = clean_db.enrich_characters_from_catalog()

        assert result["matched"] == 1
        assert result["updated"] == 1
        row = clean_db.get_connection().execute(
            "SELECT series, rank, main_image_url FROM characters WHERE name = 'Ai Hoshino'"
        ).fetchone()
        assert row["series"] == "【OSHI NO KO】"
        assert row["rank"] == "54"
        assert row["main_image_url"].startswith("https://mudae.net/")

    def test_enrichment_matches_accented_names_by_key(self, clean_db):
        # Stored NFD; the catalog carries it NFC. SQLite NOCASE would miss this.
        clean_db.add_character("Hange Zoe\u0308", "", "", "")
        clean_db.upsert_catalog_characters(
            [
                {
                    "name": "Hange Zoë",
                    "name_key": ci.name_key("Hange Zoë"),
                    "series": "Attack on Titan",
                    "rank": "42",
                    "mudae_image_url": "https://mudae.net/uploads/1/a.png",
                    "pool": "wa",
                    "is_waifu": True,
                }
            ],
            scraped_at="2026-01-01T00:00:00Z",
            source_batch="test",
        )
        result = clean_db.enrich_characters_from_catalog()
        assert result["matched"] == 1
        row = clean_db.get_connection().execute(
            "SELECT series FROM characters WHERE name = ?", ("Hange Zoe\u0308",)
        ).fetchone()
        assert row["series"] == "Attack on Titan"

    def test_only_empty_does_not_overwrite(self, clean_db):
        clean_db.add_character("Ai Hoshino", "Keep me", "999", "https://old/portrait.png")
        clean_db.upsert_catalog_characters(
            self._rows(), scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )
        result = clean_db.enrich_characters_from_catalog(overwrite=False)
        assert result["unchanged"] == 1
        assert result["updated"] == 0
        row = clean_db.get_connection().execute(
            "SELECT series, rank, main_image_url FROM characters WHERE name = 'Ai Hoshino'"
        ).fetchone()
        assert (row["series"], row["rank"]) == ("Keep me", "999")

    def test_dry_run_writes_nothing(self, clean_db):
        clean_db.add_character("Ai Hoshino", "Old", "", "")
        clean_db.upsert_catalog_characters(
            self._rows(), scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )
        result = clean_db.enrich_characters_from_catalog(dry_run=True)
        assert result["updated"] == 1
        row = clean_db.get_connection().execute(
            "SELECT series FROM characters WHERE name = 'Ai Hoshino'"
        ).fetchone()
        assert row["series"] == "Old"

    def test_enrichment_never_creates_characters(self, clean_db):
        clean_db.add_character("Ai Hoshino", "", "", "")
        clean_db.upsert_catalog_characters(
            self._rows(), scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )
        result = clean_db.enrich_characters_from_catalog()
        # Nine catalog characters, one working row.
        count = clean_db.get_connection().execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        assert count == 1
        assert len(result["unmatched"]) == 0

    def test_unmatched_characters_are_reported(self, clean_db):
        clean_db.add_character("Someone Not In The Extract", "", "", "")
        clean_db.upsert_catalog_characters(
            self._rows(), scraped_at="2026-01-01T00:00:00Z", source_batch="test"
        )
        result = clean_db.enrich_characters_from_catalog()
        assert result["unmatched"] == ["Someone Not In The Extract"]
        assert result["matched"] == 0

    def test_migration_creates_the_catalog_tables(self, clean_db):
        tables = {
            row[0]
            for row in clean_db.get_connection().execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"character_catalog", "catalog_series"} <= tables


def test_module_is_importable_without_the_database():
    """The parser must not drag Flask or the database in: the CLI imports it first."""
    module = importlib.import_module("catalog_import")
    assert module.name_key("Test") == "test"
