import getpass
import os
import subprocess
from pathlib import Path

import typer
from rich import print as rich_print

from altbuilder.config import (
    DEFAULT_CONFIG_FILE,
    USER_CONFIG_DIR,
    USER_CONFIG_FILE,
    load_config,
)
from altbuilder.exceptions import ConfigError
from altbuilder.utils import logger
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="config",
    help="Display, edit, or initialize the altbuilder configuration.",
)


def display_config(config):
    """Display the configuration in a clean, highlighted format."""
    output = []

    # Header
    config_file = config.get("config_file", str(USER_CONFIG_FILE))
    output.append("[bold cyan]altbuilder Configuration[/bold cyan]")
    output.append(f"[green]File: {config_file}[/green]")
    output.append("")

    # Global Settings
    output.append("[bold yellow]Global Settings:[/bold yellow]")
    global_keys = [
        "branch",
        "arch",
        "mirror",
        "mirror_task",
        "rdb_url",
        "packager",
        "base_dir",
        "environment_dir",
        "build_logs_dir",
    ]
    for key in global_keys:
        if key in config:
            output.append(
                f"  [cyan]{key.capitalize()}[/cyan]: [white]{config[key]}[/white]"
            )

    # Logging Settings
    output.append("")
    output.append("[bold yellow]Logging:[/bold yellow]")
    if "logging" in config:
        logging = config["logging"]
        for key in ["level", "file_level", "rotation", "format", "max_files"]:
            if key in logging:
                output.append(
                    f"  [cyan]{key.capitalize()}[/cyan]: [white]{logging[key]}[/white]"
                )

    # Sandboxes
    if config.get("sandboxes"):
        output.append("")
        output.append("[bold yellow]Sandboxes:[/bold yellow]")
        for sandbox, settings in config["sandboxes"].items():
            output.append(f"  [bold cyan]{sandbox}[/bold cyan]:")
            for key, value in settings.items():
                output.append(
                    f"    [cyan]{key.capitalize()}[/cyan]: [white]{value}[/white]"
                )

    # Footer with usage hint
    output.append("")
    output.append(
        "[green]Tip: Use 'altbuilder config --edit' to modify or 'altbuilder config --init' to generate a new config.[/green]"
    )

    return "\n".join(output)


def generate_user_config():
    """Read the bundled default configuration and tailor it for the current user."""

    try:
        try:
            current_user = getpass.getuser()
        except Exception:
            current_user = Path.home().name

        with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
            template = f.read()

        packager_placeholder = 'packager = "User <user@altlinux.org>"'
        if packager_placeholder in template:
            template = template.replace(
                packager_placeholder,
                f'packager = "{current_user} <{current_user}@altlinux.org>"',
            )

        template = template.replace("<user>", current_user)
        return template.encode("utf-8")
    except OSError as e:
        raise ConfigError(f"Failed to read default configuration: {e}") from e


def ensure_config_file(force=False):
    """Ensure the config file exists, initializing with user-specific defaults if necessary."""
    if not USER_CONFIG_FILE.exists():
        config_bytes = generate_user_config()
        try:
            os.makedirs(USER_CONFIG_DIR, exist_ok=True)
            with open(USER_CONFIG_FILE, "wb") as f:
                f.write(config_bytes)
            logger.info(f"Initialized user-specific config at {USER_CONFIG_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize config: {e}")
            raise ConfigError(f"Failed to initialize config: {e}")
    elif force:
        config_bytes = generate_user_config()
        try:
            with open(USER_CONFIG_FILE, "wb") as f:
                f.write(config_bytes)
            logger.info(
                f"Overwrote config with user-specific defaults at {USER_CONFIG_FILE}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to overwrite config: {e}")
            raise ConfigError(f"Failed to overwrite config: {e}")
    return False


@app.command()
def config_cmd(
    ctx: typer.Context,
    edit: bool = typer.Option(
        False,
        "--edit",
        "-e",
        help="Open the configuration file in the default editor (uses $EDITOR or nano).",
    ),
    init: bool = typer.Option(
        False,
        "--init",
        help="Generate a new ~/.altbuilder/config.toml with user-specific defaults.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force overwrite of existing config file when using --init.",
    ),
):
    """
    Display, edit, or initialize the altbuilder configuration.

    By default, shows the current configuration in a readable format.
    Use --edit to open the config file in your default editor.
    Use --init to generate a new config with user-specific defaults.
    """
    json_mode = is_json_mode(ctx)
    params = {"edit": edit, "init": init, "force": force}
    config_path = str(USER_CONFIG_FILE)

    # Handle --init
    if init:
        if USER_CONFIG_FILE.exists() and not force:
            message = f"Config file already exists at {USER_CONFIG_FILE}. Use --force to overwrite."
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    config_path=config_path,
                )
                return
            rich_print(f"[yellow]{message}[/yellow]")
            raise typer.Abort()

        try:
            initialized = ensure_config_file(force=force)
        except ConfigError as e:
            message = f"Failed to initialize config: {e}"
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    config_path=config_path,
                )
                return
            rich_print(f"[red]{message}[/red]")
            raise typer.Abort()

        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=(
                    f"Generated user-specific config at {USER_CONFIG_FILE}"
                    if initialized
                    else "Config file already exists."
                ),
                config_path=config_path,
            )
        else:
            if initialized:
                rich_print(
                    f"[green]Generated user-specific config at {USER_CONFIG_FILE}[/green]"
                )
        return

    # Load configuration
    try:
        config = load_config()
    except ConfigError as e:
        message = f"Error loading config: {e}"
        if json_mode:
            json_response(
                ctx,
                "error",
                params=params,
                message=message,
                code=1,
                config_path=config_path,
            )
            return
        rich_print(f"[red]{message}[/red]")
        raise typer.Abort()

    # Handle --edit
    if edit:
        # Ensure config file exists
        try:
            initialized = ensure_config_file()
        except ConfigError as e:
            message = f"Failed to ensure config file: {e}"
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    config_path=config_path,
                )
                return
            rich_print(f"[red]{message}[/red]")
            raise typer.Abort()

        created = bool(initialized)
        if created and not json_mode:
            rich_print(
                f"[green]Created user-specific config at {USER_CONFIG_FILE}[/green]"
            )

        # Determine editor
        editor = os.environ.get("EDITOR", "vim")
        try:
            subprocess.run([editor, str(USER_CONFIG_FILE)], check=True)
            if json_mode:
                extra = {"config_path": config_path, "editor": editor}
                if created:
                    extra["created"] = True
                json_response(
                    ctx,
                    "success",
                    params=params,
                    message=f"Opened {USER_CONFIG_FILE} in {editor}",
                    **extra,
                )
            else:
                rich_print(f"[green]Opened {USER_CONFIG_FILE} in {editor}[/green]")
            return
        except FileNotFoundError:
            message = (
                f"Editor '{editor}' not found. Please set $EDITOR or install {editor}."
            )
            if json_mode:
                extra = {"config_path": config_path, "editor": editor}
                if created:
                    extra["created"] = True
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    **extra,
                )
                return
            rich_print(f"[red]{message}[/red]")
            raise typer.Abort()
        except subprocess.CalledProcessError as e:
            message = f"Failed to open editor: {e}"
            if json_mode:
                extra = {"config_path": config_path, "editor": editor}
                if created:
                    extra["created"] = True
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    **extra,
                )
                return
            rich_print(f"[red]{message}[/red]")
            raise typer.Abort()

    # Default action: Display configuration
    if json_mode:
        json_response(
            ctx,
            "success",
            params=params,
            config=config,
            config_path=config.get("config_file", config_path),
        )
    else:
        rich_print(display_config(config))


if __name__ == "__main__":
    app()
