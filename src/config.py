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
    """Resolve all config paths in priority order (lowest to highest)"""
    paths = []

    sys_path = Path("/etc/barkup/config.toml")
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

def init_config(force: bool = False) -> Path:
    """Initialize default config in user config directory"""
    config_path = get_user_config_path()
    config_path_exists = config_path.exists()

    if config_path_exists and not force:
        raise FileExistsError(f"Config file already exists at '{config_path}'. Use --force to overwrite.")
    
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # default config
    default_config = f"""# Barkup Configuration File

[general]
# fields specific to this section
profile_name = "default"
dry_run = false

# 'sources', 'compression', and 'exclude' defined here
# serve as fallbacks for [local] and [[cloud_providers]]
# if they don't define their own.
sources = ["{Path.home()}"]
compression = false
exclude = ["*.tmp", ".git", "node_modules"]

[local]
# field specific to this section
destination = "{Path.home() / "Backups"}"

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
        
def update_config_runtime(config: dict, path: str, value: Any) -> None:
    """
    Update config value at runtime.
    
    Example: 
    barkup --compression=false
    update_config_runtime(config, "--compression=false", True)
    """
    pass

def set_config_section_infile(config: dict, section: str) -> None:
    """
    Docstring for set_config_section_infile
    
    :param config: Description
    :type config: dict
    :param section: Description
    :type section: str

    dev_deps: tomli_w
    """
    pass