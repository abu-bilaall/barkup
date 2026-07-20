from barkup.barkup import barkup_file, run_local_barkup
from barkup.compression import decompress_file
from barkup.database import get_file_state, open_connection
from barkup.exclude_patterns import FileToBackup


class TestBarkupFileFromFile:
    """Test barkup_file when source is a single file (source_is_dir=False)."""

    def test_copies_file_to_destination(self, tmp_path):
        # Arrange
        src = tmp_path / "file.txt"
        src.write_text("woof")
        dest = tmp_path / "backup"

        # Act
        result = barkup_file(src, src, dest, source_is_dir=False)

        # Assert
        assert result.exists()
        assert result.read_text() == "woof"

    def test_preserves_filename(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("woof")
        dest = tmp_path / "backup"

        result = barkup_file(src, src, dest, source_is_dir=False)

        assert result.name == "file.txt"

    def test_overwrites_existing_file(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("new_woof")
        dest = tmp_path / "backup"
        dest.mkdir()
        (dest / "file.txt").write_text("old_woof")

        result = barkup_file(src, src, dest, source_is_dir=False)

        assert result.read_text() == "new_woof"

    def test_creates_destination_directories(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("woof")
        dest = tmp_path / "backup" / "nested" / "deep"

        result = barkup_file(src, src, dest, source_is_dir=False)

        assert result.exists()


class TestBarkupFileFromDirectory:
    """Test barkup_file when source is a directory (source_is_dir=True).

    When source_is_dir=True, the file's relative path from source_root
    is preserved under a directory named after the source_root.
    """

    def test_preserves_relative_path(self, tmp_path):
        # Arrange: file inside a source directory
        src_dir = tmp_path / "docs"
        src_dir.mkdir()
        src_file = src_dir / "readme.md"
        src_file.write_text("hello")
        dest = tmp_path / "backup"

        # Act
        result = barkup_file(src_file, src_dir, dest, source_is_dir=True)

        # Assert: file lands at backup/docs/readme.md
        assert result == dest / "docs" / "readme.md"
        assert result.read_text() == "hello"

    def test_preserves_nested_structure(self, tmp_path):
        src_dir = tmp_path / "project"
        sub = src_dir / "sub" / "deep"
        sub.mkdir(parents=True)
        src_file = sub / "data.txt"
        src_file.write_text("nested")
        dest = tmp_path / "backup"

        result = barkup_file(src_file, src_dir, dest, source_is_dir=True)

        assert result == dest / "project" / "sub" / "deep" / "data.txt"
        assert result.read_text() == "nested"

    def test_multiple_files_from_same_source(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        file_a = src_dir / "a.txt"
        file_b = src_dir / "b.txt"
        file_a.write_text("A")
        file_b.write_text("B")
        dest = tmp_path / "backup"

        barkup_file(file_a, src_dir, dest, source_is_dir=True)
        barkup_file(file_b, src_dir, dest, source_is_dir=True)

        assert (dest / "src" / "a.txt").read_text() == "A"
        assert (dest / "src" / "b.txt").read_text() == "B"


class TestBarkupFileCompression:
    """Test barkup_file's compress flag."""

    def test_compress_creates_sidecar_zip(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("woof")
        dest = tmp_path / "backup"

        result = barkup_file(src, src, dest, source_is_dir=False, compress=True)

        assert result.name == "file.txt.zip"
        assert result.is_file()
        out = tmp_path / "restored.txt"
        decompress_file(result, out)
        assert out.read_text() == "woof"

    def test_compress_skips_already_compressed(self, tmp_path):
        src = tmp_path / "a.zip"
        src.write_bytes(b"PK\x03\x04fake")
        dest = tmp_path / "backup"

        result = barkup_file(src, src, dest, source_is_dir=False, compress=True)

        # .zip sources are skipped, so the original is copied verbatim.
        assert result.name == "a.zip"
        assert result.read_bytes() == b"PK\x03\x04fake"

    def test_compress_false_copies(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("woof")
        dest = tmp_path / "backup"

        result = barkup_file(src, src, dest, source_is_dir=False, compress=False)

        assert result.name == "file.txt"
        assert result.read_text() == "woof"


class TestRunLocalBarkupCompression:
    """Test that run_local_barkup honours the compression flag + DB flag."""

    def _state(self, conn, path, profile="p"):
        row = get_file_state(conn, str(path), profile)
        conn.commit()
        return row

    def test_compresses_plain_file_and_records_flag(self, tmp_path):
        src_dir = tmp_path / "docs"
        src_dir.mkdir()
        plain = src_dir / "notes.txt"
        plain.write_text("hello")
        already = src_dir / "pic.jpg"
        already.write_text("imgbytes")
        dest = tmp_path / "backup"
        conn = open_connection(db_path=tmp_path / "state.db")
        try:
            run_local_barkup(
                [
                    FileToBackup(path=plain, source=src_dir, source_is_dir=True),
                    FileToBackup(path=already, source=src_dir, source_is_dir=True),
                ],
                dest,
                conn,
                "p",
                compression=True,
            )
            plain_state = self._state(conn, plain)
            jpg_state = self._state(conn, already)
        finally:
            conn.close()

        assert plain_state["backup_path"].endswith(".zip")
        assert plain_state["compressed"] == 1
        assert not jpg_state["backup_path"].endswith(".zip")
        assert jpg_state["compressed"] == 0

    def test_no_compression_when_disabled(self, tmp_path):
        src_dir = tmp_path / "docs"
        src_dir.mkdir()
        plain = src_dir / "notes.txt"
        plain.write_text("hello")
        dest = tmp_path / "backup"
        conn = open_connection(db_path=tmp_path / "state.db")
        try:
            run_local_barkup(
                [FileToBackup(path=plain, source=src_dir, source_is_dir=True)],
                dest,
                conn,
                "p",
                compression=False,
            )
            state = self._state(conn, plain)
        finally:
            conn.close()

        assert not state["backup_path"].endswith(".zip")
        assert state["compressed"] == 0


import pytest
from pathlib import Path

from barkup import database
from barkup.barkup import run_barkup


class TestRunBarkupBehavior:
    @staticmethod
    def _write_config(tmp_path, sources, destination, dry_run=False):
        cfg = tmp_path / "barkup.config.toml"
        src = ", ".join(f'"{s}"' for s in sources)
        cfg.write_text(
            "[general]\n"
            'profile_name = "default"\n'
            "dry_run = " + ("true" if dry_run else "false") + "\n"
            f"sources = [{src}]\n"
            "compression = false\n"
            "exclude = []\n"
            "[local]\n"
            f'destination = "{destination}"\n'
        )
        return cfg

    def test_dry_run_does_not_copy(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        dest = tmp_path / "dest"
        cfg = self._write_config(tmp_path, [str(src)], str(dest), dry_run=True)
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=Path(":memory:")),
        )
        stats = run_barkup(cli_path=cfg, profile_name="default", skip_confirm=True)
        assert stats["dry_run"] is True
        assert stats["files_backed_up"] == 0
        assert not dest.exists()

    def test_raises_when_sources_empty(self, tmp_path, monkeypatch):
        dest = tmp_path / "dest"
        cfg = self._write_config(tmp_path, [], str(dest))
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=Path(":memory:")),
        )
        with pytest.raises(ValueError):
            run_barkup(cli_path=cfg, profile_name="default", skip_confirm=True)

    def test_raises_when_destination_empty(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.mkdir()
        cfg = self._write_config(tmp_path, [str(src)], "")
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=Path(":memory:")),
        )
        with pytest.raises(ValueError):
            run_barkup(cli_path=cfg, profile_name="default", skip_confirm=True)

    def test_raises_when_destination_inside_source(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.mkdir()
        cfg = self._write_config(tmp_path, [str(src)], str(src))
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=Path(":memory:")),
        )
        with pytest.raises(ValueError):
            run_barkup(cli_path=cfg, profile_name="default", skip_confirm=True)
