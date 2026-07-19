from collections import defaultdict

from barkup.exclude_patterns import FileToBackup


def dry_run_output(files: list[FileToBackup]) -> None:
    """Show what would be backed up, grouped by source."""

    by_source = defaultdict(list)
    for file_info in files:
        by_source[file_info.source].append(file_info.path)

    for source, source_files in by_source.items():
        if source.is_file():
            print(f"📄 File: {source}")
        else:
            print(f"📁 Directory: {source}")
            if len(files) <= 5:
                for f in source_files:
                    print(f"   - {f.relative_to(source)}")
            else:
                for f in source_files[:5]:
                    print(f"   - {f.relative_to(source)}")
                print(f"   ... and {len(files) - 5} more files")


def dry_local_run(local_backup: list[FileToBackup], local_dest: str) -> None:
    """dry run for local backup"""
    print("\n          [DRY RUN]")
    print("======= Local Backup ======")
    if not local_backup:
        print("\nNo files to backup locally.")
        return

    print(f"🔎 Found {len(local_backup)} files to backup locally...")
    dry_run_output(local_backup)

    # show destination
    print(f"\n🗃️  Destination: {local_dest}")


def dry_cloud_run(cloud_backup: list[FileToBackup], cloud_dest: str) -> None:
    """dry run for cloud backup"""
    print("\n\n====== Cloud Backup ======")
    if not cloud_backup:
        print("No files to backup to cloud.")
        return

    print(f"🔎 Found {len(cloud_backup)} files to backup to cloud...")
    dry_run_output(cloud_backup)

    # show destination
    print(f"\n🗃️  Destination: {cloud_dest}")
