"""The ImgChest cut-over cleanup.

Three halves can be tested without a network, an ImgChest account, or R2: parsing
the Discord export, deciding what to delete versus recover from a post listing,
and the recovery path reaching the Removed drawer. The deletion calls themselves
are thin wrappers over `imgchest_utils` and are exercised by the app's own
permanent-delete tests.

The stakes: this is the one pass that deletes from ImgChest. A bug that keeps
too much is untidy; a bug that keeps too little destroys images people are still
using in Discord, and ImgChest deletes cannot be undone.
"""

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "imgchest_cleanup", _REPO_ROOT / "scripts" / "imgchest_cleanup.py"
)
cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cleanup)


def _post(file_id, post_id=None, image_count=1):
    return {
        "slug": post_id or file_id,
        "file_id": file_id,
        "post_id": post_id or file_id,
        "image_count": image_count,
    }


class TestParseExport:
    def test_a_name_and_url_becomes_one_entry(self):
        in_use, malformed = cleanup.parse_export(
            "A2 - https://cdn.imgchest.com/files/8af1fd488aae.png\n"
        )
        assert in_use == {"https://cdn.imgchest.com/files/8af1fd488aae.png": "A2"}
        assert malformed == []

    def test_a_url_repeated_across_servers_is_kept_once(self):
        """The export is pulled from several servers, so duplicates are expected."""
        in_use, _ = cleanup.parse_export(
            "A2 - https://cdn.imgchest.com/files/x.png\n"
            "Ado - https://cdn.imgchest.com/files/x.png\n"
        )
        assert in_use == {"https://cdn.imgchest.com/files/x.png": "A2"}

    def test_a_name_containing_the_separator_still_parses(self):
        in_use, malformed = cleanup.parse_export("Foo - Bar - https://cdn/img.png\n")
        assert in_use == {"https://cdn/img.png": "Foo - Bar"}
        assert malformed == []

    def test_a_line_with_no_url_is_reported_not_dropped(self):
        _, malformed = cleanup.parse_export("just some words\nX - notaurl\n")
        assert malformed == ["just some words", "X - notaurl"]

    def test_blank_lines_are_ignored(self):
        in_use, malformed = cleanup.parse_export("\n\nA - https://cdn/x.png\n\n")
        assert len(in_use) == 1
        assert malformed == []


class TestBuildPlan:
    def test_an_image_in_no_keep_set_is_deleted(self):
        plan = cleanup.build_plan(
            [_post("aaa")], in_use={}, on_site_file_ids=set(), on_site_urls=set()
        )
        assert [d["file_id"] for d in plan["delete"]] == ["aaa"]

    def test_an_image_on_the_site_is_kept_whatever_its_state(self):
        """A removed-on-site image is still on the site, so it must not be deleted."""
        plan = cleanup.build_plan(
            [_post("aaa")], in_use={}, on_site_file_ids={"aaa"}, on_site_urls=set()
        )
        assert plan["delete"] == []
        assert "aaa" in plan["keepers"]

    def test_an_image_in_use_is_kept_even_when_the_site_lacks_it(self):
        plan = cleanup.build_plan(
            [_post("aaa")],
            in_use={"https://cdn.imgchest.com/files/aaa.png": "A2"},
            on_site_file_ids=set(),
            on_site_urls=set(),
        )
        assert plan["delete"] == []

    def test_in_use_images_the_site_lacks_are_recovered(self):
        plan = cleanup.build_plan(
            [_post("aaa")],
            in_use={"https://cdn.imgchest.com/files/aaa.png": "A2"},
            on_site_file_ids=set(),
            on_site_urls=set(),
        )
        assert plan["recover"] == [
            {"character": "A2", "url": "https://cdn.imgchest.com/files/aaa.png"}
        ]

    def test_an_in_use_image_the_site_has_is_not_recovered(self):
        plan = cleanup.build_plan(
            [_post("aaa")],
            in_use={"https://cdn.imgchest.com/files/aaa.png": "A2"},
            on_site_file_ids={"aaa"},
            on_site_urls={"https://cdn.imgchest.com/files/aaa.png"},
        )
        assert plan["recover"] == []

    def test_a_multi_image_post_is_flagged(self):
        plan = cleanup.build_plan(
            [_post("aaa", image_count=3)],
            in_use={},
            on_site_file_ids=set(),
            on_site_urls=set(),
        )
        assert [w["kind"] for w in plan["warnings"]] == ["multi_image_post"]

    def test_a_post_with_no_usable_id_is_skipped(self):
        plan = cleanup.build_plan(
            [_post(None)],
            in_use={},
            on_site_file_ids=set(),
            on_site_urls=set(),
        )
        assert plan["delete"] == []


class TestRecordPostIds:
    def test_the_listing_fills_the_post_id_column(self, clean_db):
        url = "https://cdn.imgchest.com/files/aaa.png"
        clean_db.add_custom_images("Rem", [url])
        rows = clean_db.all_custom_image_urls()
        assert cleanup.record_post_ids([_post("aaa", post_id="slug-a")], rows) == 1
        # Read back through the helper the purge path uses.
        assert clean_db.get_image_for_purge("Rem", url)["imgchest_post_id"] == "slug-a"

    def test_a_row_that_already_has_one_is_left_alone(self, clean_db):
        url = "https://cdn.imgchest.com/files/aaa.png"
        clean_db.add_custom_images("Rem", [url])
        assert clean_db.set_imgchest_post_id(url, "original")
        rows = clean_db.all_custom_image_urls()
        assert cleanup.record_post_ids([_post("aaa", post_id="other")], rows) == 0
        assert clean_db.get_image_for_purge("Rem", url)["imgchest_post_id"] == "original"


class TestRecoverRows:
    def test_recovered_images_land_in_the_removed_drawer(self, clean_db):
        """Recovered means re-added in the removed state, so staff can restore."""
        count = cleanup.recover_rows(
            [{"character": "Rem", "url": "https://cdn.imgchest.com/files/aaa.png"}],
            added_by=None,
        )
        assert count == 1
        assert clean_db.get_custom_image_rows("Rem") == []
        removed = clean_db.get_removed_for("Rem")
        assert [r["url"] for r in removed] == ["https://cdn.imgchest.com/files/aaa.png"]
        assert removed[0]["reason"] == cleanup._RECOVER_REASON

    def test_a_recover_is_idempotent(self, clean_db):
        item = [{"character": "Rem", "url": "https://cdn.imgchest.com/files/aaa.png"}]
        cleanup.recover_rows(item, added_by=None)
        assert cleanup.recover_rows(item, added_by=None) == 0
        assert len(clean_db.get_removed_for("Rem")) == 1
