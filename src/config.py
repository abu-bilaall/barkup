"""
config file handling for barkup.
supports layered config: system -> user -> cwd -> cli
"""

import os
from pathlib import Path
import tomllib
from typing import Any

def get_user_config_path() -> Path:
    """Get platform-specific user config path"""
    if os.name == "nt": # Windows
        base = Path(os.getenv("APPDATA", str(Path.home())))
        return base / "barkup" / "config.toml"
    else: # Unix-like (Linux, macOS)
        xdg = os.getenv("XDG_CONFIG_HOME")  
        if xdg:
            return Path(xdg) / "barkup" / "config.toml"
        return Path.home() / ".config" / "barkup" / "config.toml"

def resolve_config_paths(cli_path: Path | None = None) -> list[Path]:
    """Resolve all config paths in priority ordered lowest to highest"""
    paths = []

    sys_path = Path("/etc/barkup/config.toml")
    user_path = get_user_config_path()
    project_path = Path.cwd() / "barkup.config.toml"

    # Lowest priority first
    if sys_path.exists():
        paths.append(sys_path)

    if user_path.exists():
        paths.append(user_path)

    if project_path.exists():
        paths.append(project_path)

    if cli_path:
        if not  cli_path.exists():
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
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result

def load_config(cli_path: Path | None = None) -> dict:
    """Load and merge config from all sources"""
    config: dict = {}
    paths = resolve_config_paths(cli_path)

    if not paths:
        raise FileNotFoundError(f"No config file was found. Run 'barkup init' to create one.")

    for path in paths:
        try:
            with open(path, "rb") as f:
                parsed = tomllib.load(f)
                config = deep_merge(config, parsed)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {path}: {e}")
    
    return config

