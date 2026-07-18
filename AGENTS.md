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
5. When a task is complete, ask the user whether to commit, push, and open a PR.
   - Base branch: check rather than assume. Inspect branch naming and recent merge
     targets, or ask the user which branch the PR should target.
   - Commits: use Conventional Commits (e.g. `feat(cli): add X`), keep the subject
     under 72 chars, keep the message simple (subject + short body is fine), and never
     add AI/agent attribution or "Generated with ..." lines. Prefer focused, atomic commits.
   - PR drafting skill: look for the `pr-creator` skill in the location where skills are
     configured for this agent. If it is found there, use it; if not, ask the user where it is.
   - PR template: first look for the template in the same directory as the skill; if it is
     not there, check the project (e.g. `.github/PULL_REQUEST_TEMPLATE.md`); if still not
     found, ask the user. Use that template as the body format, put the title only in the
     PR title argument (do not duplicate it in the body), and list only the "Type of Change"
     options that apply. Follow the template's `title:` convention, e.g. `[Feature 05] - <summary>`.
   - Show the user the title, the filled body, and the `gh pr create --base <branch> ...`
     command, then wait for explicit approval before pushing or creating the PR.

6. When wrapping up a feature branch before starting the next step:
   - Return to the base branch (e.g. `dev`) and branch off it for the next step.
   - Use this wrap-up workflow. The first three steps are the user's responsibility;
     the agent must remind/urge the user to complete them and must not merge without approval:
     1. User reviews the PR.
     2. User reviews the changes.
     3. User makes any last corrections.
     4. After the above, the agent squash-merges the branch into the base branch as a single
        commit whose message summarizes the branch deliverables and references the PR number
        (e.g. `#7`). The agent must get explicit approval for both the squash-merge and the
        commit message before executing.
     5. After the squash-merge is pushed and the PR is closed, the agent deletes the
        feature branch both locally (`git branch -d <branch>`) and remotely
        (`git push origin --delete <branch>`). The agent must get explicit approval
        before deleting the branch.
   - Keep plan/roadmap-specific wording out of version control. References to internal
     plan steps, phases, or roadmap coordinates (e.g. "Step 1.1", "Phase 0", "Step 0.3")
     must not appear in commit messages, PRs, code comments, or docs, because future
     contributors cannot verify them once the plan file is removed from the repo.
     Describe work by what it delivers, not by where it sits in the plan.

### Testing Patterns
- Write tests for all new functionality
- Tests must be deterministic and isolated
- For unit tests, mock all dependencies.
- The tests for a particular task must pass before you mark it as complete
