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
import json
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

    def test_a_non_imgchest_url_is_foreign_not_recoverable(self):
        """The app has only ever uploaded to ImgChest.

        An Imgur URL in the export is somebody else's upload used in Discord.
        Recovering it would put a foreign image on the site, under a row that can
        never be permanently deleted here because this account has no post for
        it. It is reported so the operator can see it, and never recovered.
        """
        plan = cleanup.build_plan(
            [],
            in_use={
                "https://cdn.imgchest.com/files/aaa.png": "Mine",
                "https://i.imgur.com/zzz.png": "Theirs",
            },
            on_site_file_ids=set(),
            on_site_urls=set(),
        )
        assert plan["recover"] == [
            {"character": "Mine", "url": "https://cdn.imgchest.com/files/aaa.png"}
        ]
        assert plan["foreign"] == [
            {"character": "Theirs", "url": "https://i.imgur.com/zzz.png"}
        ]

    def test_a_foreign_url_present_on_the_site_is_still_dropped(self):
        # Already on the site means nothing to do, whichever host it is.
        plan = cleanup.build_plan(
            [],
            in_use={"https://i.imgur.com/zzz.png": "Theirs"},
            on_site_file_ids=set(),
            on_site_urls={"https://i.imgur.com/zzz.png"},
        )
        assert plan["recover"] == []
        assert plan["foreign"] == []

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
    def test_record_post_ids_sees_rows_added_after_the_first_read(self, clean_db):
        """The step must re-read, or recovered rows are left without a post id.

        `main` reads every URL once at the start, then recovers -- which adds
        1,222 rows. Passing that first read to `record_post_ids` skips them, and
        a row with no post id can never be permanently deleted through the app.
        """
        # Before recovery: the URL is not on the site, so the first read had nothing.
        first_read = clean_db.all_custom_image_urls()
        assert first_read == []

        cleanup.recover_rows(
            [{"character": "Rem", "url": "https://cdn.imgchest.com/files/aaa.png"}],
            added_by=None,
        )
        posts = [_post("aaa", post_id="slug-aaa")]

        # The stale list misses it; a fresh read does not.
        assert cleanup.record_post_ids(posts, first_read) == 0
        assert cleanup.record_post_ids(posts, clean_db.all_custom_image_urls()) == 1
        conn = clean_db.get_connection()
        assert (
            conn.execute("SELECT imgchest_post_id FROM custom_images").fetchone()[0] == "slug-aaa"
        )

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

    def test_a_recover_is_not_attributed_to_anyone(self, clean_db):
        """No person made this call, so `removed_by` must stay NULL.

        Passing an empty string instead is not the same thing: it is non-NULL, so
        the row joins to an identity and lands in that identity's moderation
        history under a generated pseudonym. That shipped once, to 1,222 rows,
        which read as removed by "Gilded Wigeon".
        """
        cleanup.recover_rows(
            [{"character": "Rem", "url": "https://cdn.imgchest.com/files/aaa.png"}],
            added_by=None,
        )
        conn = clean_db.get_connection()
        row = conn.execute("SELECT added_by, removed_by FROM custom_images").fetchone()
        assert row["added_by"] is None
        assert row["removed_by"] is None
        # And no identity was minted for the empty string.
        assert (
            conn.execute("SELECT COUNT(*) FROM identities WHERE id = ''").fetchone()[0] == 0
        )

    def test_the_recovered_rows_stay_out_of_moderation_history(self, clean_db):
        # Moderation history is built from `removed_by IS NOT NULL`, so a NULL
        # actor is what keeps a script action from reading as a person's.
        cleanup.recover_rows(
            [{"character": "Rem", "url": "https://cdn.imgchest.com/files/aaa.png"}],
            added_by=None,
        )
        conn = clean_db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM custom_images WHERE removed_by IS NOT NULL").fetchone()[0] == 0


class TestDeleteFingerprint:
    """The guard on `--execute`.

    Every run re-lists the account and rebuilds the plan, so the execute run does
    not use the reviewed plan unless something checks. This is that check: a
    digest of *which* files would be deleted, written into the preview, compared
    before anything is removed.
    """

    def test_is_stable_across_ordering_and_cosmetic_change(self):
        # Order comes from the listing and can vary between runs; only the set
        # that would be deleted matters.
        a = [{"file_id": "a", "url": "x"}, {"file_id": "b", "url": "y"}]
        b = [{"file_id": "b", "url": "other"}, {"file_id": "a", "url": "z"}]
        assert cleanup.delete_fingerprint(a) == cleanup.delete_fingerprint(b)

    def test_changes_when_a_candidate_is_added(self):
        before = cleanup.delete_fingerprint([{"file_id": "a"}])
        after = cleanup.delete_fingerprint([{"file_id": "a"}, {"file_id": "b"}])
        assert before != after

    def test_changes_when_a_candidate_is_removed(self):
        # A post already deleted by hand is no longer a candidate. The plan the
        # operator reviewed is no longer this one.
        before = cleanup.delete_fingerprint([{"file_id": "a"}, {"file_id": "b"}])
        after = cleanup.delete_fingerprint([{"file_id": "b"}])
        assert before != after

    def test_an_empty_plan_is_a_valid_fingerprint(self):
        assert cleanup.delete_fingerprint([]) == cleanup.delete_fingerprint([])


class TestDescribeDeleteDiff:
    def test_names_what_was_added_and_removed(self):
        lines = cleanup.describe_delete_diff([{"file_id": "a"}], [{"file_id": "b"}])
        assert any("b" in line and "newly in line" in line for line in lines)
        assert any("a" in line and "no longer a candidate" in line for line in lines)

    def test_says_nothing_extra_when_the_sets_match(self):
        lines = cleanup.describe_delete_diff([{"file_id": "a"}], [{"file_id": "a"}])
        assert len(lines) == 1
        assert "newly" not in lines[0]


class TestReadPreviousPreview:
    def test_returns_none_when_there_is_no_file(self, tmp_path):
        assert cleanup.read_previous_preview(tmp_path / "absent.json") is None

    def test_returns_none_rather_than_raising_on_junk(self, tmp_path):
        # A guard rail, not a parser: refusing to run because a previous preview
        # was truncated would be its own failure.
        junk = tmp_path / "junk.json"
        junk.write_text("{ not json", encoding="utf-8")
        assert cleanup.read_previous_preview(junk) is None

    def test_reads_back_a_written_preview(self, tmp_path):
        path = tmp_path / "preview.json"
        path.write_text('{"fingerprint": "abc", "delete": []}', encoding="utf-8")
        assert cleanup.read_previous_preview(path)["fingerprint"] == "abc"


class TestExecuteGuard:
    """The guard as wired into `main`, not just its helpers.

    This is the part that is easy to get wrong: the fresh preview must be written
    only after the comparison, or a refusal destroys the very plan it refused to
    vouch for.
    """

    def _run(self, monkeypatch, tmp_path, listing, argv, rows=None):
        export = tmp_path / "export.txt"
        export.write_text("Rem - https://cdn.imgchest.com/files/keep.png\n", encoding="utf-8")
        monkeypatch.setenv("IMGCHEST_API_KEY", "test-key")
        monkeypatch.setattr(cleanup, "list_posts", lambda username, token: listing)
        # A cleanup plans against the site, so the database read must not be empty
        # unless the test is about exactly that.
        default_rows = [{"url": "https://cdn.imgchest.com/files/keep.png"}]
        monkeypatch.setattr(
            cleanup,
            "db",
            type(
                "D",
                (),
                {
                    "all_custom_image_urls": lambda self: default_rows if rows is None else rows,
                    "database_path": lambda self: "/fake/imgmanager.db",
                },
            )(),
        )
        monkeypatch.setattr(cleanup, "record_post_ids", lambda posts, rows: 0)
        monkeypatch.setattr(cleanup, "recover_rows", lambda recover, added_by=None: 0)
        deleted = []
        monkeypatch.setattr(cleanup, "delete_candidate", lambda c: deleted.append(c["file_id"]))
        monkeypatch.setattr(cleanup, "_DELETE_DELAY", 0)
        monkeypatch.setattr(
            "sys.argv",
            [
                "cleanup",
                "--username",
                "u",
                "--export",
                str(export),
                "--preview",
                str(tmp_path / "p.json"),
                *argv,
            ],
        )
        code = cleanup.main()
        # A refused run writes no preview, which is the point of refusing.
        path = tmp_path / "p.json"
        preview = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return code, preview, deleted

    def test_execute_refuses_when_the_plan_moved(self, monkeypatch, tmp_path):
        # Review a plan with one candidate, then the account gains another.
        self._run(monkeypatch, tmp_path, [_post("doomed")], [])
        code, preview, deleted = self._run(
            monkeypatch, tmp_path, [_post("doomed"), _post("newlydoomed")], ["--execute"]
        )

        assert code == 1, "an execute that no longer matches the review must not proceed"
        assert deleted == [], "nothing may be deleted when the guard trips"
        # The reviewed preview is intact, and the proposed one is beside it.
        assert len(preview["delete"]) == 1
        proposed = json.loads((tmp_path / "p.proposed.json").read_text(encoding="utf-8"))
        assert len(proposed["delete"]) == 2

    def test_execute_proceeds_when_the_plan_is_unchanged(self, monkeypatch, tmp_path):
        self._run(monkeypatch, tmp_path, [_post("doomed")], [])
        code, preview, deleted = self._run(monkeypatch, tmp_path, [_post("doomed")], ["--execute"])
        assert code == 0
        assert deleted == ["doomed"]
        assert preview["executed"] is True

    def test_force_accepts_a_moved_plan(self, monkeypatch, tmp_path):
        self._run(monkeypatch, tmp_path, [_post("doomed")], [])
        code, _, deleted = self._run(
            monkeypatch, tmp_path, [_post("doomed"), _post("newlydoomed")], ["--execute", "--force"]
        )
        assert code == 0
        assert sorted(deleted) == ["doomed", "newlydoomed"]

    def test_the_fingerprint_is_written_into_the_preview(self, monkeypatch, tmp_path):
        _, preview, _ = self._run(monkeypatch, tmp_path, [_post("doomed")], [])
        assert preview["fingerprint"] == cleanup.delete_fingerprint(preview["delete"])

    def test_an_empty_database_is_refused(self, monkeypatch, tmp_path):
        """Losing DATABASE_PATH silently plans against an empty site.

        `db` falls back to ./data/imgmanager.db and creates it, so the run reads
        no images, keeps only what the export names, and reports a delete list
        thousands too long -- with nothing in the output saying so. Refusing is
        the only safe answer, because there is no legitimate cleanup against an
        empty library.
        """
        code, preview, deleted = self._run(monkeypatch, tmp_path, [_post("doomed")], [], rows=[])
        assert code == 1
        assert deleted == []
        # Nothing was written, so no preview for a later run to be judged against.
        assert preview is None


class TestRecoverLiveness:
    """Dead URLs must not be recovered back onto the site.

    The export records what was pasted into Discord, not what is still hosted.
    Re-adding a dead one puts a broken image on the site for staff to remove
    again, which is worse than leaving the export alone.
    """

    def _response(self, status=200, content_type="image/png"):
        class _R:
            status_code = status
            headers = {"Content-Type": content_type}

            def close(self):
                pass

        return _R()

    def test_a_served_image_is_alive(self, monkeypatch):
        monkeypatch.setattr(cleanup.requests, "get", lambda *a, **k: self._response())
        assert cleanup.url_is_alive("https://cdn.imgchest.com/files/aaa.png") is True

    def test_a_404_is_not_alive(self, monkeypatch):
        monkeypatch.setattr(
            cleanup.requests, "get", lambda *a, **k: self._response(404, "text/html")
        )
        assert cleanup.url_is_alive("https://cdn.imgchest.com/files/gone.png") is False

    def test_a_403_is_not_alive_and_that_is_the_point(self, monkeypatch):
        # ImgChest answers 403 to a request without a browser User-Agent, so the
        # probe has to send one or every image reads as dead. This pins that the
        # headers are passed, not just that a 403 means dead.
        seen = {}

        def fake_get(url, headers=None, **kwargs):
            seen["headers"] = headers or {}
            return self._response(200)

        monkeypatch.setattr(cleanup.requests, "get", fake_get)
        cleanup.url_is_alive("https://cdn.imgchest.com/files/aaa.png")
        assert "User-Agent" in seen["headers"]
        assert "Mozilla" in seen["headers"]["User-Agent"]

    def test_a_non_image_response_is_not_alive(self, monkeypatch):
        # An HTML error page served as 200 is not an image.
        monkeypatch.setattr(
            cleanup.requests, "get", lambda *a, **k: self._response(200, "text/html")
        )
        assert cleanup.url_is_alive("https://cdn.imgchest.com/files/aaa.png") is False

    def test_a_network_failure_reads_as_not_alive(self, monkeypatch):
        def boom(*a, **k):
            raise cleanup.requests.RequestException("nope")

        monkeypatch.setattr(cleanup.requests, "get", boom)
        assert cleanup.url_is_alive("https://cdn.imgchest.com/files/aaa.png") is False

    def test_partition_splits_alive_dead_and_foreign(self, monkeypatch):
        monkeypatch.setattr(cleanup.time, "sleep", lambda _s: None)
        monkeypatch.setattr(
            cleanup,
            "url_is_alive",
            lambda url: "dead" not in url,
        )
        parted = cleanup.partition_recover(
            {
                "https://cdn.imgchest.com/files/alive.png": "A",
                "https://cdn.imgchest.com/files/dead.png": "B",
                "https://i.imgur.com/zzz.png": "C",
            },
            on_site_urls=set(),
        )
        assert [e["character"] for e in parted["recover"]] == ["A"]
        assert [e["character"] for e in parted["dead"]] == ["B"]
        assert [e["character"] for e in parted["foreign"]] == ["C"]

    def test_partition_without_verify_keeps_everything_imgchest(self, monkeypatch):
        monkeypatch.setattr(cleanup.time, "sleep", lambda _s: None)

        def should_not_run(url):  # pragma: no cover - asserts by not being used
            raise AssertionError("the probe ran despite verify=False")

        monkeypatch.setattr(cleanup, "url_is_alive", should_not_run)
        parted = cleanup.partition_recover(
            {"https://cdn.imgchest.com/files/maybe0dead.png": "A"},
            on_site_urls=set(),
            verify=False,
        )
        assert [e["character"] for e in parted["recover"]] == ["A"]
        assert parted["dead"] == []

    def test_an_on_site_url_is_reported_as_nothing(self, monkeypatch):
        monkeypatch.setattr(cleanup.time, "sleep", lambda _s: None)
        monkeypatch.setattr(cleanup, "url_is_alive", lambda url: True)
        url = "https://cdn.imgchest.com/files/present.png"
        parted = cleanup.partition_recover({url: "A"}, on_site_urls={url})
        assert parted == {"recover": [], "dead": [], "foreign": []}
