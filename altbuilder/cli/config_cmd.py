import os
import getpass
import subprocess
import click
import tomli
import tomli_w
from pathlib import Path
from ..config import load_config, USER_CONFIG_DIR, USER_CONFIG_FILE, DEFAULT_CONFIG_FILE
from ..utils.logger import logger
from ..utils.helpers import colorize
from ..exceptions import ConfigError


def display_config(config):
    """Display the configuration in a clean, colorized format."""
    output = []

    # Header
    config_file = config.get("config_file", str(USER_CONFIG_FILE))
    output.append(colorize(f"altbuilder Configuration", bold=True, color="cyan"))
    output.append(colorize(f"File: {config_file}", color="green"))
    output.append("")

    # Global Settings
    output.append(colorize("Global Settings:", bold=True, color="yellow"))
    global_keys = [
        "branch",
        "arch",
        "mirror",
        "packager",
        "base_dir",
        "environment_dir",
        "build_logs_dir",
    ]
    for key in global_keys:
        if key in config:
            output.append(
                f"  {colorize(key.capitalize(), color='cyan')}: "
                f"{colorize(str(config[key]), color='white')}"
            )

    # Logging Settings
    output.append("")
    output.append(colorize("Logging:", bold=True, color="yellow"))
    if "logging" in config:
        logging = config["logging"]
        for key in ["level", "file_level", "rotation", "format"]:
            if key in logging:
                output.append(
                    f"  {colorize(key.capitalize(), color='cyan')}: "
                    f"{colorize(str(logging[key]), color='white')}"
                )

    # Sandboxes
    if config.get("sandboxes"):
        output.append("")
        output.append(colorize("Sandboxes:", bold=True, color="yellow"))
        for sandbox, settings in config["sandboxes"].items():
            output.append(f"  {colorize(sandbox, color='cyan', bold=True)}:")
            for key, value in settings.items():
                output.append(
                    f"    {colorize(key.capitalize(), color='cyan')}: "
                    f"{colorize(str(value), color='white')}"
                )

    # Footer with usage hint
    output.append("")
    output.append(
        colorize(
            "Tip: Use 'altbuilder config --edit' to modify or "
            "'altbuilder config --init' to generate a new config.",
            color="green",
        )
    )

    return "\n".join(output)


def generate_user_config():
    """Generate a user-specific default configuration."""
    username = getpass.getuser()
    # Capitalize username for packager name (e.g., "user" -> "User")
    packager_name = username.capitalize()
    packager_email = f"{username}@altlinux.org"

    base_dir = f"/tmp/.private/{username}/altbuilder"
    build_logs_dir = f"/home/{username}/.altbuilder/builds"
    # Ensure the base directory is writable
    os.makedirs(base_dir, exist_ok=True)
    if not os.access(base_dir, os.W_OK):
        raise ConfigError(f"Directory {base_dir} is not writable")

    config = {
        "branch": "Sisyphus",
        "arch": "x86_64",
        "mirror": "http://ftp.altlinux.org/pub/distributions",
        "packager": f"{packager_name} <{packager_email}>",
        "base_dir": base_dir,
        "environment_dir": os.path.join(base_dir, "environments"),
        "build_logs_dir": build_logs_dir,
        "logging": {
            "level": "ERROR",
            "file_level": "DEBUG",
            "rotation": "10 MB",
            "format": "{time} | {level} | {message}",
        },
        "sandboxes": {
            "Sisyphus-x86_64": {"mirror": "http://ftp.altlinux.org/pub/distributions"}
        },
    }

    return config


def ensure_config_file(force=False):
    """Ensure the config file exists, initializing with user-specific defaults if necessary."""
    if not USER_CONFIG_FILE.exists():
        config = generate_user_config()
        try:
            os.makedirs(USER_CONFIG_DIR, exist_ok=True)
            with open(USER_CONFIG_FILE, "wb") as f:
                tomli_w.dump(config, f)
            logger.info(f"Initialized user-specific config at {USER_CONFIG_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize config: {e}")
            raise ConfigError(f"Failed to initialize config: {e}")
    elif force:
        config = generate_user_config()
        try:
            with open(USER_CONFIG_FILE, "wb") as f:
                tomli_w.dump(config, f)
            logger.info(
                f"Overwrote config with user-specific defaults at {USER_CONFIG_FILE}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to overwrite config: {e}")
            raise ConfigError(f"Failed to overwrite config: {e}")
    return False


@click.command("config")
@click.option(
    "--edit",
    "-e",
    is_flag=True,
    help="Open the configuration file in the default editor (uses $EDITOR or nano).",
)
@click.option(
    "--init",
    is_flag=True,
    help="Generate a new ~/.altbuilder/config.toml with user-specific defaults.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force overwrite of existing config file when using --init.",
)
@click.help_option("--help", "-h")
def config_cmd(edit, init, force):
    """
    Display, edit, or initialize the altbuilder configuration.

    By default, shows the current configuration in a readable format.
    Use --edit to open the config file in your default editor.
    Use --init to generate a new config with user-specific defaults.
    """
    # Handle --init
    if init:
        if USER_CONFIG_FILE.exists() and not force:
            click.echo(
                colorize(
                    f"Config file already exists at {USER_CONFIG_FILE}. "
                    "Use --force to overwrite.",
                    color="yellow",
                )
            )
            raise click.Abort()

        initialized = ensure_config_file(force=force)
        if initialized:
            click.echo(
                colorize(
                    f"Generated user-specific config at {USER_CONFIG_FILE}",
                    color="green",
                )
            )
        return

    # Load configuration
    try:
        config = load_config()
    except ConfigError as e:
        click.echo(colorize(f"Error loading config: {e}", color="red"))
        raise click.Abort()

    # Handle --edit
    if edit:
        # Ensure config file exists
        initialized = ensure_config_file()
        if initialized:
            click.echo(
                colorize(
                    f"Created user-specific config at {USER_CONFIG_FILE}",
                    color="green",
                )
            )

        # Determine editor
        editor = os.environ.get("EDITOR", "vim")
        try:
            subprocess.run([editor, str(USER_CONFIG_FILE)], check=True)
            click.echo(
                colorize(
                    f"Opened {USER_CONFIG_FILE} in {editor}",
                    color="green",
                )
            )
            return
        except FileNotFoundError:
            click.echo(
                colorize(
                    f"Editor '{editor}' not found. Please set $EDITOR or install {editor}.",
                    color="red",
                )
            )
            raise click.Abort()
        except subprocess.CalledProcessError as e:
            click.echo(
                colorize(
                    f"Failed to open editor: {e}",
                    color="red",
                )
            )
            raise click.Abort()

    # Default action: Display configuration
    click.echo(display_config(config))
