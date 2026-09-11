"""Where in-flight uploads are written.

Every upload lands on disk before it is validated, converted and sent to
ImgChest. Those files were written next to the code, as `./temp_custom_<name>`,
which works from a checkout and fails on the server: the unit sets
`ProtectSystem=strict` with `ReadWritePaths=/var/lib/imgmanager`, so the working
directory `/opt/imgmanager` is read-only and every upload died with
`[Errno 30] Read-only file system`.

Nothing caught it because the tests, like a dev checkout, run somewhere
writable. So the test that matters here is the one that makes the working
directory read-only and uploads anyway.
"""

import os
import re
from pathlib import Path

import pytest

import tempfiles


class TestReserve:
    def test_it_writes_outside_the_working_directory(self, tmp_path, monkeypatch):
        """The bug in one line: a scratch path must not be CWD-relative."""
        monkeypatch.chdir(tmp_path)
        path = tempfiles.reserve("custom", "picture.png")
        try:
            assert os.path.isabs(path)
            assert Path(path).parent != Path.cwd()
        finally:
            tempfiles.discard(path)

    def test_the_file_exists_and_is_writable(self):
        path = tempfiles.reserve("custom", "a.png")
        try:
            Path(path).write_bytes(b"hello")
            assert Path(path).read_bytes() == b"hello"
        finally:
            tempfiles.discard(path)

    def test_it_keeps_the_extension_the_conversion_step_reads(self):
        path = tempfiles.reserve("custom", "photo.JPEG")
        try:
            assert path.endswith(".JPEG")
        finally:
            tempfiles.discard(path)

    def test_two_uploads_of_one_filename_do_not_collide(self):
        """The old scheme named the file after the upload, so simultaneous
        uploads of `image.png` overwrote each other and somebody got somebody
        else's picture."""
        a = tempfiles.reserve("custom", "image.png")
        b = tempfiles.reserve("custom", "image.png")
        try:
            assert a != b
            assert Path(a).exists() and Path(b).exists()
        finally:
            tempfiles.discard(a)
            tempfiles.discard(b)

    def test_a_hostile_filename_cannot_escape(self):
        path = tempfiles.reserve("custom", "../../../etc/passwd")
        try:
            assert Path(path).parent == Path(tempfiles.upload_dir())
            assert "etc" not in Path(path).name
        finally:
            tempfiles.discard(path)

    def test_no_filename_at_all_is_fine(self):
        path = tempfiles.reserve("custom")
        try:
            assert Path(path).exists()
        finally:
            tempfiles.discard(path)

    def test_an_explicit_directory_is_honoured_and_created(self, tmp_path, monkeypatch):
        target = tmp_path / "scratch" / "uploads"
        monkeypatch.setenv("UPLOAD_TMP_DIR", str(target))
        path = tempfiles.reserve("custom", "a.png")
        try:
            assert Path(path).parent == target
        finally:
            tempfiles.discard(path)


class TestDiscard:
    def test_it_removes_the_file(self):
        path = tempfiles.reserve("custom", "a.png")
        tempfiles.discard(path)
        assert not Path(path).exists()

    def test_removing_twice_is_not_an_error(self):
        path = tempfiles.reserve("custom", "a.png")
        tempfiles.discard(path)
        tempfiles.discard(path)

    def test_none_is_not_an_error(self):
        tempfiles.discard(None)


class TestAgainstAReadOnlyWorkingDirectory:
    """The production shape: code directory read-only, temp writable."""

    def test_an_upload_succeeds_with_the_working_directory_read_only(
        self, client, clean_db, tmp_path, monkeypatch
    ):
        code_dir = tmp_path / "opt"
        code_dir.mkdir()
        monkeypatch.chdir(code_dir)
        code_dir.chmod(0o555)  # r-xr-xr-x, as ProtectSystem=strict leaves it

        clean_db.add_character("Rem", "Re:Zero", "1", "")
        sent = []
        monkeypatch.setattr(
            "routes.customs.upload_to_imgchest",
            lambda path, upload_name=None: (
                sent.append(Path(path).parent),
                ("post", "https://cdn.imgchest.com/files/a.png"),
            )[1],
        )

        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (400, 600), "red").save(buf, "PNG")
        buf.seek(0)

        try:
            response = client.post(
                "/api/custom-image",
                data={"character_name": "Rem", "files": (buf, "picture.png")},
                content_type="multipart/form-data",
            )
        finally:
            code_dir.chmod(0o755)

        body = response.get_json()
        assert response.status_code == 200, body
        # The old code would have raised OSError here rather than uploading.
        assert sent and sent[0] != code_dir

    def test_the_error_that_was_reported_is_gone(self, tmp_path, monkeypatch):
        """`[Errno 30] Read-only file system: './temp_custom_...'`"""
        locked = tmp_path / "readonly"
        locked.mkdir()
        monkeypatch.chdir(locked)
        locked.chmod(0o555)
        try:
            with pytest.raises(OSError, match=re.compile("Read-only|Permission")):
                Path("./temp_custom_probe.png").write_bytes(b"x")
            path = tempfiles.reserve("custom", "probe.png")
            Path(path).write_bytes(b"x")
            tempfiles.discard(path)
        finally:
            locked.chmod(0o755)
