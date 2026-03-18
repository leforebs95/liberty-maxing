"""Configuration loading utilities."""

import json
import os
from pathlib import Path

from pydantic_settings import EnvSettingsSource, SettingsConfigDict

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
    Load configuration from file, with environment variables taking precedence.

    Reads structure and non-secret values from the JSON config file. Any field
    can be overridden via environment variables using the NANOBOT_ prefix and
    double-underscore nesting (e.g. NANOBOT_PROVIDERS__ANTHROPIC__API_KEY).

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    # Read and normalize the JSON file to snake_case via a pydantic round-trip.
    # This ensures keys are consistent with what EnvSettingsSource produces so
    # that deep_update correctly merges values and env vars can override file values.
    file_data: dict = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            file_data = Config.model_validate(raw).model_dump()
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    class _Config(Config):
        model_config = SettingsConfigDict(
            env_prefix="NANOBOT_",
            env_nested_delimiter="__",
            populate_by_name=True,
        )

        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
            # env vars have higher priority than JSON file data (passed as init kwargs)
            return (EnvSettingsSource(settings_cls), init_settings)

    try:
        return _Config(**file_data)
    except Exception as e:
        print(f"Warning: Failed to load config: {e}")
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
