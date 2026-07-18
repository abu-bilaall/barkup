# AGENTS.md - barkup

## Project Overview

### Basic Description
**Barkup** is a Python-based CLI tool for automating personal backups to local and cloud storage with support for Google Drive.

### Tech Stack
- python >= 3.12
- pydantic>=2.12.5
- pytest>=9.0.2

### Layered Pipeline Architecture
```
TOML config files → Deep merge (system/user/cwd/CLI precedence)
  ↓
Pydantic validation models (config_models.py)
  ↓
Resolved dataclasses with inheritance applied (config_resolvers.py)
  ↓
Scan source directories → FileToBackup objects
  ↓
Apply exclusion patterns (fnmatch glob matching)
  ↓
Compare SHA256 hashes with SQLite state
  ↓
Filter changed/new files only
  ↓
Dry-run preview (optional) → User confirmation
  ↓
Copy files preserving metadata and directory structure
  ↓
Update SQLite state (hash, path, size, timestamp)
```
## Key Commands

### Package Management
```bash
uv add <package>         # Runtime dependency
uv add --dev <package>   # Development dependency
```
### Running the Application
```bash
./main.sh                 # Development runner
uv run src/main.py        # Direct execution
```

### Testing
```bash
./run_tests.sh           # Verbose test runner
uv run pytest -v         # Direct pytest execution
uv run pytest tests/test_database.py  # Run specific test file
```

### barkup-specific commands (to be implemented)
```bash
barkup init              # Create default config
barkup run               # Execute backup
barkup list              # Show backup history
barkup status            # Check backup state
barkup verify            # Validate backup integrity
barkup restore           # Restore files
```

### State Management

- SQLite database (`~/.config/barkup/state.db`) with one row per `(profile, file)` tuple
- Schema: `profile`, `original_path`, `backup_path`, `hash`, `size`, `last_backup`
- UNIQUE constraint on `(profile, original_path)` for upsert pattern
- Separate profiles enable backup isolation

### Config Inheritance Pattern

- **General section** (`[general]`): Provides default values for `sources`, `compression`, `exclude` patterns
- **Local/Cloud sections** (`[local]`, `[[cloud_providers]]`): Override general defaults
- **Exclude lists**: Merge and deduplicate rather than replace
- **Config precedence**: CLI path → `./barkup.config.toml` → `~/.config/barkup/config.toml` → `/etc/barkup/config.toml`

## Project Structure

- **`src/`**: application source code (not nested).
- **`tests/`**: Pytest test suite (mirrors src/ structure)
- **Root**: Configuration examples, shell script runners, spec documentation

## Code Conventions & Common Patterns

### Naming Conventions
- **Modules**: `snake_case.py`
- **Classes**: `PascalCase` (e.g., `GeneralConfig`, `ResolvedLocalConfig`)
- **Functions**: `snake_case` (e.g., `run_barkup`, `calculate_file_hash`)
- **Private functions**: Leading underscore `_filter_changed`, `_print_change_summary`
- **Test classes**: `TestCamelCase` (e.g., `TestCalculateFileHash`)
- **Test methods**: `test_<action>_<expected_result>`

### Preferred Workflow Steps
1. Write code for a functionality
2. If appropriate, test the functionality (you will see the test principles below). If it fails, fix the code until it passes.
3. If feature is not done/completed, write code for another functionality neccessary for the feature.
4. If feature is completed, update the docs if neccessary and prepare the PR back to development branch.
5. Ask nicely whether to commit the files, push to the remote branch and open the PR. If granted, use the pr creator skill. When you've written the PR and prepare, ask the user to review before you execute. We love convntional commits and we love to keep our commit message under the suggested characters such that it is displayed nicely on remote (you know what I mean).

### Testing Patterns
- Write tests for all new functionality
- Tests must be deterministic and isolated
- For unit tests, mock all dependencies.
- The tests for a particular task must pass before you mark it as complete
