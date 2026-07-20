# Barkup

[![CI](https://github.com/abu-bilaall/barkup/actions/workflows/ci.yml/badge.svg)](https://github.com/abu-bilaall/barkup/actions/workflows/ci.yml)

Barkup is a Python-based CLI tool for automating personal backups to local and cloud storage (Google Drive), with incremental, hash-checked copies and a config-driven workflow.

<!-- TODO: add a demo GIF/screenshot here once the tool is fully working -->

## Motivation

Barkup started because I needed a reliable way to automatically back up the photos from my final year at university — and the ones I'll keep taking at conferences and elsewhere — to somewhere safe like Google Drive. I soon realized the same approach covers my eBooks and other files too. Barkup is the result: a small, config-driven CLI I built for myself, and my first personal project on boot.dev.

## Quick Start

```bash
# Clone and install
git clone https://github.com/abu-bilaall/barkup
cd barkup
uv sync

# Scaffold a config, then edit it
uv run barkup init
# writes ~/.config/barkup/config.toml (see config.example.toml for all options)

# Run your first backup
uv run barkup run

# List what's backed up
uv run barkup list
```

Once installed, the `barkup` command is available via `uv run barkup`. You can also install the console script directly (`uv pip install -e .`), or install from PyPI once published (`pip install barkup`).

## Usage

### Configuration

Barkup loads and deep-merges config from these locations, **lowest to highest priority**:

1. `/etc/barkup/config.toml` (system)
2. `~/.config/barkup/config.toml` (user; respects `XDG_CONFIG_HOME`)
3. `./barkup.config.toml` (current directory)
4. `--config <PATH>` (CLI flag — highest priority)

A minimal config:

```toml
[general]
profile_name = "default"
dry_run = false
sources = ["/home/you/Documents", "/home/you/Pictures"]
compression = false
exclude = ["*.tmp", ".git", "node_modules"]

[local]
destination = "/mnt/backups"
exclude = [".tmp*"]

[[cloud_providers]]
provider = "google_drive"
enabled = false
# credentials_file = "/home/you/.barkup/google_drive.json"
# remote_folder = "Backups/Barkup"
```

- `[general]` sets defaults for `sources`, `compression`, and `exclude`.
- `[local]` and `[[cloud_providers]]` override those defaults; their `exclude` lists **merge and deduplicate** with the general list.
- `compression` is a placeholder for the upcoming ZIP feature.
- See `config.example.toml` in the repo for the full annotated example (including `[advanced] temp_dir`).

### Commands

Global option: `--config <PATH>` (use a custom config file for any command).

| Command | Options | Description |
| --- | --- | --- |
| `barkup init` | `--force` | Create the default config at the user config path (overwrite with `--force`). |
| `barkup run` | `--name <PROFILE>`, `--yes` | Run a backup. `--name` selects the profile; `--yes` skips the confirmation prompt (for automation/cron). |
| `barkup list` | `--name <PROFILE>` | List backed-up files (original path, backup path, size, last backup). Filter by profile. |
| `barkup status` | `--name <PROFILE>` | Show backup statistics for a profile (or all profiles). |
| `barkup verify` | `--name <PROFILE>` | Recalculate hashes and compare with stored state; reports OK / missing / mismatched. Exits non-zero if any problem is found. |
| `barkup restore <path>` | `--to <DEST>`, `--all`, `--name <PROFILE>` | Restore a single file (or `--all` for the whole set). `--to` restores to a custom location (preserves directory structure); `--name` selects the profile. `--all` requires `--name`. |

Examples:

```bash
uv run barkup run --name default --yes
uv run barkup restore /mnt/backups/Documents/notes.txt --to ~/restore
uv run barkup restore --all --name default --to ~/restore-all
uv run barkup verify
```

## How I use Barkup

I run Barkup unattended as a scheduled job (cron) rather than by hand. My setup:

1. `barkup init` to scaffold `~/.config/barkup/config.toml`.
2. Point `[general].sources` at `~/Pictures` and `~/Documents`; set `[local].destination` to an external drive; enable the `google_drive` provider with a credentials file and a `remote_folder`.
3. Run it daily via cron with `barkup run --yes` — the `--yes` flag skips the confirmation prompt so it runs non-interactively.

The config is the single source of truth, so adjust sources, destinations, and schedule to taste.

## Contributing

- Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).
- Install dev dependencies and run tests:

  ```bash
  uv sync
  uv run pytest -v
  ```

- Lint/format: `uv run ruff check .` and `uv run black --check .`.
- Run the app during development: `./main.sh` or `uv run src/main.py`.
- Workflow: feature branches are opened against `dev`; PR titles follow `[Feature NN] - <summary>` (see `.github/PULL_REQUEST_TEMPLATE.md`). Keep changes focused and tests deterministic.

## License

Released under the [MIT License](LICENSE).
