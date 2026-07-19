"""Restore logic for barkup: single-file and full-profile restore.

Pure functions over the SQLite state DB. The CLI layer (``cli.py``) wraps
these with user-facing messaging and exit codes.

All DB access goes through ``database.open_connection`` / ``close_connection``
(via module reference, not a top-level binding) so tests can monkeypatch
``database.open_connection`` with an in-memory connection.
"""

import shutil
from pathlib import Path

import database


def _restore_target(original_path: str, destination: str | None) -> Path:
    """Resolve where a single file should be restored to.

    With ``destination`` given, restore to that exact path (a file).
    Otherwise restore in place at the original path.
    """
    if destination:
        return Path(destination)
    return Path(original_path)


def _profile_restore_target(original_path: str, destination: str | None) -> Path:
    """Resolve where a profile file should be restored to.

    With ``destination`` given, reconstruct the original directory tree
    underneath it (collision-free), so two same-named files in different
    source directories don't clobber each other. Otherwise restore in place.
    """
    original = Path(original_path)
    if destination:
        if original.is_absolute():
            return Path(destination) / original.relative_to(original.anchor)
        return Path(destination) / original
    return original


def find_backup_path(original_path: str, profile: str | None = None) -> str | None:
    """Query the DB for the backup location of an original file path.

    Args:
        original_path: Original file path. Compared against the stored
            ``original_path`` column after resolving to an absolute path, so
            a relative argument still matches an absolute DB entry.
        profile: Optional profile name to scope the lookup.

    Returns:
        The stored ``backup_path`` string, or ``None`` if no matching row.
    """
    resolved = str(Path(original_path).resolve())
    conn = database.open_connection()
    try:
        if profile:
            cursor = conn.execute(
                "SELECT backup_path FROM backups "
                "WHERE original_path = ? AND profile = ?",
                (resolved, profile),
            )
        else:
            cursor = conn.execute(
                "SELECT backup_path FROM backups WHERE original_path = ?",
                (resolved,),
            )
        row = cursor.fetchone()
    finally:
        database.close_connection(conn)
    return row["backup_path"] if row else None


def restore_file(
    original_path: str,
    destination: str | None = None,
    profile: str | None = None,
) -> Path:
    """Restore a single file from backup.

    Args:
        original_path: Original file path (used to query the DB).
        destination: Custom restore location (a file path). Defaults to the
            original location.
        profile: Profile name to filter the lookup by.

    Returns:
        Path where the file was restored.

    Raises:
        FileNotFoundError: If no DB row matches or the backup file is missing.
    """
    backup_path_str = find_backup_path(original_path, profile)

    if not backup_path_str:
        if profile:
            raise FileNotFoundError(
                f"File '{original_path}' not found in backup for profile '{profile}'"
            )
        raise FileNotFoundError(f"File '{original_path}' not found in any backup")

    backup_path = Path(backup_path_str)
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file missing: {backup_path}")

    restore_path = _restore_target(original_path, destination)
    restore_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, restore_path)
    return restore_path


def restore_all_files(profile: str, destination: str | None = None) -> dict:
    """Restore every file in a backup profile.

    Args:
        profile: Profile name to restore.
        destination: Custom directory to restore into, preserving the
            original directory tree. Defaults to restoring in place.

    Returns:
        Dict with ``restored`` count and a ``failed`` list of
        ``{"path", "error"}`` entries. Individual file failures are collected,
        not fatal.

    Raises:
        ValueError: If the profile has no backup rows.
    """
    conn = database.open_connection()
    try:
        rows = conn.execute(
            "SELECT original_path, backup_path FROM backups "
            "WHERE profile = ? ORDER BY original_path",
            (profile,),
        ).fetchall()
    finally:
        database.close_connection(conn)

    if not rows:
        raise ValueError(f"No backups found for profile '{profile}'")

    results: dict = {"restored": 0, "failed": []}
    for original_path, backup_path in rows:
        try:
            backup_file = Path(backup_path)
            if not backup_file.is_file():
                results["failed"].append(
                    {"path": original_path, "error": "Backup file missing"}
                )
                continue

            restore_path = _profile_restore_target(original_path, destination)
            restore_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, restore_path)
            results["restored"] += 1
        except Exception as e:  # noqa: BLE001 - report and continue
            results["failed"].append({"path": original_path, "error": str(e)})

    return results
