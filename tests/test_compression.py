"""Tests for the compression module (ZIP helpers)."""

import zipfile

import pytest

from barkup.compression import (
    compress_file,
    decompress_file,
    should_compress,
)


class TestShouldCompress:
    def test_skips_compressed_extensions(self, tmp_path):
        for ext in [".zip", ".gz", ".jpg", ".png", ".mp3", ".mp4", ".7z", ".rar"]:
            assert should_compress(tmp_path / f"file{ext}") is False

    def test_compresses_plain_extensions(self, tmp_path):
        for ext in [".txt", ".md", ".csv", ".py", ".json", ".log"]:
            assert should_compress(tmp_path / f"file{ext}") is True

    def test_case_insensitive(self, tmp_path):
        assert should_compress(tmp_path / "PHOTO.JPG") is False
        assert should_compress(tmp_path / "Notes.TXT") is True

    def test_unknown_extension_is_compressed(self, tmp_path):
        assert should_compress(tmp_path / "data") is True


class TestCompressFile:
    def test_creates_zip_with_original_arcname(self, tmp_path):
        src = tmp_path / "notes.txt"
        src.write_text("secret content")
        dest_zip = tmp_path / "out" / "notes.txt.zip"

        result = compress_file(src, dest_zip)

        assert result == dest_zip
        assert dest_zip.is_file()
        with zipfile.ZipFile(dest_zip) as zf:
            assert zf.namelist() == ["notes.txt"]

    def test_round_trip_content(self, tmp_path):
        src = tmp_path / "data.bin"
        src.write_bytes(b"\x00\x01\x02binary")
        dest_zip = tmp_path / "archive.zip"

        compress_file(src, dest_zip)

        extracted = tmp_path / "extracted.bin"
        decompress_file(dest_zip, extracted)
        assert extracted.read_bytes() == b"\x00\x01\x02binary"


class TestDecompressFile:
    def test_extracts_to_given_path(self, tmp_path):
        src = tmp_path / "report.md"
        src.write_text("# report")
        dest_zip = tmp_path / "report.md.zip"
        compress_file(src, dest_zip)

        out = tmp_path / "restored" / "report.md"
        result = decompress_file(dest_zip, out)

        assert result == out
        assert out.read_text() == "# report"

    def test_empty_archive_raises(self, tmp_path):
        empty = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty, "w"):
            pass
        with pytest.raises(ValueError):
            decompress_file(empty, tmp_path / "x")
