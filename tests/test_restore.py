"""Tests for the restore module (single-file and full-profile restore).

``restore.py`` opens and closes its own connection per call, so the
in-memory ``:memory:`` pattern used elsewhere (one shared connection that is
never closed by the tested function) doesn't survive multiple calls. These
tests seed a file-backed DB and monkeypatch ``database.open_connection`` to
return a *fresh* connection to that same file each time, mirroring production.
"""

import pytest
from pathlib import Path

import database
from database import open_connection, update_file_state
from restore import (
    find_backup_path,
    restore_all_files,
    restore_file,
)


def _shared_db(tmp_path):
    """Create a file-backed DB and return (conn, db_path)."""
    db_path = tmp_path / "state.db"
    return open_connection(db_path=db_path), db_path


def _patch_open(monkeypatch, db_path):
    """Route database.open_connection to a fresh connection on the same file."""
    monkeypatch.setattr(
        database,
        "open_connection",
        lambda *a, **k: open_connection(db_path=db_path),
    )


def _seed(conn, tmp_path, profile="p"):
    """Create real backup files + DB rows; return (a, b, ba, bb) paths."""
    bk = tmp_path / "bk"
    bk.mkdir()
    a = tmp_path / "a.txt"
    a.write_text("alpha")
    ba = bk / "a.txt"
    ba.write_text("alpha")
    b = tmp_path / "b.txt"
    b.write_text("beta")
    bb = bk / "b.txt"
    bb.write_text("beta")
    update_file_state(conn, profile, str(a), str(ba), "ha", a.stat().st_size)
    update_file_state(conn, profile, str(b), str(bb), "hb", b.stat().st_size)
    return a, b, ba, bb


class TestFindBackupPath:
    def test_finds_backup_path(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, _, ba, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        assert find_backup_path(str(a)) == str(ba)

    def test_returns_none_when_not_found(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        _patch_open(monkeypatch, db_path)

        assert find_backup_path("/no/such/file.txt") is None

    def test_filters_by_profile(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        bk = tmp_path / "bk"
        bk.mkdir()
        a = tmp_path / "a.txt"
        a.write_text("x")
        bp = bk / "p.txt"
        bp.write_text("p")
        bo = bk / "o.txt"
        bo.write_text("o")
        update_file_state(conn, "p", str(a), str(bp), "h", 1)
        update_file_state(conn, "other", str(a), str(bo), "h", 1)
        _patch_open(monkeypatch, db_path)

        assert find_backup_path(str(a), "p") == str(bp)
        assert find_backup_path(str(a), "other") == str(bo)


class TestRestoreFile:
    def test_restores_to_original_location(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, _, _, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        restored = restore_file(str(a))

        assert restored == Path(str(a))
        assert a.read_text() == "alpha"

    def test_restores_to_custom_location(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, _, _, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        dest = tmp_path / "restored" / "a.txt"
        restored = restore_file(str(a), destination=str(dest))

        assert restored == dest
        assert dest.is_file()
        assert dest.read_text() == "alpha"

    def test_creates_parent_directories(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, _, _, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        dest = tmp_path / "deep" / "nested" / "custom.txt"
        restored = restore_file(str(a), destination=str(dest))

        assert restored == dest
        assert dest.is_file()

    def test_raises_when_backup_not_found(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        _patch_open(monkeypatch, db_path)

        with pytest.raises(FileNotFoundError):
            restore_file("/no/such/file.txt")

    def test_raises_when_backup_file_missing(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        # Row exists but the backup file was deleted.
        missing_bk = tmp_path / "bk" / "gone.txt"
        update_file_state(conn, "p", str(tmp_path / "src.txt"), str(missing_bk), "h", 5)
        _patch_open(monkeypatch, db_path)

        with pytest.raises(FileNotFoundError):
            restore_file(str(tmp_path / "src.txt"))


class TestRestoreAllFiles:
    def test_restores_all_files_in_profile(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, b, _, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        results = restore_all_files("p")

        assert results["restored"] == 2
        assert results["failed"] == []
        assert a.read_text() == "alpha"
        assert b.read_text() == "beta"

    def test_restores_to_custom_directory_preserving_tree(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        a, b, _, _ = _seed(conn, tmp_path)
        _patch_open(monkeypatch, db_path)

        dest_root = tmp_path / "out"
        results = restore_all_files("p", destination=str(dest_root))

        assert results["restored"] == 2
        rel_a = Path(str(a)).relative_to(Path(str(a)).anchor)
        rel_b = Path(str(b)).relative_to(Path(str(b)).anchor)
        assert (dest_root / rel_a).is_file()
        assert (dest_root / rel_b).is_file()

    def test_continues_on_individual_file_errors(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        _seed(conn, tmp_path)  # one good row set
        # Add a row whose backup file doesn't exist.
        missing_bk = tmp_path / "bk" / "gone.txt"
        update_file_state(conn, "p", str(tmp_path / "src.txt"), str(missing_bk), "h", 5)
        _patch_open(monkeypatch, db_path)

        results = restore_all_files("p")

        assert results["restored"] == 2
        assert len(results["failed"]) == 1
        assert results["failed"][0]["path"] == str(tmp_path / "src.txt")

    def test_raises_when_profile_not_found(self, monkeypatch, tmp_path):
        conn, db_path = _shared_db(tmp_path)
        _patch_open(monkeypatch, db_path)

        with pytest.raises(ValueError):
            restore_all_files("nope")
