"""
Glob patterns specifying files and directories to exclude from the backup.

Patterns are matched against both the filename and each individual path
component, so a pattern like '*.log' will exclude any file with a .log
extension regardless of its location, and a pattern like '.git' will
exclude any file nested under a directory named .git.

Uses Unix shell-style wildcards (via fnmatch):
    *       matches everything
    ?       matches any single character
    [seq]   matches any character in seq
    [!seq]  matches any character not in seq

Examples:
    ['*.log', '.git', '__pycache__', '*.tmp']
"""

from pathlib import Path
from fnmatch import fnmatch
from dataclasses import dataclass

from config_resolvers import ResolvedLocalConfig, ResolvedCloudConfig

@dataclass
class FileToBackup:
    """A file that needs backing up, with metadata about its source."""
    path: Path
    source: Path  # The original source path (file or dir)
    source_is_dir: bool

def scan_sources(sources: list[str]) -> list[FileToBackup]:
    """Scan sources and return files with metadata."""
    files_to_backup = []
    
    for source in sources:
        source_path = Path(source).expanduser().resolve()
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source path doesn't exist: {source}")
        
        if source_path.is_file():
            files_to_backup.append(FileToBackup(
                path=source_path,
                source=source_path,
                source_is_dir=False
            ))
        elif source_path.is_dir():
            for file in source_path.rglob("*"):
                if file.is_file():
                    files_to_backup.append(FileToBackup(
                        path=file,
                        source=source_path,
                        source_is_dir=True
                    ))
    
    return files_to_backup


def should_exclude(file_path: Path, patterns: list[str]) -> bool:
    """Check if file matches any exclude pattern."""
    for pattern in patterns:
        # Match against filename
        if fnmatch(file_path.name, pattern):
            return True
        
        # Match against any path component
        for part in file_path.parts:
            if fnmatch(part, pattern):
                return True
    
    return False


def resolve_excluded(config: ResolvedLocalConfig | ResolvedCloudConfig) -> list[FileToBackup]:
    """Scan sources and filter out excluded files."""
    all_files = scan_sources(config.sources)
    included = [f for f in all_files if not should_exclude(f.path, config.exclude)]
    return included