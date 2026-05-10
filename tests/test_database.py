import sqlite3
from pathlib import Path

from database import (
    open_connection,
    initialize_database,
    get_file_state,
    has_file_changed,
    update_file_state,
    close_connection,
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

        assert work_state["hash"] == "hash1"
        assert personal_state["hash"] == "hash2"
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
        from hashing import calculate_file_hash

        update_file_state(
            conn, "default", str(f), "/backup/stable.txt",
            calculate_file_hash(f), f.stat().st_size,
        )

        assert has_file_changed(conn, f, "default") is False
        close_connection(conn)

    def test_modified_file_returns_true(self, tmp_path):
        conn = _memory_connection()
        f = tmp_path / "changing.txt"
        f.write_text("original")

        from hashing import calculate_file_hash

        update_file_state(
            conn, "default", str(f), "/backup/changing.txt",
            calculate_file_hash(f), f.stat().st_size,
        )

        # modify the file
        f.write_text("modified")

        assert has_file_changed(conn, f, "default") is True
        close_connection(conn)
