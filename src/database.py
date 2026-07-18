"""
SQLite state database for tracking backed-up files.

Stores a record per file per profile: the original path, where it was
backed up to, its SHA256 hash at backup time, size, and timestamp.
On each backup run, the engine compares current hashes against stored
ones to decide which files need copying (incremental backup).

The database lives alongside the user config:
    Linux/Mac:  ~/.config/barkup/state.db
    Windows:    %APPDATA%/barkup/state.db

If the database doesn't exist, it's created automatically.
If it's deleted, the next run does a full backup and rebuilds it.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import get_user_config_path
from hashing import calculate_file_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS backups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile     TEXT NOT NULL,
    original_path TEXT NOT NULL,
    backup_path TEXT NOT NULL,
    hash        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    last_backup TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(profile, original_path)
);

CREATE INDEX IF NOT EXISTS idx_profile
    ON backups(profile);
"""


def get_database_path() -> Path:
    """Database path, derived from user config directory."""
    return get_user_config_path().parent / "state.db"


def open_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and auto-create) the state database."""
    if db_path is None:
        db_path = get_database_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # dict-like access on rows
    initialize_database(conn)
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they don't exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def get_file_state(
    conn: sqlite3.Connection,
    original_path: str,
    profile: str,
) -> sqlite3.Row | None:
    """Look up the stored state for a file. Returns None if never backed up."""
    cursor = conn.execute(
        "SELECT * FROM backups WHERE profile = ? AND original_path = ?",
        (profile, original_path),
    )
    return cursor.fetchone()


def has_file_changed(
    conn: sqlite3.Connection,
    file_path: Path,
    profile: str,
) -> bool:
    """Check whether a file is new or has changed since last backup."""
    state = get_file_state(conn, str(file_path), profile)

    if state is None:
        return True  # new file, never backed up

    current_hash = calculate_file_hash(file_path)
    return current_hash != state["hash"]


def update_file_state(
    conn: sqlite3.Connection,
    profile: str,
    original_path: str,
    backup_path: str,
    file_hash: str,
    size: int,
) -> None:
    """Insert or update the state record for a backed-up file."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        """
        INSERT INTO backups (profile, original_path, backup_path, hash, size, last_backup)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile, original_path)
        DO UPDATE SET
            backup_path = excluded.backup_path,
            hash        = excluded.hash,
            size        = excluded.size,
            last_backup = excluded.last_backup
        """,
        (profile, original_path, backup_path, file_hash, size, now),
    )
    conn.commit()


def close_connection(conn: sqlite3.Connection) -> None:
    """Commit any pending changes and close."""
    conn.commit()
    conn.close()


def list_backups(
    conn: sqlite3.Connection,
    profile: str | None = None,
) -> list[sqlite3.Row]:
    """Return backed-up file records.

    With ``profile=None``, returns every record across all profiles,
    ordered by profile then original path. With a profile given, returns
    only that profile's records, ordered by original path.
    """
    if profile:
        rows = conn.execute(
            "SELECT * FROM backups WHERE profile = ? ORDER BY original_path",
            (profile,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM backups ORDER BY profile, original_path"
        ).fetchall()
    return rows


def get_backup_stats(
    conn: sqlite3.Connection,
    profile: str | None = None,
) -> dict:
    """Return per-profile backup statistics.

    With ``profile=None``, returns stats for all profiles.
    With a profile given, returns stats only for that profile.
    Returns empty dict when no backups exist.

    Each profile's stats include:
    - file_count: number of backed-up files
    - total_size: sum of file sizes in bytes
    - last_backup: most recent backup timestamp
    """
    if profile:
        rows = conn.execute(
            "SELECT profile, COUNT(*) AS count, COALESCE(SUM(size), 0) AS total, "
            "MAX(last_backup) AS last FROM backups WHERE profile = ? GROUP BY profile",
            (profile,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT profile, COUNT(*) AS count, COALESCE(SUM(size), 0) AS total, "
            "MAX(last_backup) AS last FROM backups GROUP BY profile"
        ).fetchall()

    return {
        r["profile"]: {
            "file_count": r["count"],
            "total_size": r["total"],
            "last_backup": r["last"],
        }
        for r in rows
    }


def format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size string (1024-based)."""
    if size_bytes == 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024**3:
        return f"{size_bytes / (1024**2):.1f} MB"
    return f"{size_bytes / (1024**3):.1f} GB"


def get_all_backups(
    conn: sqlite3.Connection, profile: str | None = None
) -> list[sqlite3.Row]:
    """Return all backup rows, optionally filtered by profile.
    Columns: profile, original_path, backup_path, hash.
    """
    cursor = conn.cursor()
    if profile:
        cursor.execute(
            "SELECT profile, original_path, backup_path, hash FROM backups WHERE profile = ?",
            (profile,),
        )
    else:
        cursor.execute("SELECT profile, original_path, backup_path, hash FROM backups")
    return cursor.fetchall()


def verify_backup(entry: sqlite3.Row) -> str:
    """Verify a single backup entry.
    Returns "ok" if the original file exists and matches the stored hash,
    "missing" if the file is absent, and "mismatch" if the hash differs.
    """
    original = Path(entry["original_path"])
    if not original.is_file():
        return "missing"
    try:
        current_hash = calculate_file_hash(str(original))
    except Exception:
        return "mismatch"
    return "ok" if current_hash == entry["hash"] else "mismatch"
