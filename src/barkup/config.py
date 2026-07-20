"""
config file handling for barkup.
supports layered config: system -> user -> cwd -> cli
"""

import os
from pathlib import Path
import tomllib
from barkup.config_models import BarkupConfig
from barkup.config_resolvers import ResolvedLocalConfig
from dataclasses import fields
import sys


def get_user_config_path() -> Path:
    """Get platform-specific user config path"""
    if os.name == "nt":  # Windows
        base = Path(os.getenv("APPDATA", str(Path.home())))
        return base / "barkup" / "config.toml"
    else:  # Unix-like (Linux, macOS)
        xdg = os.getenv("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "barkup" / "config.toml"
        return Path.home() / ".config" / "barkup" / "config.toml"


def get_sys_config_path() -> Path:
    """Get platform-specific system config path"""
    if os.name == "nt":
        base = Path(os.getenv("PROGRAMDATA", "C:\\ProgramData"))
    else:
        base = Path("/etc")

    return base / "barkup" / "config.toml"


def resolve_config_paths(cli_path: Path | None = None) -> list[Path]:
    """Resolve all config paths in priority order (lowest to highest)"""
    paths = []

    sys_path = get_sys_config_path()
    user_path = get_user_config_path()
    cwd_path = Path.cwd() / "barkup.config.toml"

    # Lowest priority first
    if sys_path.exists():
        paths.append(sys_path)

    if user_path.exists():
        paths.append(user_path)

    if cwd_path.exists():
        paths.append(cwd_path)

    if cli_path:
        if not cli_path.exists():
            raise FileNotFoundError(f"Config file not found: {cli_path}")
        paths.append(cli_path)

    return paths


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override dict into base dict.
    Override values take precedence.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_config(cli_path: Path | None = None) -> BarkupConfig:
    """Load and merge config from all sources"""
    raw_config: dict = {}
    paths = resolve_config_paths(cli_path)

    if not paths:
        raise FileNotFoundError(
            "No config file was found. Run 'barkup init' to create one."
        )

    for path in paths:
        try:
            with open(path, "rb") as f:
                parsed = tomllib.load(f)
                raw_config = deep_merge(raw_config, parsed)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {path}: {e}")

    return BarkupConfig(**raw_config)


def init_config(force: bool = False) -> Path:
    """Initialize default config in user config directory"""
    config_path = get_user_config_path()
    config_path_exists = config_path.exists()

    if config_path_exists and not force:
        raise FileExistsError(
            f"Config file already exists at '{config_path}'. Use --force to overwrite."
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # default config
    default_config = """# Barkup Configuration File
# Edit the values below, then run: barkup run

[general]
# fields specific to this section
profile_name = "default"
dry_run = false

# Set the paths you want to back up here (files or directories).
# Leave as an empty list until configured -- `barkup run` will remind you.
sources = []

# 'compression' and 'exclude' defined here serve as fallbacks for
# [local] and [[cloud_providers]] if they don't define their own.
compression = false
exclude = ["*.tmp", ".git", "node_modules"]

[local]
# Where backups are written. Must be set and must NOT be inside a source.
destination = ""

[[cloud_providers]]
# check the docs for more about this section
provider = "google_drive"
enabled = false
"""

    config_path.write_text(default_config)

    if config_path_exists:
        print(f"Config file overwritten at '{config_path}'.")
    else:
        print(f"Config file written at '{config_path}'.")

    return config_path


def update_config_runtime(config: ResolvedLocalConfig, cmdStr: str) -> None:
    """
    Update config value at runtime.

    Example:
    barkup --compression=false
    """
    field, value = cmdStr.lstrip("-").split("=", 1)
    configFields = [f.name for f in fields(config)]
    if field not in configFields:
        print(f"{field} is not a valid config field.")
        sys.exit(0)

    setattr(config, field, value)
