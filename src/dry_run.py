"""
Provides a dry-run output utility for previewing backup operations.

Displays the files that would be backed up, grouped by their source path.
Directory sources are summarised with a truncated file listing (first 5 files)
to keep output readable when a large number of files are matched.
"""

from collections import defaultdict

from exclude_patterns import FileToBackup

def dry_run_output(files: list[FileToBackup]):
    """Show what would be backed up, grouped by source."""
    
    by_source = defaultdict(list)
    for file_info in files:
        by_source[file_info.source].append(file_info.path)
    
    for source, files in by_source.items():
        if source.is_file():
            print(f"📄 File: {source}")
        else:
            print(f"📁 Directory: {source}")
            if len(files) <= 5:
                for f in files:
                    print(f"   - {f.relative_to(source)}")
            else:
                for f in files[:5]:
                    print(f"   - {f.relative_to(source)}")
                print(f"   ... and {len(files) - 5} more files")