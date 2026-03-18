"""Configuration loading utilities."""

import json
import os
from pathlib import Path

from liberty_max.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path.

    Respects the LIBERTY_MAX_CONFIG environment variable, falling back to
    config.json in the current working directory.
    """
    return Path(os.environ.get("LIBERTY_MAX_CONFIG", "config.json"))


def get_data_dir() -> Path:
    """Get the liberty-max data directory."""
    from liberty_max.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file, expanding ${VAR} references from the environment.

    String values in the JSON file that match the ${VAR_NAME} pattern are replaced
    with the corresponding environment variable at load time. This keeps secrets out
    of the config file itself — store them as plain environment variables and
    reference them in config.json using ${VAR_NAME} syntax.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(os.path.expandvars(raw))
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
