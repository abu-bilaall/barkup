from pathlib import Path
import shutil
import sqlite3

from config import load_config
from exclude_patterns import resolve_excluded, FileToBackup
from dry_run import dry_local_run, dry_cloud_run
from config_resolvers import (
    resolve_local_config,
    resolve_cloud_config,
)
from database import open_connection, has_file_changed, update_file_state, close_connection
from hashing import calculate_file_hash


def barkup_file(
    file_path: Path, source_root: Path, destination: Path, source_is_dir: bool
) -> Path:
    # Calculate relative path from source root
    if source_is_dir:
        relative_path = source_root.name / file_path.relative_to(source_root)
    else:
        relative_path = file_path.relative_to(source_root.parent)

    # Build destination path
    dest_file = destination / relative_path

    # Create parent directories if needed
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    # Copy the file (with metadata preserved)
    shutil.copy2(file_path, dest_file)

    return dest_file


def run_barkup(cli_path: Path | None = None) -> None:
    config = load_config(cli_path)

    local_config = resolve_local_config(config.general, config.local)
    cloud_configs = [
        resolve_cloud_config(config.general, provider)
        for provider in config.cloud_providers
        if provider.enabled
    ]

    profile = local_config.profile_name

    # open state database
    conn = open_connection()

    try:
        # local files prep
        all_local_files = resolve_excluded(local_config)
        local_destination = Path(local_config.destination)

        # filter to only changed files
        changed_files, unchanged_count = _filter_changed(conn, all_local_files, profile)

        # cloud files prep
        # TODO: resolve cloud files from cloud_configs when cloud backup is implemented
        cloud_files_to_backup: list[FileToBackup] = []
        cloud_dest = ""

        # always show preview of all non-excluded files
        dry_local_run(all_local_files, local_destination)
        if cloud_configs:
            dry_cloud_run(cloud_files_to_backup, cloud_dest)

        # show change summary
        _print_change_summary(changed_files, unchanged_count)

        # if nothing changed, exit early
        if not changed_files and not cloud_files_to_backup:
            print("\n✅ Everything is up to date. No files need backing up.")
            return

        # if dry-run: ask if they want to proceed
        if local_config.dry_run:
            response = input("\nProceed with backup? [y/N]: ").strip().lower()
            if response != "y":
                print("Backup cancelled.")
                return

        print("\nRunning backups...")

        if changed_files:
            run_local_barkup(changed_files, local_destination, conn, profile)

        if cloud_configs:
            run_cloud_barkup(cloud_configs)
    finally:
        close_connection(conn)


def _filter_changed(
    conn: sqlite3.Connection,
    files: list[FileToBackup],
    profile: str,
) -> tuple[list[FileToBackup], int]:
    """Split files into changed (need backup) and unchanged (skip).

    Returns (changed_files, unchanged_count).
    """
    changed = []
    unchanged_count = 0

    for f in files:
        if has_file_changed(conn, f.path, profile):
            changed.append(f)
        else:
            unchanged_count += 1

    return changed, unchanged_count


def _print_change_summary(changed: list[FileToBackup], unchanged: int) -> None:
    """Show how many files are new/modified vs skipped."""
    total = len(changed) + unchanged
    print(f"\n📊 {len(changed)} to backup, {unchanged} unchanged (skipped) — {total} total")


def run_local_barkup(
    files_to_backup: list[FileToBackup],
    destination: Path,
    conn: sqlite3.Connection,
    profile: str,
) -> None:
    """Run the local backup process with state tracking."""
    print("\n======= Local Backup ======")
    print("Backing up files...")
    success_count = 0

    for file_info in files_to_backup:
        try:
            backed_up_path = barkup_file(
                file_path=file_info.path,
                source_root=file_info.source,
                destination=destination,
                source_is_dir=file_info.source_is_dir,
            )

            # update state after successful copy
            file_hash = calculate_file_hash(file_info.path)
            file_size = file_info.path.stat().st_size
            update_file_state(
                conn,
                profile=profile,
                original_path=str(file_info.path),
                backup_path=str(backed_up_path),
                file_hash=file_hash,
                size=file_size,
            )

            print(f"  ✓ {file_info.path.name}")
            success_count += 1
        except Exception as e:
            print(f"  ✗ {file_info.path}: {e}")

    print(
        f"\n✅ Backup complete! {success_count}/{len(files_to_backup)} files backed up."
    )


def run_cloud_barkup(cloud_configs):
    pass
