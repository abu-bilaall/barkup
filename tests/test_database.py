import sqlite3
from pathlib import Path

from barkup.database import (
    open_connection,
    initialize_database,
    get_file_state,
    has_file_changed,
    update_file_state,
    close_connection,
    get_backup_stats,
    format_size,
    get_all_backups,
    verify_backup,
    calculate_file_hash,
)


def _memory_connection() -> sqlite3.Connection:
    """Open an in-memory database for testing (no disk I/O)."""
    return open_connection(db_path=Path(":memory:"))


class TestInitializeDatabase:
    def test_creates_backups_table(self):
        conn = _memory_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backups'"
        )
        assert cursor.fetchone() is not None
        close_connection(conn)

    def test_idempotent(self):
        """Calling initialize_database twice doesn't error."""
        conn = _memory_connection()
        initialize_database(conn)  # second call
        close_connection(conn)


class TestUpdateAndGetFileState:
    def test_insert_and_retrieve(self):
        conn = _memory_connection()

        update_file_state(
            conn,
            profile="default",
            original_path="/home/user/doc.txt",
            backup_path="/backups/doc.txt",
            file_hash="abc123",
            size=1024,
        )

        state = get_file_state(conn, "/home/user/doc.txt", "default")

        assert state is not None
        assert state["original_path"] == "/home/user/doc.txt"
        assert state["backup_path"] == "/backups/doc.txt"
        assert state["hash"] == "abc123"
        assert state["size"] == 1024
        assert state["last_backup"] is not None
        close_connection(conn)

    def test_upsert_updates_existing(self):
        conn = _memory_connection()

        update_file_state(conn, "default", "/doc.txt", "/old.txt", "old_hash", 100)
        update_file_state(conn, "default", "/doc.txt", "/new.txt", "new_hash", 200)

        state = get_file_state(conn, "/doc.txt", "default")
        assert state is not None

        assert state["backup_path"] == "/new.txt"
        assert state["hash"] == "new_hash"
        assert state["size"] == 200
        close_connection(conn)

    def test_returns_none_for_unknown_file(self):
        conn = _memory_connection()

        state = get_file_state(conn, "/nonexistent.txt", "default")

        assert state is None
        close_connection(conn)

    def test_profiles_are_isolated(self):
        conn = _memory_connection()

        update_file_state(conn, "work", "/doc.txt", "/b1.txt", "hash1", 100)
        update_file_state(conn, "personal", "/doc.txt", "/b2.txt", "hash2", 200)

        work_state = get_file_state(conn, "/doc.txt", "work")
        personal_state = get_file_state(conn, "/doc.txt", "personal")
        assert work_state is not None
        assert personal_state is not None

        assert work_state["hash"] == "hash1"
        close_connection(conn)


class TestHasFileChanged:
    def test_new_file_returns_true(self, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "new.txt"
        f.write_text("hello")

        assert has_file_changed(conn, f, "default") is True
        close_connection(conn)

    def test_unchanged_file_returns_false(self, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "stable.txt"
        f.write_text("content")

        # simulate a previous backup
        from barkup.hashing import calculate_file_hash

        update_file_state(
            conn,
            "default",
            str(f),
            "/backup/stable.txt",
            calculate_file_hash(f),
            f.stat().st_size,
        )

        assert has_file_changed(conn, f, "default") is False
        close_connection(conn)

    def test_modified_file_returns_true(self, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "changing.txt"
        f.write_text("original")

        from barkup.hashing import calculate_file_hash

        update_file_state(
            conn,
            "default",
            str(f),
            "/backup/changing.txt",
            calculate_file_hash(f),
            f.stat().st_size,
        )

        # modify the file
        f.write_text("modified")

        assert has_file_changed(conn, f, "default") is True
        close_connection(conn)


class TestListBackups:
    def test_returns_all_rows_when_profile_is_none(self):
        from barkup.database import list_backups

        conn = _memory_connection()
        update_file_state(conn, "default", "/a.txt", "/b/a.txt", "h1", 10)
        update_file_state(conn, "docs", "/b.txt", "/b/b.txt", "h2", 20)

        rows = list_backups(conn, None)
        assert len(rows) == 2
        assert {row["profile"] for row in rows} == {"default", "docs"}
        close_connection(conn)

    def test_omitting_profile_lists_all_rows(self):
        from barkup.database import list_backups

        conn = _memory_connection()
        update_file_state(conn, "p1", "/x.txt", "/b/x.txt", "hx", 1)
        update_file_state(conn, "p2", "/y.txt", "/b/y.txt", "hy", 2)

        rows = list_backups(conn)
        assert len(rows) == 2
        close_connection(conn)

    def test_filters_by_profile(self):
        from barkup.database import list_backups

        conn = _memory_connection()
        update_file_state(conn, "default", "/a.txt", "/b/a.txt", "h1", 10)
        update_file_state(conn, "docs", "/b.txt", "/b/b.txt", "h2", 20)

        rows = list_backups(conn, "docs")
        assert len(rows) == 1
        assert rows[0]["profile"] == "docs"
        assert rows[0]["original_path"] == "/b.txt"
        close_connection(conn)

    def test_respects_profile_isolation(self):
        from barkup.database import list_backups

        conn = _memory_connection()
        update_file_state(conn, "work", "/shared.txt", "/b/w.txt", "hw", 1)
        update_file_state(conn, "home", "/shared.txt", "/b/h.txt", "hh", 2)

        work_rows = list_backups(conn, "work")
        home_rows = list_backups(conn, "home")
        assert len(work_rows) == 1 and work_rows[0]["profile"] == "work"
        assert len(home_rows) == 1 and home_rows[0]["profile"] == "home"
        close_connection(conn)


class TestGetBackupStats:
    def test_empty_db_returns_empty_dict(self):
        conn = _memory_connection()
        stats = get_backup_stats(conn)
        assert stats == {}
        close_connection(conn)

    def test_single_profile_aggregates(self):
        conn = _memory_connection()
        update_file_state(conn, "default", "/a.txt", "/b/a.txt", "ha", 100)
        update_file_state(conn, "default", "/b.txt", "/b/b.txt", "hb", 200)

        stats = get_backup_stats(conn)
        assert len(stats) == 1
        assert "default" in stats
        assert stats["default"]["file_count"] == 2
        assert stats["default"]["total_size"] == 300
        assert stats["default"]["last_backup"] is not None
        close_connection(conn)

    def test_multiple_profiles(self):
        conn = _memory_connection()
        update_file_state(conn, "work", "/w1.txt", "/b/w1.txt", "hw1", 500)
        update_file_state(conn, "work", "/w2.txt", "/b/w2.txt", "hw2", 600)
        update_file_state(conn, "home", "/h1.txt", "/b/h1.txt", "hh1", 300)

        stats = get_backup_stats(conn)
        assert len(stats) == 2
        assert stats["work"]["file_count"] == 2
        assert stats["work"]["total_size"] == 1100
        assert stats["home"]["file_count"] == 1
        assert stats["home"]["total_size"] == 300
        close_connection(conn)

    def test_profile_filter(self):
        conn = _memory_connection()
        update_file_state(conn, "docs", "/d.txt", "/b/d.txt", "hd", 400)
        update_file_state(conn, "pics", "/p.txt", "/b/p.txt", "hp", 800)

        stats = get_backup_stats(conn, "docs")
        assert len(stats) == 1
        assert "docs" in stats
        assert "pics" not in stats
        assert stats["docs"]["file_count"] == 1
        assert stats["docs"]["total_size"] == 400
        close_connection(conn)


class TestFormatSize:
    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_bytes(self):
        assert format_size(512) == "512 B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_size(1024**2) == "1.0 MB"
        assert format_size(int(1.5 * 1024**2)) == "1.5 MB"

    def test_gigabytes(self):
        assert format_size(1024**3) == "1.0 GB"
        assert format_size(int(2.8 * 1024**3)) == "2.8 GB"


class TestGetAllBackups:
    def test_empty_db_returns_empty_list(self, monkeypatch):
        conn = _memory_connection()
        # patch open_connection to use in‑memory DB
        from barkup import database

        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        rows = get_all_backups(conn)
        assert rows == []

    def test_returns_rows_filtered_by_profile(self, monkeypatch, tmp_path):
        conn = _memory_connection()
        # create two dummy files to have real hashes
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        f2 = tmp_path / "b.txt"
        f2.write_text("world")
        hash1 = calculate_file_hash(str(f1))
        hash2 = calculate_file_hash(str(f2))
        update_file_state(
            conn, "profile1", str(f1), "/bk/a.txt", hash1, f1.stat().st_size
        )
        update_file_state(
            conn, "profile2", str(f2), "/bk/b.txt", hash2, f2.stat().st_size
        )
        from barkup import database

        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        rows_all = get_all_backups(conn)
        assert len(rows_all) == 2
        rows_profile1 = get_all_backups(conn, "profile1")
        assert len(rows_profile1) == 1
        assert rows_profile1[0]["profile"] == "profile1"


class TestVerifyBackup:
    def test_missing_file_returns_missing(self, monkeypatch, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "a.txt"
        f.write_text("data")
        hash_val = calculate_file_hash(str(f))
        update_file_state(conn, "p", str(f), "/bk/a.txt", hash_val, f.stat().st_size)
        # delete the file to simulate missing
        f.unlink()
        row = get_all_backups(conn, "p")[0]
        assert verify_backup(row) == "missing"

    def test_mismatch_returns_mismatch(self, monkeypatch, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "a.txt"
        f.write_text("original")
        good_hash = calculate_file_hash(str(f))
        update_file_state(conn, "p", str(f), "/bk/a.txt", good_hash, f.stat().st_size)
        # modify file
        f.write_text("changed")
        row = get_all_backups(conn, "p")[0]
        assert verify_backup(row) == "mismatch"

    def test_ok_returns_ok(self, monkeypatch, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "a.txt"
        f.write_text("unchanged")
        h = calculate_file_hash(str(f))
        update_file_state(conn, "p", str(f), "/bk/a.txt", h, f.stat().st_size)
        row = get_all_backups(conn, "p")[0]
        assert verify_backup(row) == "ok"


class TestSchemaMigration:
    def test_initialize_adds_compressed_column_when_missing(self, tmp_path):
        from barkup.database import open_connection

        db_path = tmp_path / "old.db"
        conn = open_connection(db_path=db_path)
        # Simulate the pre-compressed-column schema.
        conn.execute("DROP TABLE IF EXISTS backups")
        conn.execute(
            "CREATE TABLE backups ("
            "id INTEGER PRIMARY KEY, profile TEXT, original_path TEXT, "
            "backup_path TEXT, hash TEXT, size INTEGER, last_backup TEXT)"
        )
        conn.commit()
        conn.close()

        # Re-opening runs initialize_database, which migrates the schema.
        conn2 = open_connection(db_path=db_path)
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(backups)")}
        assert "compressed" in cols
        conn2.close()
