from pathlib import Path
import shutil

from config import load_config
from exclude_patterns import resolve_excluded, FileToBackup
from dry_run import dry_local_run, dry_cloud_run
from config_resolvers import (
    resolve_local_config,
    resolve_cloud_config,
)


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

    # local files prep
    local_files_to_backup = resolve_excluded(local_config)
    local_destination = Path(local_config.destination)

    # cloud files prep
    # TODO: resolve cloud files from cloud_configs when cloud backup is implemented
    cloud_files_to_backup: list[FileToBackup] = []
    cloud_dest = ""

    # always show preview
    dry_local_run(local_files_to_backup, local_destination)
    if cloud_configs:
        dry_cloud_run(cloud_files_to_backup, cloud_dest)

    # if no real files to backup, exit early
    if not local_files_to_backup and not cloud_files_to_backup:
        return

    # if dry-run: ask if they want to proceed
    if local_config.dry_run:
        response = input("\nProceed with backup? [y/N]: ").strip().lower()
        if response != "y":
            print("Backup cancelled.")
            return

    print("\nRunning backups...")

    if local_config:
        run_local_barkup(local_files_to_backup, local_destination)

    if cloud_configs:
        run_cloud_barkup(cloud_configs)


def run_local_barkup(files_to_backup: list[FileToBackup], destination: str) -> None:
    """Run the local backup process."""
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
            print(f"✓ Backed up {file_info.path.name} to {backed_up_path}")
            success_count += 1
        except Exception as e:
            print(f"✗ Failed to backup {file_info.path}: {e}")

    print(
        f"\n✅ Backup complete! {success_count}/{len(files_to_backup)} files backed up."
    )


def run_cloud_barkup(cloud_configs):
    pass
