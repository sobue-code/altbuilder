import os
import getpass
from pathlib import Path
import tomli

# import tomllib as tomli
from ..utils.logger import logger
from ..exceptions import ConfigError

USER_CONFIG_DIR = Path.home() / ".altbuilder"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.toml"
DEFAULT_CONFIG_FILE = Path(__file__).parent / "default_config.toml"


def _get_username():
    """Return the current user name without requiring a controlling terminal."""
    return getpass.getuser()


def load_config(config_file=None):
    """Load configuration from file or default."""
    config = {}
    config_file = Path(config_file or USER_CONFIG_FILE)
    if config_file.exists():
        try:
            with open(config_file, "rb") as f:
                config = tomli.load(f) or {}
            config["config_file"] = str(config_file)
        except Exception as e:
            logger.error(f"Failed to load {config_file}: {e}")
            raise ConfigError(f"Invalid configuration file: {e}")
    else:
        try:
            with open(DEFAULT_CONFIG_FILE, "rb") as f:
                config = tomli.load(f) or {}
            config["config_file"] = str(DEFAULT_CONFIG_FILE)
        except Exception as e:
            logger.error(f"Failed to load default config: {e}")
            raise ConfigError(f"Cannot load default config: {e}")

    # Expand placeholders in config values
    username = _get_username()
    home_dir = str(Path.home())

    def expand_placeholders(value):
        """Recursively expand placeholders in config values."""
        if isinstance(value, str):
            return value.replace("<user>", username).replace("~", home_dir)
        elif isinstance(value, dict):
            return {k: expand_placeholders(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [expand_placeholders(item) for item in value]
        return value

    config = expand_placeholders(config)

    # Validate and set defaults
    config.setdefault("base_dir", str(USER_CONFIG_DIR))
    config.setdefault(
        "environment_dir",
        config.get("environment_dir", os.path.join(config["base_dir"], "environments")),
    )
    config.setdefault("build_logs_dir", os.path.join(config["base_dir"], "builds"))
    config.setdefault("branch", "Sisyphus")
    config.setdefault("arch", "x86_64")
    config.setdefault("mirror", "http://ftp.altlinux.org/pub/distributions")
    config.setdefault("mirror_task", "http://git.altlinux.org")
    config.setdefault("rdb_url", "https://rdb.altlinux.org")
    config.setdefault("packager", f"{username} <{username}@altlinux.org>")
    config.setdefault(
        "logging",
        {
            "level": "INFO",
            "file_level": "DEBUG",
            "rotation": "10 MB",
            "format": "{time} | {level} | {message}",
        },
    )

    # Validate logging configuration
    valid_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
    if config["logging"]["level"] not in valid_levels:
        raise ConfigError(f"Invalid logging level: {config['logging']['level']}")
    if config["logging"]["file_level"] not in valid_levels:
        raise ConfigError(
            f"Invalid file logging level: {config['logging']['file_level']}"
        )

    # Ensure directories are writable
    for key in ["base_dir", "build_logs_dir", "environment_dir"]:
        dir_path = os.path.abspath(config[key])
        os.makedirs(dir_path, exist_ok=True)
        if not os.access(dir_path, os.W_OK):
            raise ConfigError(f"Directory {dir_path} is not writable")
        config[key] = dir_path

    return config


def get_sandbox_config(sandbox_name, config, branch=None, arch=None):
    """Get configuration specific to a sandbox."""
    defaults = {
        "branch": branch or config["branch"],
        "arch": arch or config["arch"],
        "mirror": config["mirror"],
        "mirror_task": config["mirror_task"],
        "rdb_url": config["rdb_url"],
        "packager": config["packager"],
        "base_dir": config["base_dir"],
        "environment_dir": config["environment_dir"],
        "build_logs_dir": config["build_logs_dir"],
    }
    if not branch and not arch:
        sandbox_config = config.get("sandboxes", {}).get(sandbox_name, {})
        defaults.update(sandbox_config)
    return defaults


class ConfigError(Exception):
    pass
