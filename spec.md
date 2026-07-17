# Barkup - AI Coding Tool Specification

## Project Overview

**Name:** Barkup  
**Type:** CLI backup tool  
**Language:** Python 3.11+  
**Purpose:** Backup files/folders to local destinations with optional Google Drive sync  
**Timeline:** MVP first, then enhancements  
**Repository:** GitHub (in progress)

---

## What Has Been Implemented So Far

The developer has already completed the following features:

### ✅ Completed: Config File Handling
**Branch:** `feature/02-config-file`

**Implementation:**
- TOML-based configuration system (`tomllib` for parsing)
- Layered config loading with priority order: system → user → project → CLI
- Cross-platform config path resolution (Windows/Linux/Mac)
- Deep merge function for config inheritance
- Pydantic models for validation:
  - `BarkupConfig` (root model)
  - `GeneralConfig` (profile, dry_run, sources, compression, exclude)
  - `LocalConfig` (destination + optional overrides)
  - `CloudProvider` (Google Drive config)
  - `AdvancedConfig` (temp_dir)
- Config resolution system using dataclasses:
  - `ResolvedLocalConfig` (concrete local backup config)
  - `ResolvedGoogleDriveCloudConfig` (concrete cloud config)
- Config inheritance pattern where `general` section provides defaults for `sources`, `compression`, `exclude`
- Section-level overrides in `local` and `cloud_providers`
- Exclude lists merge (general excludes + section excludes combined and deduplicated)

**Files:**
- `config.py` - Config loading, path resolution, deep merge
- `config_models.py` - Pydantic models + resolved dataclasses + resolution functions
- `config.example.toml` - Example configuration file

**Key Functions:**
- `get_user_config_path()` - Platform-specific config path
- `resolve_config_paths(cli_path)` - Returns list of config paths in priority order
- `deep_merge(base, override)` - Recursively merge config dictionaries
- `load_config(cli_path)` - Load, merge, and validate config
- `resolve_local_config(general, local)` - Resolve local config to concrete values
- `resolve_cloud_config(general, provider)` - Resolve cloud config to concrete values

### ✅ Completed: Basic Local Backup Engine
**Branch:** `feature/03-local-backup-basic`

**Implementation:**
- Simple copy-all backup (copies all files, no state tracking yet)
- File and directory source handling
- Directory structure preservation during backup
- Uses `shutil.copy2()` to preserve metadata

**File:**
- `backup_engine.py`

**Key Function:**
```python
def backup_file(file_path: Path, source_root: Path, destination: Path) -> Path:
    """
    Backup a single file, preserving relative path structure.
    - For file sources: Uses filename only
    - For directory sources: Preserves relative path from source_root
    """
```

### ✅ Completed: Exclude Patterns
**Branch:** `feature/06-exclude-patterns`

**Implementation:**
- Glob pattern matching using Python's `fnmatch` module
- Recursive source scanning with `Path.rglob("*")`
- File metadata tracking via `FileToBackup` dataclass
- Exclude pattern matching against both filename and path components
- Merge general excludes + section excludes

**File:**
- `exclude_patterns.py`

**Key Components:**
```python
@dataclass
class FileToBackup:
    """File with metadata about its source."""
    path: Path           # Actual file location
    source: Path         # Original source (file or directory)
    source_is_dir: bool  # Whether source was a directory

def scan_sources(sources: list[str]) -> list[FileToBackup]
def should_exclude(file_path: Path, patterns: list[str]) -> bool
def resolve_excluded(config: ResolvedLocalConfig | ResolvedCloudConfig) -> list[FileToBackup]
```

**Pattern Matching:**
- Checks patterns against filename (e.g., `*.tmp` matches `test.tmp`)
- Checks patterns against path components (e.g., `.git` matches any `.git` directory in path)
- Uses `fnmatch` for glob-style patterns (not regex)

### ✅ Completed: Dry Run Mode Integration
**Implementation:**
- Shows preview of files to backup grouped by source
- Prompts for confirmation when dry_run is enabled
- Skips actual backup if user declines
- Integrated into `run_local_barkup()` function

**Flow:**
```python
def run_local_barkup(local_config: ResolvedLocalConfig):
    files = resolve_excluded(local_config)
    dry_run_output(files)  # Always show preview
    
    if local_config.dry_run:
        response = input("Proceed with backup? [y/N]: ")
        if response != 'y':
            return
    
    # Backup files...
```

---

## Core Requirements

### Design Philosophy
1. **Simple file replacement** - No versioning system (files are replaced when changed)
2. **Hybrid approach** - Config file for rules, CLI for manual operations
3. **Incremental backups** - Only backup changed files (detect via hash comparison)
4. **Optional compression** - ZIP format, user must enable it
5. **Config inheritance** - General defaults can be overridden per section
6. **All file types supported** - Videos, PDFs, docs, code - everything

### Tech Stack
**Required Libraries:**
- `pathlib` - File path operations
- `hashlib` - SHA256 hashing for file change detection
- `zipfile` - Compression (when enabled)
- `sqlite3` - State tracking database
- `tomllib` - TOML config parsing (Python 3.11+ built-in)
- `shutil` - File operations
- `fnmatch` - Glob pattern matching
- `pydantic>=2.0.0` - Config validation
- `dataclasses` - Resolved config containers

**Future Libraries (Cloud Integration):**
- `google-api-python-client` - Google Drive API

**Future Libraries (CLI & UX):**
- `click` or `argparse` - CLI framework
- `tqdm` - Progress bars

---

## MVP Features (Implement First)

These features should be completed before moving to enhancements:

### 1. State Tracking
**Goal:** Track which files have been backed up and detect changes using file hashes.

**Requirements:**
- SQLite database stored at `~/.config/barkup/state.db` (Linux/Mac) or `%APPDATA%\barkup\state.db` (Windows)
- Database tracks: original_path, backup_path, hash (SHA256), size, last_backup timestamp, profile name
- Hash calculation must read files in chunks (64KB recommended) to handle large files
- Compare current file hash with stored hash to detect changes
- Skip unchanged files during backup
- Update state after each successful backup
- If database doesn't exist, create it automatically
- If database is deleted, recreate and do full backup

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT,
    original_path TEXT,
    backup_path TEXT,
    hash TEXT,
    size INTEGER,
    last_backup TIMESTAMP,
    UNIQUE(profile, original_path)
);

CREATE INDEX IF NOT EXISTS idx_original_path ON backups(original_path);
```

**Key Functions:**
- `calculate_file_hash(file_path: Path) -> str` - SHA256 hash
- `get_file_state(conn, file_path, profile) -> dict | None` - Get stored state
- `has_file_changed(conn, file_path, profile) -> bool` - Compare hashes
- `update_file_state(conn, file_info)` - Insert or update state

**Updated Backup Flow:**
```
1. Open database connection
2. Scan sources
3. Filter excluded files
4. Filter to only changed files (new or hash differs)
5. Show stats: "X new, Y modified, Z unchanged (skipped)"
6. Backup changed files only
7. Update state for each backed-up file
8. Close database connection
```

### 2. Restore Functionality
**Goal:** Restore files from backup.

**Requirements:**
- Restore specific file: `barkup restore /path/to/file.txt`
- Restore all files from backup set: `barkup restore --all --name "Documents"`
- Handle both compressed and uncompressed backups
- Query database to find backup location
- Copy file back to original location (or specified location)
- Verify file integrity after restore (optional hash check)

**Key Functions:**
- `restore_file(original_path, destination)` - Restore single file
- `restore_all(backup_name)` - Restore entire backup set
- `find_backup_path(original_path)` - Query database for backup location

### 3. CLI Commands
**Goal:** Provide full command-line interface for all operations.

**Required Commands:**

**`barkup init`**
- Create default config file at user config location
- Copy from `config.example.toml` or generate minimal config
- Prompt user to edit config before first run

**`barkup run [--name PROFILE] [--yes]`**
- Run backup using config
- `--name`: Specify which backup profile to run (default: use config's profile_name)
- `--yes`: Skip confirmation prompt (useful for automation/cron)
- Show preview of files to backup
- If dry_run enabled: prompt for confirmation
- Backup changed files only (using state tracking)
- Update database state

**`barkup list [--name PROFILE]`**
- List all files currently backed up
- Show: original path, backup path, size, last backup time
- Group by backup profile if multiple exist
- Optional filters: by date, by size, by pattern

**`barkup status [--name PROFILE]`**
- Show backup statistics:
  - Total files tracked
  - Total backup size (local)
  - Total backup size (cloud, if enabled)
  - Last backup time
  - Number of backups (profiles)
- Show storage usage breakdown

**`barkup verify [--name PROFILE]`**
- Verify backup integrity
- Check all backed-up files still exist
- Recalculate hashes and compare with stored hashes
- Report any corrupted or missing files

**`barkup restore <path> [--to DESTINATION]`**
- Restore specific file
- `--to`: Restore to custom location (default: original location)

**`barkup restore --all --name PROFILE [--to DESTINATION]`**
- Restore entire backup set
- `--to`: Restore to custom directory (preserves structure)

**Framework:**
- Use `click` or `argparse` for CLI
- Provide `--help` for all commands
- Use `--config PATH` global option to specify custom config file

### 4. Documentation
**Goal:** Comprehensive README for users and developers.

**Required Sections:**

**README.md:**
1. **Project Description**
   - What Barkup is
   - Key features
   - Why it exists

2. **Installation**
   ```bash
   # From source
   git clone https://github.com/username/barkup
   cd barkup
   pip install -e .
   
   # Future: From PyPI
   pip install barkup
   ```

3. **Quick Start**
   ```bash
   barkup init
   # Edit ~/.config/barkup/config.toml
   barkup run
   ```

4. **Configuration**
   - Explain TOML config structure
   - Show example config with comments
   - Explain inheritance pattern (general → local/cloud)
   - Explain exclude patterns (glob syntax)

5. **Usage Examples**
   - Running backups
   - Restoring files
   - Viewing status
   - Dry run mode
   - Compression

6. **CLI Reference**
   - All commands with options
   - Example outputs

7. **Development**
   - How to clone and run locally
   - How to run tests (when implemented)
   - Project structure
   - How to contribute

8. **Requirements**
   - Python 3.11+
   - Dependencies

**Additional Docs (optional):**
- `CONTRIBUTING.md` - Contribution guidelines
- `CHANGELOG.md` - Version history

---

## Enhancement Features (Implement After MVP)

These features should be implemented after MVP is complete and working:

### 5. Compression
**Goal:** Optional ZIP compression for backups.

**Requirements:**
- Compression is **disabled by default**
- When enabled (per config section), use Python's `zipfile` module
- ZIP format using DEFLATE algorithm (lossless)
- When compression is enabled, show info message on first run:
  ```
  ℹ️  Compression is enabled (ZIP format)
     ZIP uses DEFLATE algorithm for lossless compression.
     To restore files, you can use:
     - barkup restore command
     - 7-Zip, WinZip, or any ZIP utility
  ```
- Compressed files stored as: `filename.ext.zip`
- Uncompressed files stored as: `filename.ext`
- Restore command must detect and handle both formats
- Hash calculation happens on original file (before compression)
- Database tracks whether file was compressed

**Smart Compression (optional enhancement):**
- Detect already-compressed formats (videos, JPEGs, ZIPs)
- Skip compression for these (minimal benefit, wastes CPU)
- Log: "Skipping compression for video.mp4 (already compressed format)"

### 6. Google Drive Integration
**Goal:** Upload backups to Google Drive.

**Requirements:**
- Uses `google-api-python-client` library
- Requires `credentials_file` (JSON from Google Cloud Console)
- Uploads to specified `remote_folder` path
- Large file warning: prompt before uploading files >1GB
  ```
  ⚠️  Large file detected: vacation.mp4 (2.3GB)
  
  Upload to Google Drive? [y/N]:
  ```
- Track upload status in database (`uploaded_to_cloud` boolean)
- Option to backup to:
  - Local only (`cloud.enabled = false`)
  - Local + Cloud (`cloud.enabled = true`)
  - Cloud only (future enhancement)
- Compress before upload if `cloud.compression = true`
- Skip excluded files (same exclude patterns apply)

**Cloud Backup Flow:**
```
1. Run local backup first
2. For each successfully backed up file:
   - Check file size
   - If >1GB: prompt user
   - If user confirms or <1GB: upload to Google Drive
   - Update database: uploaded_to_cloud = true
3. Show summary: "X files uploaded, Y files skipped"
```

**Authentication:**
- Use OAuth 2.0 with credentials file
- Handle token refresh automatically
- Store tokens in `~/.config/barkup/` directory

**Error Handling:**
- Network errors: retry up to 3 times
- Auth errors: prompt user to re-authenticate
- Quota exceeded: show clear error message
- Continue with other files if one fails

### 7. Comprehensive Error Handling
**Goal:** Graceful error handling throughout the application.

**Requirements:**
- Define custom exception classes:
  - `BarkupError` (base)
  - `ConfigError` (config issues)
  - `BackupError` (backup operation errors)
  - `CloudError` (Google Drive errors)
  - `DatabaseError` (SQLite errors)
- Handle common errors:
  - Source path doesn't exist → Skip with warning
  - No write permission on destination → Clear error message
  - Database corrupted → Recreate database
  - Config file invalid → Show validation errors
  - Network timeout → Retry logic
  - Insufficient disk space → Stop and warn user
- Log errors to file: `~/.config/barkup/barkup.log`
- Show user-friendly error messages (not stack traces)
- Exit codes:
  - 0: Success
  - 1: General error
  - 2: Config error
  - 3: Backup failed
  - 4: Cloud error

### 8. Progress Indicators
**Goal:** Show progress for long-running operations.

**Requirements:**
- Use `tqdm` library for progress bars
- Show progress when:
  - Scanning sources (file count)
  - Hashing files (progress through large files)
  - Backing up files (file count + total size)
  - Uploading to cloud (file count + upload progress)
- Display:
  - Current file being processed
  - Files completed / total files
  - Data transferred / total size
  - ETA (estimated time remaining)
- Example output:
  ```
  Backing up files: 45/100 [=============>      ] 45% | 1.2GB/2.5GB | ETA: 2m 15s
  Current: /home/user/Documents/large-video.mp4
  ```

### 9. Testing
**Goal:** Unit and integration tests for reliability.

**Requirements:**
- Use `pytest` framework
- Test coverage for:
  - Config loading and merging
  - Exclude pattern matching
  - File hashing
  - State tracking (database operations)
  - Backup and restore operations
  - CLI commands
- Mock external dependencies (Google Drive API)
- Test fixtures for config files and test data
- Integration tests for end-to-end workflows
- Aim for >80% code coverage

### 10. Installation & Distribution
**Goal:** Make Barkup easy to install.

**Requirements:**
- `setup.py` for pip installation:
```python
from setuptools import setup, find_packages

setup(
    name="barkup",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
    ],
    entry_points={
        'console_scripts': [
            'barkup=barkup.cli:main',
        ],
    },
    python_requires='>=3.11',
)
```
- `requirements.txt` with all dependencies
- Make it installable via: `pip install -e .` (development) or `pip install barkup` (future PyPI)
- After installation, `barkup` command available globally

---

## Configuration System (Already Implemented - Reference)

### Config File Structure (TOML)

**Location Priority (highest to lowest):**
1. CLI-specified: `--config /path/to/config.toml`
2. Project: `./barkup.config.toml`
3. User: `~/.config/barkup/config.toml` (Linux/Mac) or `%APPDATA%\barkup\config.toml` (Windows)
4. System: `/etc/barkup/config.toml` (Linux only)

**Example config.toml:**
```toml
[general]
profile_name = "my-backup"
dry_run = false
sources = ["/home/user/Documents", "/home/user/Projects"]
compression = false
exclude = ["*.tmp", ".git", "node_modules", "__pycache__"]

[local]
destination = "/home/user/Backups"
# Optional overrides (inherits from [general] if not specified):
# sources = ["/home/user/Documents"]
# compression = true
# exclude = ["*.log"]

[[cloud_providers]]
provider = "google_drive"
enabled = true
credentials_file = "/home/user/.barkup/google_drive.json"
remote_folder = "Backups/Barkup"
large_file_warning = 1000  # MB (1GB)
# Optional overrides:
# sources = ["/home/user/Documents"]
# compression = true
# exclude = ["*.mp4"]

[advanced]
temp_dir = "/tmp/barkup"
```

### Config Inheritance Rules
1. `[general]` section defines defaults for: `sources`, `compression`, `exclude`
2. `[local]` and `[[cloud_providers]]` inherit these defaults
3. Sections can override by specifying their own values
4. `exclude` lists are **merged** (general excludes + section excludes combined, duplicates removed)
5. Other fields are **replaced** (section value completely overrides general value)

### Validation (Pydantic Models - Already Implemented)
- All configs validated on load
- Type checking (strings, booleans, lists, integers)
- Required fields checked
- Provider-specific validation (e.g., Google Drive needs `credentials_file` when enabled)
- Clear error messages when validation fails

---

## Project Structure

```
barkup/
├── barkup/
│   ├── __init__.py
│   ├── cli.py              # CLI commands (init, run, list, status, verify, restore)
│   ├── config.py           # Config loading, path resolution, deep merge [DONE]
│   ├── config_models.py    # Pydantic models + resolved dataclasses [DONE]
│   ├── backup_engine.py    # Core backup logic [PARTIALLY DONE]
│   ├── exclude_patterns.py # Path scanning and filtering [DONE]
│   ├── database.py         # SQLite operations (state tracking) [TODO]
│   ├── compression.py      # ZIP compression utilities [TODO]
│   ├── cloud.py            # Google Drive integration [TODO]
│   ├── restore.py          # Restore functionality [TODO]
│   └── utils.py            # Helper functions (hashing, etc.) [TODO]
├── tests/
│   ├── test_config.py
│   ├── test_backup_engine.py
│   ├── test_exclude_patterns.py
│   ├── test_database.py
│   └── ...
├── config.example.toml     # Example configuration [DONE]
├── requirements.txt        # Dependencies
├── setup.py               # Installation config
├── README.md              # Documentation [TODO]
├── .gitignore
└── LICENSE
```

---

## Key Design Patterns

### 1. Config Validation → Resolution Pattern
```
Raw TOML dict
    ↓ (Pydantic validation)
BarkupConfig (may have None values)
    ↓ (Resolution functions)
ResolvedLocalConfig / ResolvedCloudConfig (all values concrete)
    ↓ (Used by backup engine)
Backup operations
```

### 2. State Tracking Pattern
```
Before each backup:
1. Calculate current file hash
2. Query database for stored hash
3. Compare: if different or new → backup needed
4. After successful backup → update database

Database = single source of truth for "what's been backed up"
```

### 3. File Scanning Pattern
```
Sources (files + directories)
    ↓ (scan_sources)
All files with metadata (FileToBackup objects)
    ↓ (filter with exclude patterns)
Files to backup
    ↓ (check against state database)
Changed files only
    ↓ (backup)
Update state
```

### 4. Backup Flow (High Level)
```
1. Load and validate config
2. Resolve config to concrete values
3. Scan sources → get all files
4. Apply exclude patterns → filter files
5. Check state database → identify changed files
6. Show preview (dry run output)
7. If dry_run: prompt for confirmation
8. Backup changed files to local destination
9. Update state database
10. If cloud enabled: upload to Google Drive
11. Show summary statistics
```

---

## Data Models Reference

### FileToBackup (Already Implemented)
```python
@dataclass
class FileToBackup:
    path: Path           # Actual file location
    source: Path         # Original source (file or directory)
    source_is_dir: bool  # Whether source was a directory
```

### ResolvedLocalConfig (Already Implemented)
```python
@dataclass
class ResolvedLocalConfig:
    destination: str
    sources: list[str]
    compression: bool
    exclude: list[str]
```

### ResolvedGoogleDriveCloudConfig (Already Implemented)
```python
@dataclass
class ResolvedGoogleDriveCloudConfig:
    provider: str  # Always "google_drive"
    enabled: bool
    large_file_warning: int  # MB
    sources: list[str]
    compression: bool
    exclude: list[str]
    credentials_file: str
    remote_folder: str
```

---

## Testing Strategy

### Manual Testing Checklist
- [ ] First backup (no state) - backs up all files
- [ ] Second backup (no changes) - skips all files
- [ ] Modify a file - backs up only that file
- [ ] Add new file - backs up only new file
- [ ] Delete state database - recreates and does full backup
- [ ] Exclude patterns work (*.tmp, .git, etc.)
- [ ] Dry run mode - shows preview, prompts correctly
- [ ] Compression enabled - creates .zip files
- [ ] Compression disabled - creates regular files
- [ ] Google Drive upload - files appear in Drive
- [ ] Large file warning - prompts for files >1GB
- [ ] Restore single file - restores correctly
- [ ] Restore all files - restores entire backup
- [ ] CLI commands work (init, run, list, status, verify, restore)

### Automated Testing (Future)
- Unit tests for each module
- Integration tests for workflows
- Mock Google Drive API for cloud tests
- Test fixtures for configs and data

---

## Error Scenarios to Handle

1. **Config Errors:**
   - Config file not found → suggest `barkup init`
   - Invalid TOML syntax → show parse error
   - Missing required fields → show validation error
   - Invalid paths → show clear error message

2. **Backup Errors:**
   - Source doesn't exist → skip with warning
   - No write permission on destination → clear error
   - Insufficient disk space → stop and warn
   - File locked/in use → skip with warning
   - Hash calculation fails → skip file

3. **Database Errors:**
   - Database corrupted → recreate automatically
   - Database locked → retry or clear error
   - Query fails → log error, continue

4. **Cloud Errors:**
   - No internet connection → skip cloud, continue local
   - Authentication fails → clear error, instructions to re-auth
   - Quota exceeded → show error, suggest cleanup
   - Upload fails → retry 3 times, then skip
   - Invalid credentials file → clear error

5. **General Errors:**
   - Out of memory → graceful shutdown
   - Keyboard interrupt (Ctrl+C) → clean shutdown
   - Unexpected errors → log stack trace, show user-friendly message

---

## Success Criteria

### MVP Complete When:
- [ ] State tracking works (detects changed files)
- [ ] Restore functionality works (single file + all files)
- [ ] All CLI commands implemented and working
- [ ] Comprehensive README written
- [ ] Can be installed via `pip install -e .`
- [ ] Manual testing checklist passes

### Full Project Complete When:
- [ ] Compression feature implemented
- [ ] Google Drive integration working
- [ ] Error handling comprehensive
- [ ] Progress indicators added
- [ ] Tests written (>80% coverage)
- [ ] Documentation complete
- [ ] Ready for portfolio presentation

---

## Development Workflow

### Branch Strategy
- `main` - Stable releases
- `dev` - Integration branch
- `feature/XX-name` - Feature branches

**Completed Branches:**
- `feature/02-config-file` ✅
- `feature/03-local-backup-basic` ✅
- `feature/06-exclude-patterns` ✅

**Next Branches:**
- `feature/04-state-tracking` (MVP)
- `feature/07-restore` (MVP)
- `feature/10-cli-commands` (MVP)
- `feature/15-documentation` (MVP)
- `feature/05-compression` (Enhancement)
- `feature/08-cloud-google-drive` (Enhancement)
- `feature/13-error-handling` (Enhancement)
- `feature/12-progress-indicators` (Enhancement)
- `feature/14-testing` (Enhancement)

### Commit Messages
Use clear, descriptive messages:
- "Add state tracking with SQLite"
- "Implement restore functionality"
- "Add progress bars for backup operations"
- "Fix bug in exclude pattern matching"
- "Update README with usage examples"

---

## Timeline

### This Week (MVP Focus)
1. State tracking
2. Restore functionality
3. CLI commands
4. Documentation

**Goal:** Working MVP that can be used daily

### Later (Enhancements)
5. Compression
6. Google Drive integration
7. Error handling
8. Progress indicators
9. Testing

**Goal:** Portfolio-ready, production-quality tool

---

## Additional Notes

### Why These Choices?

**SQLite for state:**
- Persistent between runs
- Fast lookups
- Handles thousands of files
- Single file, no external database
- Built into Python

**Glob patterns (fnmatch) not regex:**
- Users expect glob (like .gitignore)
- Simpler syntax
- Standard across tools

**No versioning:**
- Keeps scope manageable (20-40 hour project)
- Simple replacement model
- Can add versioning later as enhancement

**ZIP compression:**
- Standard format
- Lossless
- Users can extract with any tool
- Good compression ratio

**Google Drive only:**
- Most users have Google account
- Good API documentation
- Free tier sufficient for most users

### Performance Considerations
- Hash calculation: read files in 64KB chunks (handles large files)
- Database: indexed on original_path for fast lookups
- Exclude patterns: check early to avoid processing unnecessary files
- Progress bars: update every N files to avoid slowdown

### Security Considerations
- Credentials file: user responsible for securing it
- Don't log sensitive data (credentials, tokens)
- File permissions: preserve original permissions when restoring
- Hash verification: detect corrupted backups

---

## Questions for AI Coding Tool

As you implement this specification, consider:

1. How should the restore command handle conflicts? (file exists at restore location)
2. Should there be a `--force` flag to overwrite without prompting?
3. Should the status command show size in human-readable format (GB/MB/KB)?
4. Should there be a `--verbose` flag for detailed output?
5. How should the CLI handle multiple backup profiles? (select which to run)
6. Should there be a `--quiet` flag for cron jobs? (minimal output)
7. Should the verify command auto-repair corrupted files? (re-backup them)

These can be decided during implementation based on best practices and user experience.

---

**This specification is comprehensive and ready for an AI coding tool to implement. Start with MVP features, then proceed to enhancements.**