# Barkup Development Roadmap Plan

## Context

This plan establishes the complete development roadmap for Barkup from its current MVP state to a fully-featured, installable CLI backup tool. The developer is a Junior Backend Engineer (TypeScript primary) returning after a 2-month hiatus. The workflow is: feature-branch → implement functions → write unit tests → merge to dev → next feature. Once MVP is complete, proceed to nice-to-have features including PyPI packaging.

**Current State:**
- ✅ Config system (TOML parsing, validation, inheritance) - COMPLETE
- ✅ Basic local backup with file copying - COMPLETE  
- ✅ Exclude patterns with glob matching - COMPLETE
- ✅ Dry-run preview mode - COMPLETE
- ✅ State tracking (SQLite + SHA256 hashing) - COMPLETE
- ✅ Incremental backups (only changed files) - COMPLETE
- ✅ 30 unit tests passing (barkup, config, database, hashing modules)
- ❌ Tests for exclude_patterns, dry_run, config_resolvers - MISSING
- ❌ CLI commands framework - NOT STARTED
- ❌ Restore functionality - NOT STARTED
- ❌ Compression (ZIP) - NOT STARTED
- ❌ Google Drive integration - NOT STARTED
- ❌ Installable package - NOT STARTED
- ❌ Documentation (README) - EMPTY

**Testing Philosophy Agreement:**
Unit tests are the right primary focus for a CLI tool. Integration/E2E tests will be valuable later for command workflows, but unit tests give the fastest feedback loop and highest ROI during feature development. We'll add integration tests after MVP CLI is working.

## Approach

### Phase 0: Foundation Improvements (Current State to Solid Base)

#### Step 0.1: Add Missing Unit Tests for Implemented Features
**Branch:** `test/complete-unit-coverage`

Before adding new features, ensure all existing code has tests. Missing coverage:
- `exclude_patterns.py`: 3 functions untested
- `dry_run.py`: 3 functions untested  
- `config_resolvers.py`: 2 resolver functions untested
- `main.py`: Entry point error handling untested

**Files to create:**
- `tests/test_exclude_patterns.py` - Test `scan_sources()`, `should_exclude()`, `resolve_excluded()`
- `tests/test_dry_run.py` - Test `dry_run_output()`, `dry_local_run()`, `dry_cloud_run()`
- `tests/test_config_resolvers.py` - Test `resolve_local_config()`, `resolve_cloud_config()`
- `tests/test_main.py` - Test ValidationError handling in main entry point

**Test scenarios per module:**

`test_exclude_patterns.py`:
- `scan_sources()`: file source, directory source, nested dirs, nonexistent path raises FileNotFoundError, symlinks
- `should_exclude()`: filename match (`*.log`), path component match (`.git`), no match, multiple patterns
- `resolve_excluded()`: filters correctly, empty exclude list, all files excluded

`test_dry_run.py`:
- `dry_run_output()`: single source, multiple sources, >5 files truncation, file vs directory labeling
- `dry_local_run()`: shows file count, shows destination, empty files list
- `dry_cloud_run()`: shows file count, shows destination, empty files list
(Note: These are display functions - tests verify output content via capsys fixture)

`test_config_resolvers.py`:
- `resolve_local_config()`: uses general defaults when local fields None, overrides with local values, merges exclude lists, compression flag inheritance
- `resolve_cloud_config()`: Google Drive provider resolution, source/exclude inheritance, validates provider type

`test_main.py`:
- Entry point catches Pydantic ValidationError and calls sys.exit(1)
- Entry point runs successfully with valid config

**Testing Pattern Notes (for TypeScript developer):**
- Use `tmp_path` fixture (pytest equivalent of Node's temp directory) for filesystem tests
- Use `capsys` fixture to capture stdout for display function tests
- In-memory SQLite pattern already established in `test_database.py` - reuse `_memory_connection()` helper if needed
- Arrange-Act-Assert pattern throughout (like Jest's structure)
- Test class naming: `TestFunctionName`, method naming: `test_<behavior>_<expected_result>`

**Acceptance:** All 4 new test files created, `uv run pytest -v` shows 50+ tests passing, coverage for all existing src/ modules.

---

#### Step 0.2: Fix Any Code Quality Issues Discovered by Tests
**Branch:** Same branch as 0.1 (test/complete-unit-coverage)

While writing tests, if bugs or edge cases are discovered:
- Fix them in the same branch
- Update tests to verify the fix
- Document the issue in commit message

Common patterns to watch:
- Path resolution edge cases (relative paths, symlinks, ~ expansion)
- Empty list handling in exclude patterns
- Unicode filenames (Python 3 handles well, but test it)
- Large file handling (already chunked in hashing.py, verify it works)

**Acceptance:** All discovered issues fixed, tests prove the fixes work.

---

#### Step 0.3: Add Quality Gates - Pre-commit, Lint, CI
**Branch:** `feature/cli-framework` (added alongside Step 1.1)

**Pre-commit hooks (the Python equivalent of husky + lint-staged):**
Install `pre-commit` + `ruff` as dev dependencies and add `.pre-commit-config.yaml`:
- `ruff` hook (`--fix`) - linting only (unused imports, undefined names, import sorting)
- `black` hook - formatting, runs automatically on every commit

Run `uv run pre-commit install` once to activate the git hook. This mirrors
husky: files are auto-checked/formatted before each commit.

**Ruff config (`[tool.ruff]` in `pyproject.toml`):** scoped to lint rules only
(`select = ["F", "I"]`). Formatting (including line length) is owned by `black`,
so ruff must NOT select the `E` (pycodestyle) category - doing so duplicates
black and conflicts with it.

**CI (GitHub Actions):** `.github/workflows/ci.yml`
- Trigger: `pull_request` on `branches: [dev, main]` (runs before merge)
- Job `lint`: `uv run ruff check .` + `uv run black --check .`
- Job `test`: `uv run pytest -v`
- Type-checking (pyright/basedpyright) is deliberately deferred - see Step 3.1b.

**README:** Added a CI status badge (placeholder `[username]`) pointing at
`?branch=dev`, since active development happens on `dev`.

**Files created/modified:**
- `.pre-commit-config.yaml` (new)
- `.github/workflows/ci.yml` (new)
- `README.md` (badge added)
- `pyproject.toml` (`[tool.ruff]` config; dev deps `pre-commit`, `ruff`)

**Acceptance:** `uv run pre-commit run --all-files` passes; `uv run ruff check .`
and `uv run black --check .` are clean; `uv run pytest` is green; CI runs on PRs
targeting `dev` and `main`.

---

### Phase 1: MVP Feature - CLI Commands Framework

**Default Profile Resolution:**
All CLI commands follow this three-tier fallback for profile selection:
1. **CLI flag** `--name` (highest priority) - user explicitly specifies profile
2. **Config file** `[general] profile_name = "mybackup"` (middle priority) - user's preferred default
3. **Hardcoded fallback** `"default"` (lowest priority) - when nothing else specified

**Implementation pattern for all commands:**
```python
def resolve_profile_name(cli_name: str | None, config) -> str:
    """Resolve which profile to use based on precedence."""
    if cli_name:
        return cli_name
    if hasattr(config, 'general') and hasattr(config.general, 'profile_name'):
        return config.general.profile_name
    return "default"
```

This helper function is created in Step 1.1 and reused in all subsequent commands.

**Why this design:**
- Explicit CLI flag always wins (user intent in the moment)
- Config default provides convenience (set once, use everywhere)
- Hardcoded fallback prevents errors (something always works)
- Consistent across all commands (no surprises)

---

#### Step 1.1: Add Click Framework and Basic Command Structure
**Branch:** `feature/cli-framework`

Install Click (industry-standard Python CLI framework, similar to Commander.js in Node):
```bash
uv add click
```

**Why Click over argparse:**
- Cleaner syntax (decorators vs imperative code)
- Better help text formatting
- Subcommand support built-in
- TypeScript devs find decorator syntax familiar

**Create:** `src/cli.py`

Structure (with profile resolution helper):
```python
import click
from pathlib import Path

def resolve_profile_name(cli_name: str | None, config) -> str:
    """Resolve which profile to use based on three-tier precedence.
    
    1. CLI --name flag (highest priority)
    2. Config [general] profile_name field
    3. Hardcoded "default" fallback
    """
    if cli_name:
        return cli_name
    if hasattr(config, 'general') and hasattr(config.general, 'profile_name'):
        return config.general.profile_name
    return "default"

@click.group()
@click.option('--config', type=click.Path(exists=True), help='Custom config file path')
@click.pass_context
def cli(ctx, config):
    """Barkup - CLI backup tool for local and cloud storage."""
    # Store config path in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = Path(config) if config else None

@cli.command()
def init():
    """Create default config file."""
    # Implementation in Step 1.2
    pass

@cli.command()
@click.option('--name', help='Backup profile name')
@click.option('--yes', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def run(ctx, name, yes):
    """Run backup using config."""
    # Implementation in Step 1.3
    pass

@cli.command('list')  # Renamed to avoid Python keyword
@click.option('--name', help='Filter by profile name')
def list_cmd(name):
    """List all backed up files."""
    # Implementation in Step 1.4
    pass

@cli.command()
@click.option('--name', help='Show stats for specific profile')
def status(name):
    """Show backup statistics."""
    # Implementation in Step 1.5
    pass

@cli.command()
@click.option('--name', help='Verify specific profile')
def verify(name):
    """Verify backup integrity."""
    # Implementation in Step 1.6
    pass

@cli.command()
@click.argument('path', required=False)
@click.option('--to', 'destination', help='Restore to custom location')
@click.option('--all', 'restore_all', is_flag=True, help='Restore entire backup set')
@click.option('--name', help='Profile name')
def restore(path, destination, restore_all, name):
    """Restore files from backup."""
    # Implementation in Phase 2
    pass

if __name__ == '__main__':
    cli()
```

**Update:** `src/main.py`
```python
from cli import cli

if __name__ == '__main__':
    cli()
```

**Update:** `pyproject.toml`
Add console_scripts entry point:
```toml
[project.scripts]
barkup = "cli:cli"
```

**Testing:** `tests/test_cli.py`
```python
from click.testing import CliRunner
from cli import cli

class TestCliStructure:
    def test_cli_help_shows_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'init' in result.output
        assert 'run' in result.output
        assert 'list' in result.output
        # ... etc
    
    def test_custom_config_option(self):
        # Test --config flag is recognized
        pass

class TestResolveProfileName:
    def test_cli_name_takes_precedence(self):
        # Mock config with profile_name="config_profile"
        # Call resolve_profile_name("cli_profile", config)
        # Assert returns "cli_profile"
        pass
    
    def test_uses_config_profile_when_no_cli_name(self):
        # Mock config with profile_name="config_profile"
        # Call resolve_profile_name(None, config)
        # Assert returns "config_profile"
        pass
    
    def test_defaults_to_default_when_nothing_specified(self):
        # Mock config without profile_name
        # Call resolve_profile_name(None, config)
        # Assert returns "default"
        pass
```

**Click Testing Pattern (for TypeScript dev):**
- `CliRunner` is like a test HTTP client - simulates CLI invocation
- `runner.invoke(cli, ['arg1', '--flag'])` simulates `barkup arg1 --flag`
- Check `result.exit_code` (0 = success, 1 = error, like process exit codes)
- Check `result.output` for stdout content

**Acceptance:** `uv run barkup --help` shows all commands, test suite passes, profile resolution works correctly.

---

#### Step 1.2: Implement `barkup init` Command
**Branch:** `feature/cli-init` (branched from `feature/cli-framework`)

**Reuse:** `src/config.py` has `init_config()` function (line 84) - already implemented, just needs CLI wrapper.

**Update:** `src/cli.py` - `init()` function:
```python
@cli.command()
def init():
    """Create default config file at user config location."""
    from config import init_config, get_user_config_path
    
    config_path = get_user_config_path()
    
    if config_path.exists():
        click.echo(f"Config file already exists at {config_path}")
        if not click.confirm("Overwrite?"):
            return
    
    init_config()
    click.echo(f"✓ Created config file at {config_path}")
    click.echo(f"\nEdit this file to configure your backup sources and destinations.")
    click.echo(f"Example: {config_path.parent / 'config.example.toml'}")
```

**Testing:** Add to `tests/test_cli.py`:
```python
class TestInitCommand:
    def test_creates_config_file(self, tmp_path, monkeypatch):
        # Mock get_user_config_path to return tmp_path location
        # Invoke init command
        # Assert config file created
        pass
    
    def test_prompts_before_overwriting_existing_config(self):
        # Create existing config
        # Invoke with input='n'
        # Assert file unchanged
        pass
```

**Acceptance:** `uv run barkup init` creates config file, shows helpful message, prompts before overwriting.

---

#### Step 1.3: Implement `barkup run` Command  
**Branch:** `feature/cli-run` (branched from feature/cli-init after merge to dev)

This command wraps the existing `run_barkup()` orchestrator but adds CLI-specific features.

**Reuse:** `src/barkup.py` - `run_barkup()` already implements the full backup flow.

**New behavior needed:**
1. `--name` flag to override profile in config
2. `--yes` flag to skip confirmation prompts (set dry_run=False temporarily)
3. Profile resolution using `resolve_profile_name()` helper
4. Better output formatting for CLI context
5. Exit codes: 0 = success, 1 = error, 2 = user cancelled

**Update:** `src/cli.py` - `run()` function:
```python
@cli.command()
@click.option('--name', help='Backup profile name (overrides config)')
@click.option('--yes', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def run(ctx, name, yes):
    """Run backup using config."""
    from barkup import run_barkup
    from config import load_config
    import sys
    
    config_path = ctx.obj.get('config_path')
    
    try:
        config = load_config(config_path)
        
        # Resolve profile name using three-tier fallback
        profile = resolve_profile_name(name, config)
        config.general.profile_name = profile
        
        # Disable dry_run if --yes flag provided
        if yes:
            config.general.dry_run = False
        
        click.echo(f"Running backup for profile: {profile}")
        stats = run_barkup(cli_path=config_path)
        
        click.echo(f"\n✓ Backup completed successfully")
        click.echo(f"  New files: {stats['new_files']}")
        click.echo(f"  Modified files: {stats['modified_files']}")
        click.echo(f"  Skipped (unchanged): {stats['skipped_files']}")
        sys.exit(0)
        
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nBackup cancelled by user")
        sys.exit(2)
```

**Update:** `src/barkup.py` - `run_barkup()` function:
Current implementation doesn't return meaningful status. Change return type:
```python
def run_barkup(cli_path: Path | None = None) -> dict:
    """Run backup and return summary statistics."""
    # ... existing code ...
    
    # After backup completes, before closing connection:
    return {
        'files_backed_up': len(new) + len(modified),
        'new_files': len(new),
        'modified_files': len(modified),
        'skipped_files': unchanged_count
    }
```

**Testing:** Add to `tests/test_cli.py`:
```python
class TestRunCommand:
    def test_runs_backup_successfully(self, tmp_path):
        # Create valid config
        # Invoke run command
        # Assert exit_code == 0
        pass
    
    def test_yes_flag_skips_confirmation(self):
        # Config with dry_run=true
        # Invoke with --yes
        # Assert backup runs without prompt
        pass
    
    def test_name_flag_overrides_profile(self):
        # Config with profile_name="default"
        # Invoke with --name="custom"
        # Assert uses custom profile
        pass
    
    def test_uses_config_profile_when_no_name_flag(self):
        # Config with profile_name="myprofile"
        # Invoke without --name
        # Assert uses "myprofile"
        pass
    
    def test_defaults_to_default_profile(self):
        # Config without profile_name field
        # Invoke without --name
        # Assert uses "default"
        pass
    
    def test_keyboard_interrupt_exits_gracefully(self):
        # Mock KeyboardInterrupt during backup
        # Assert exit_code == 2
        pass
```

**Acceptance:** `uv run barkup run` executes backup with correct profile resolution, `--yes` skips prompts, `--name` overrides profile, exit codes correct.

---

#### Step 1.4: Implement `barkup list` Command
**Branch:** `feature/cli-list` (branched from `dev` after Step 1.3 merge)

Wraps the DB layer to list backed-up files.

**New behavior needed:**
1. `--name` flag to filter by a single profile
2. When `--name` is omitted, list **all** profiles (overview command, not just `"default"`)
3. Readable per-file output: source -> backup path, size, last-backup date
4. Friendly message when nothing has been backed up

**Update:** `src/database.py` - add `list_backups()`:
```python
def list_backups(conn, profile=None) -> list[sqlite3.Row]:
    if profile:
        return conn.execute(
            "SELECT * FROM backups WHERE profile = ? ORDER BY original_path",
            (profile,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM backups ORDER BY profile, original_path"
    ).fetchall()
```

**Update:** `src/cli.py` - `list_cmd()`:
```python
@cli.command("list")
@click.option("--name", help="Filter by profile name")
def list_cmd(name):
    """List all backed up files."""
    from database import open_connection, close_connection, list_backups

    conn = open_connection()
    try:
        rows = list_backups(conn, name)
    finally:
        close_connection(conn)

    if not rows:
        click.echo("No backups found.")
        return

    for row in rows:
        click.echo(f"{row['original_path']} -> {row['backup_path']}")
        click.echo(f"  {row['size']} bytes, backed up {row['last_backup']}")
```

**Testing:** Add to `tests/test_database.py` and `tests/test_cli.py`:
- `list_backups` returns all rows when `profile=None` and filters when given; respects profile isolation.
- `list` command prints each file; empty DB prints "No backups found."

**Acceptance:** `uv run barkup list` shows every backed-up file across profiles; `--name` scopes to one profile.

---

#### Step 1.5: Implement `barkup status` Command
**Branch:** `feature/cli-status` (branched from `dev` after Step 1.4 merge)

Shows backup statistics per profile.

**New behavior needed:**
1. `--name` flag to scope to one profile
2. When `--name` is omitted, show stats for **all** profiles
3. Per-profile: file count, total size, last-backup time
4. Human-readable size (a small `format_size()` helper may be added to `database.py` or a utils module)

**Update:** `src/database.py` - add `get_backup_stats()`:
```python
def get_backup_stats(conn, profile=None) -> dict:
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
```

**Update:** `src/cli.py` - `status()`:
```python
@cli.command()
@click.option("--name", help="Show stats for specific profile")
def status(name):
    """Show backup statistics."""
    from database import open_connection, close_connection, get_backup_stats

    conn = open_connection()
    try:
        stats = get_backup_stats(conn, name)
    finally:
        close_connection(conn)

    if not stats:
        click.echo("No backups found.")
        return

    for profile, s in stats.items():
        click.echo(f"Profile: {profile}")
        click.echo(f"  Files: {s['file_count']}")
        click.echo(f"  Total size: {s['total_size']} bytes")
        click.echo(f"  Last backup: {s['last_backup']}")
```

**Testing:**
- `get_backup_stats` returns per-profile aggregates; profile filter works; empty DB -> `{}`.
- `status` prints per-profile stats; empty DB prints "No backups found."

**Acceptance:** `uv run barkup status` shows file counts, total sizes, and last-backup times per profile; `--name` scopes.

---

#### Step 1.6: Implement `barkup verify` Command
**Branch:** `feature/cli-verify` (branched from `dev` after Step 1.5 merge)

Validates backup integrity: confirms the backup copy is intact AND flags stale sources.

**New behavior needed:**
1. `--name` flag to scope to one profile
2. When `--name` is omitted, verify **all** profiles
3. For each backup row, check `backup_path` exists and its hash matches the stored `hash` (copy integrity -> `MISSING`/`CORRUPT`)
4. Also re-hash the source `original_path`: if it differs from the stored `hash`, mark `STALE` (source changed since last backup)
5. Print `OK` / `MISSING` / `CORRUPT` / `STALE` per file plus a summary
6. Exit code `0` if everything is `OK`, `1` if any `MISSING`/`CORRUPT`/`STALE`

**Update:** `src/database.py` - add `verify_backups()`:
```python
def verify_backups(conn, profile=None) -> list[tuple[sqlite3.Row, str]]:
    rows = list_backups(conn, profile)
    results = []
    for row in rows:
        backup = Path(row["backup_path"])
        source = Path(row["original_path"])
        if not backup.exists():
            results.append((row, "missing"))
            continue
        if calculate_file_hash(backup) != row["hash"]:
            results.append((row, "corrupt"))
            continue
        if source.exists() and calculate_file_hash(source) != row["hash"]:
            results.append((row, "stale"))
            continue
        results.append((row, "ok"))
    return results
```

**Update:** `src/cli.py` - `verify()`:
```python
@cli.command()
@click.option("--name", help="Verify specific profile")
def verify(name):
    """Verify backup integrity."""
    import sys

    from database import open_connection, close_connection, verify_backups

    conn = open_connection()
    try:
        results = verify_backups(conn, name)
    finally:
        close_connection(conn)

    if not results:
        click.echo("No backups found.")
        sys.exit(0)

    problems = 0
    for row, status in results:
        click.echo(f"{status.upper()}: {row['original_path']}")
        if status != "ok":
            problems += 1
    click.echo(f"\n{len(results) - problems} OK, {problems} issue(s)")
    sys.exit(1 if problems else 0)
```

**Testing:**
- `verify_backups`: `ok` when copy matches and source unchanged; `missing` when backup absent; `corrupt` when copy hash differs; `stale` when source changed.
- `verify` command: prints each status; exit `0` when all `OK`; exit `1` when any problem.

**Acceptance:** `uv run barkup verify` reports intact/corrupt/missing/stale backups and returns a non-zero exit code when any issue exists; `--name` scopes.

---

**Note:** Steps 1.4-1.6 were deleted by the original planning agent and have been rediscovered and specified above (2026-07-17). They complete the read/inspect CLI commands (`list` / `status` / `verify`). Confirmed decisions: read commands show all profiles when `--name` is omitted; `verify` checks both backup-copy integrity and stale sources. Only after all CLI commands are implemented do we move to Phase 2.

### Phase 2: MVP Feature - Restore Functionality

#### Step 2.1: Implement Single File Restore
**Branch:** `feature/restore-single-file`

**Create:** `src/restore.py` (no existing equivalent found)
```python
from pathlib import Path
import shutil
from database import open_connection

def find_backup_path(original_path: str, profile: str | None = None) -> str | None:
    """Query database for backup location of a file."""
    conn = open_connection()
    cursor = conn.cursor()
    
    if profile:
        cursor.execute(
            "SELECT backup_path FROM backups WHERE original_path = ? AND profile = ?",
            (str(original_path), profile)
        )
    else:
        # No profile specified - find first match
        cursor.execute(
            "SELECT backup_path FROM backups WHERE original_path = ?",
            (str(original_path),)
        )
    
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else None

def restore_file(original_path: str, destination: str | None = None, profile: str | None = None) -> Path:
    """Restore a single file from backup.
    
    Args:
        original_path: Original file path (used to query database)
        destination: Custom restore location (default: original location)
        profile: Profile name to filter by
    
    Returns:
        Path where file was restored
    
    Raises:
        FileNotFoundError: If file not found in backup database or backup file missing
    """
    backup_path_str = find_backup_path(original_path, profile)
    
    if not backup_path_str:
        if profile:
            raise FileNotFoundError(f"File '{original_path}' not found in backup for profile '{profile}'")
        else:
            raise FileNotFoundError(f"File '{original_path}' not found in any backup")
    
    backup_path = Path(backup_path_str)
    
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file missing: {backup_path}")
    
    # Determine restore location
    if destination:
        restore_path = Path(destination)
    else:
        restore_path = Path(original_path)
    
    # Create parent directories if needed
    restore_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy file (preserving metadata)
    shutil.copy2(backup_path, restore_path)
    
    return restore_path
```

**Update:** `src/cli.py` - `restore()` function (single file case):
```python
@cli.command()
@click.argument('path', required=False)
@click.option('--to', 'destination', help='Restore to custom location')
@click.option('--all', 'restore_all', is_flag=True, help='Restore entire backup set')
@click.option('--name', help='Profile name')
def restore(path, destination, restore_all, name):
    """Restore files from backup."""
    from restore import restore_file, restore_all_files
    
    if restore_all:
        # Implementation in Step 2.2
        if not name:
            click.echo("Error: --name required with --all", err=True)
            raise SystemExit(1)
        
        click.echo(f"Restoring all files from profile '{name}'...")
        # TODO: Step 2.2
        return
    
    # Single file restore
    if not path:
        click.echo("Error: PATH argument required (or use --all)", err=True)
        raise SystemExit(1)
    
    try:
        restored_path = restore_file(path, destination, name)
        click.echo(f"✓ Restored {path}")
        click.echo(f"  → {restored_path}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
```

**Testing:** Add to `tests/test_restore.py`:
```python
class TestFindBackupPath:
    def test_finds_backup_path(self):
        # Insert database entry
        # Call find_backup_path()
        # Assert returns correct path
        pass
    
    def test_returns_none_when_not_found(self):
        pass
    
    def test_filters_by_profile(self):
        pass

class TestRestoreFile:
    def test_restores_to_original_location(self, tmp_path):
        # Create backup file and database entry
        # Call restore_file()
        # Assert file restored to original path
        pass
    
    def test_restores_to_custom_location(self, tmp_path):
        # Provide custom destination
        # Assert file restored to custom path
        pass
    
    def test_creates_parent_directories(self, tmp_path):
        pass
    
    def test_raises_when_backup_not_found(self):
        with pytest.raises(FileNotFoundError):
            restore_file('/nonexistent/file.txt')
    
    def test_raises_when_backup_file_missing(self):
        # Database entry exists but file deleted
        with pytest.raises(FileNotFoundError):
            restore_file('/test/file.txt')
```

**Acceptance:** `uv run barkup restore /path/to/file.txt` restores file, `--to` changes destination, errors handled gracefully.

---

#### Step 2.2: Implement Full Backup Restore
**Branch:** Same as 2.1 (`feature/restore-single-file`)

**Update:** `src/restore.py` - add `restore_all_files()`:
```python
def restore_all_files(profile: str, destination: str | None = None) -> dict:
    """Restore all files from a backup profile.
    
    Args:
        profile: Profile name to restore
        destination: Custom directory to restore into (preserves structure)
    
    Returns:
        Dict with 'restored' count and 'failed' list
    """
    conn = open_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT original_path, backup_path FROM backups WHERE profile = ?",
        (profile,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise ValueError(f"No backups found for profile '{profile}'")
    
    results = {'restored': 0, 'failed': []}
    
    for original_path, backup_path in rows:
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                results['failed'].append({
                    'path': original_path,
                    'error': 'Backup file missing'
                })
                continue
            
            # Determine restore location
            if destination:
                # Custom destination: preserve relative structure
                original = Path(original_path)
                # Use only filename for file sources, full path for directory sources
                # (same logic as backup - reuse the pattern)
                restore_path = Path(destination) / original.name
            else:
                restore_path = Path(original_path)
            
            restore_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, restore_path)
            results['restored'] += 1
            
        except Exception as e:
            results['failed'].append({
                'path': original_path,
                'error': str(e)
            })
    
    return results
```

**Update:** `src/cli.py` - `restore()` function (--all case):
```python
# In restore() function, replace TODO with:
    if restore_all:
        if not name:
            click.echo("Error: --name required with --all", err=True)
            raise SystemExit(1)
        
        try:
            results = restore_all_files(name, destination)

#### Step 3.5: Multi-Profile Management (Post-MVP)
**Branch:** `feature/multi-profile`

Add commands to manage multiple backup profiles more easily.

**Create:** `src/profile_manager.py` (no existing equivalent found)
```python
from database import open_connection

def list_profiles() -> list[dict]:
    """List all backup profiles in the database."""
    conn = open_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            profile,
            COUNT(*) as file_count,
            SUM(size) as total_size,
            MAX(last_backup) as last_backup
        FROM backups
        GROUP BY profile
        ORDER BY last_backup DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            'name': row[0],
            'file_count': row[1],
            'total_size': row[2],
            'last_backup': row[3]
        }
        for row in rows
    ]
```

**Update:** `src/cli.py` - add `profiles` command:
```python
@cli.command()
def profiles():
    """List all backup profiles."""
    from profile_manager import list_profiles
    from list_backups import format_size
    from datetime import datetime
    
    profiles_list = list_profiles()
    
    if not profiles_list:
        click.echo("No backup profiles found")
        return
    
    click.echo("Backup Profiles:")
    click.echo("=" * 70)
    
    for profile in profiles_list:
        click.echo(f"\n{profile['name']}")
        click.echo(f"  Files: {profile['file_count']}")
        click.echo(f"  Size: {format_size(profile['total_size'])}")
        if profile['last_backup']:
            timestamp = datetime.fromisoformat(profile['last_backup'])
            click.echo(f"  Last backup: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
```

**Testing:** Add to `tests/test_profile_manager.py`:
```python
class TestListProfiles:
    def test_lists_all_profiles(self):
        # Insert data for multiple profiles
        # Call list_profiles()
        # Assert returns all profiles with correct stats
        pass
    
    def test_returns_empty_when_no_profiles(self):
        # Empty database
        # Assert returns empty list
        pass
```

**Acceptance:** `uv run barkup profiles` lists all backup profiles with statistics, helps users manage multiple profiles easily.

---

            
            click.echo(f"✓ Restored {results['restored']} files from profile '{name}'")
            
            if destination:
                click.echo(f"  → {destination}")
            
            if results['failed']:
                click.echo(f"\n⚠ Failed to restore {len(results['failed'])} files:")
                for item in results['failed']:
                    click.echo(f"  - {item['path']}: {item['error']}")
                raise SystemExit(1)
                
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
        
        return
```

**Testing:** Add to `tests/test_restore.py`:
```python
class TestRestoreAllFiles:
    def test_restores_all_files_in_profile(self, tmp_path):
        # Create multiple backup files and database entries
        # Call restore_all_files()
        # Assert all files restored
        pass
    
    def test_restores_to_custom_directory(self, tmp_path):
        # Provide destination
        # Assert files restored to custom location with structure preserved
        pass
    
    def test_continues_on_individual_file_errors(self, tmp_path):
        # Some backup files missing
        # Assert continues and reports failures
        pass
    
    def test_raises_when_profile_not_found(self):
        with pytest.raises(ValueError):
            restore_all_files('nonexistent')
```

**Acceptance:** `uv run barkup restore --all --name mybackup` restores all files, `--to` changes destination, partial failures reported.

---

### Phase 3: Nice-to-Have Features

#### Step 3.1: Make Barkup Installable (PyPI-ready)
**Branch:** `feature/packaging`

**Update:** `pyproject.toml` - add build system and metadata:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
# ... existing metadata ...
readme = "README.md"
keywords = ["backup", "cli", "incremental", "google-drive"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: System :: Archiving :: Backup",
]

[project.urls]
Homepage = "https://github.com/[username]/barkup"
Issues = "https://github.com/[username]/barkup/issues"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

**Why hatchling:** Modern, minimal build backend. Alternative to setuptools. Zero configuration for simple packages.

**Testing installation:**
```bash
# Build distribution
uv run python -m build

# Install locally in editable mode
uv pip install -e .

# Test installed command
barkup --help

# Uninstall
uv pip uninstall barkup
```

**Acceptance:** `uv pip install -e .` installs successfully, `barkup` command available globally, `python -m build` creates wheel/sdist.

---

#### Step 3.1b: CD - Automated PyPI Publish (Release Workflow)
**Branch:** `feature/packaging` (same as 3.1)

Build and publish is **Continuous Deployment (CD)**, distinct from the CI
pipeline added in Step 0.3. It runs only on tagged releases, not on every PR,
so it never blocks normal development.

**Create:** `.github/workflows/release.yml`
```yaml
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    name: Build and publish to PyPI
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Build distribution
        run: uv build
      - name: Publish to PyPI
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}
        run: uv publish
```

**Prerequisites:** Requires the `[build-system]` (hatchling) added in Step 3.1 so
`uv build` can produce wheel + sdist, and a `PYPI_TOKEN` repository secret.

**Acceptance:** Pushing a `v*` tag builds the distribution and publishes it to
PyPI; CI (Step 0.3) remains the gate for PRs into `dev`/`main`.

---

#### Step 3.2: Write Comprehensive README
**Branch:** Same as 3.1 (`feature/packaging`)

**Update:** `README.md` - populate with full documentation.

Structure (from spec.md):
1. Project Description
   - What Barkup is
   - Key features (incremental, SHA256, exclude patterns, dry-run)
   - Why it exists (simple, config-driven backups)

2. Installation
   ```bash
   # From source
   git clone https://github.com/[username]/barkup
   cd barkup
   uv pip install -e .
   
   # Future: From PyPI
   pip install barkup
   ```

3. Quick Start
   ```bash
   # Create config file
   barkup init
   
   # Edit config
   nano ~/.config/barkup/config.toml
   
   # Run first backup
   barkup run
   
   # List backed up files
   barkup list
   ```

4. Configuration
   - Config file locations and precedence
   - Example config with all sections explained
   - Inheritance pattern (general → local/cloud)
   - Exclude patterns examples

5. Commands Reference
   - `barkup init` - Create default config
   - `barkup run` - Run backup
   - `barkup list` - List backups
   - `barkup status` - Show statistics
   - `barkup verify` - Verify integrity
   - `barkup restore` - Restore files
   Include all flags and options

6. Development
   - Python 3.12+ required
   - uv package manager
   - Run tests: `uv run pytest -v`
   - Run app: `./main.sh` or `uv run src/main.py`

7. License
   - MIT License link

**Acceptance:** README.md complete, covers all implemented features, includes examples.

---

#### Step 3.3: Implement Compression (ZIP)
**Branch:** `feature/compression`

This is a post-MVP enhancement. Only implement if time allows after core MVP is solid.

**Smart compression logic:**
- Skip already-compressed formats: `.zip`, `.gz`, `.bz2`, `.xz`, `.7z`, `.rar`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.mp4`, `.avi`, `.mov`, `.mp3`, `.flac`
- Compress everything else when `compression = true` in config

**Create:** `src/compression.py`
```python
from pathlib import Path
import zipfile

COMPRESSED_EXTENSIONS = {
    '.zip', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.mp4', '.avi', '.mov', '.mkv', '.webm',
    '.mp3', '.flac', '.ogg', '.m4a'
}

def should_compress(file_path: Path) -> bool:
    """Check if file should be compressed based on extension."""
    return file_path.suffix.lower() not in COMPRESSED_EXTENSIONS

def compress_files(files: list[Path], output_path: Path) -> Path:
    """Compress files into a ZIP archive."""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            zipf.write(file, arcname=file.name)
    
    return output_path
```

**Update:** `src/barkup.py` - integrate compression in `barkup_file()`:
- Check if compression enabled in config
- Check if file should be compressed
- Compress before copying if needed
- Store compressed file instead of original
- Update database with `.zip` extension

**Note:** This adds complexity to restore logic - needs to detect and decompress ZIP files during restore.

**Acceptance:** Files compressed when enabled, already-compressed formats skipped, restore handles compressed files.

---

#### Step 3.4: Google Drive Integration (Future)
**Branch:** `feature/google-drive`

This is a significant enhancement requiring OAuth, API integration, and error handling. Out of scope for initial MVP.

**Dependencies needed:**
```bash
uv add google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

**Key components:**
- OAuth 2.0 authentication flow
- Token storage and refresh
- Upload API integration
- Large file handling (>10MB warnings)
- Sync detection (compare Drive vs local state)
- Network error handling and retries

**Defer until:** MVP complete and working reliably.

---

## Critical Files & Anchors

1. **`src/barkup.py`** (lines 37-94) - `run_barkup()` orchestrator
   - Currently returns None, needs to return dict with stats for CLI
   - All new CLI features wrap this function

2. **`src/database.py`** - Database operations
   - `open_connection()` returns connection, used by all new features
   - Schema already includes `profile` field for multi-profile support
   - All query functions in new modules follow this pattern

3. **`src/config.py`** (line 84) - `init_config()` function
   - Already implemented, reuse for `barkup init` command
   - Copies from `config.example.toml` to user config path

4. **`tests/test_database.py`** - Testing patterns reference
   - `_memory_connection()` helper at top of file - reuse for all database tests
   - Class-based organization pattern to follow

5. **`pyproject.toml`** - Package metadata
   - Add `[project.scripts]` for CLI entry point
   - Add `[build-system]` for installability
   - Dependencies already minimal and correct

## Verification

### Phase 0 Verification:
```bash
# Run tests - should see 50+ passing
uv run pytest -v

# Check coverage of new test files
ls tests/test_exclude_patterns.py tests/test_dry_run.py tests/test_config_resolvers.py tests/test_main.py
```

### Phase 1 Verification (CLI Commands):
```bash
# Test CLI structure
uv run barkup --help
# Should list: init, run, list, status, verify, restore

# Test init command
rm -f ~/.config/barkup/config.toml
uv run barkup init
# Should create config file

# Test run command (after editing config with test paths)
uv run barkup run
# Should show preview and run backup

# Test list command
uv run barkup list
# Should show backed up files

# Test status command
uv run barkup status
# Should show statistics

# Test verify command
uv run barkup verify
# Should verify all files OK

# Test restore command
echo "test content" > /tmp/test-restore.txt
uv run barkup run  # Backup it first
rm /tmp/test-restore.txt
uv run barkup restore /tmp/test-restore.txt
cat /tmp/test-restore.txt
# Should contain "test content"
```

### Phase 2 Verification (Restore):
```bash
# Create test backup
mkdir -p /tmp/barkup-test/{src,backup}
echo "file1" > /tmp/barkup-test/src/file1.txt
echo "file2" > /tmp/barkup-test/src/file2.txt

# Configure barkup to backup /tmp/barkup-test/src to /tmp/barkup-test/backup
# Run backup
uv run barkup run

# Delete source files
rm -rf /tmp/barkup-test/src

# Restore single file
uv run barkup restore /tmp/barkup-test/src/file1.txt
cat /tmp/barkup-test/src/file1.txt
# Should show "file1"

# Restore all files
rm -rf /tmp/barkup-test/src
uv run barkup restore --all --name default
ls /tmp/barkup-test/src
# Should show file1.txt and file2.txt
```

### Phase 3 Verification (Packaging):
```bash
# Build package
python -m build
ls dist/
# Should show .whl and .tar.gz files

# Install in new venv
python -m venv test-venv
source test-venv/bin/activate
pip install dist/barkup-*.whl
barkup --help
# Should work without uv run prefix

# Verify all commands work
barkup init
barkup run
barkup list
# etc.
```

## Assumptions & Contingencies

1. **Assumption:** Click is the preferred CLI framework over argparse
   - **Rationale:** Better DX for junior dev from TypeScript background (decorator syntax familiar)
   - **Contingency:** If Click causes issues, switch to argparse (standard library, no dependency)

2. **Assumption:** Unit tests are sufficient for MVP phase
   - **Rationale:** Fast feedback, good ROI for CLI tool
   - **Contingency:** If bugs found in command workflows, add integration tests using CliRunner fixtures that exercise full command pipelines

3. **Assumption:** Hatchling is acceptable build backend
   - **Rationale:** Modern, zero-config for simple packages
   - **Contingency:** If issues arise, switch to setuptools (more mature, wider support)

4. **Assumption:** Phase order is strictly followed (0 → 1 → 2 → 3)
   - **Rationale:** Each phase builds on previous, tests ensure stability
   - **Contingency:** If a phase blocks (complex bug, missing requirement), skip to next independent phase and return later

5. **Assumption:** Google Drive integration deferred until post-MVP
   - **Rationale:** Complex OAuth flow, API rate limits, network errors add significant scope
   - **Contingency:** If user needs cloud backup urgently, implement simple FTP/SFTP as interim solution (much simpler than Drive API)

6. **Assumption:** Compression is optional nice-to-have
   - **Rationale:** Adds complexity to backup and restore, many files already compressed
   - **Contingency:** If storage space is critical issue, prioritize compression before packaging

7. **Assumption:** Single profile used in most commands (--name optional)
   - **Rationale:** Most users will have one backup profile
   - **Contingency:** If multi-profile usage common, make --name required for all commands and add `barkup profiles` command to list available profiles
