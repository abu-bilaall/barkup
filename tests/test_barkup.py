import pytest
from pathlib import Path
from barkup import barkup_file


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