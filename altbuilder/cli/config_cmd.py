import getpass
import os
import re
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
    help="Manage altbuilder configuration with subcommands for initialization, editing, and display.",
    invoke_without_command=True,
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
        "[green]Tip: Use 'altbuilder config edit' to modify or 'altbuilder config init' to generate a new config.[/green]"
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


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string value.

    Supports both $VAR and ${VAR} syntax.
    Examples:
        "$HOME/.altbuilder" -> "/home/user/.altbuilder"
        "$USER <$USER@altlinux.org>" -> "test <test@altlinux.org>"
    """
    if not isinstance(value, str):
        return value

    # Expand using os.path.expandvars (handles $VAR and ${VAR})
    expanded = os.path.expandvars(value)

    # Also expand ~ for home directory
    if "~" in expanded:
        expanded = os.path.expanduser(expanded)

    return expanded


def update_config_field(field: str, value: str) -> tuple[str, bool]:
    """Update a specific field in the user config file.

    Args:
        field: The configuration field name (e.g., 'mirror', 'packager')
        value: The new value (will be expanded for environment variables)

    Returns:
        Tuple of (expanded_value, was_created) where was_created indicates if config was auto-created

    Raises:
        ConfigError: If field update fails
    """
    # Auto-create config if it doesn't exist
    was_created = False
    if not USER_CONFIG_FILE.exists():
        ensure_config_file()
        was_created = True

    # Expand environment variables in the value
    expanded_value = expand_env_vars(value)

    try:
        with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Find and update the field
        field_pattern = re.compile(rf'^(\s*){re.escape(field)}\s*=')
        updated = False
        new_lines = []

        for line in lines:
            if field_pattern.match(line):
                # Preserve indentation
                indent = field_pattern.match(line).group(1)
                # Format the new value (add quotes for strings)
                new_lines.append(f'{indent}{field} = "{expanded_value}"\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            raise ConfigError(
                f"Field '{field}' not found in config file. "
                f"Available fields can be seen with 'altbuilder config show'."
            )

        # Write back to file
        with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"Updated {field} = {expanded_value} in {USER_CONFIG_FILE}")
        return (expanded_value, was_created)

    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Failed to update config field: {e}") from e


@app.callback(invoke_without_command=True)
def config_callback(ctx: typer.Context):
    """Manage altbuilder configuration.

    Without a subcommand, defaults to 'show' to display current configuration.

    Examples:
        altbuilder config                    # Show current configuration
        altbuilder config show               # Same as above
        altbuilder config init               # Initialize new configuration
        altbuilder config edit               # Edit configuration in editor
        altbuilder config edit --field mirror "file:/mnt/repo"
    """
    if ctx.invoked_subcommand is None:
        # Default to show command
        ctx.invoke(show_cmd, ctx)


@app.command("show")
def show_cmd(ctx: typer.Context):
    """Display the current altbuilder configuration.

    Shows all configuration settings including global settings, logging configuration,
    and sandbox-specific overrides in a formatted, easy-to-read layout.

    Examples:
        altbuilder config show
        altbuilder config              # 'show' is the default subcommand
    """
    json_mode = is_json_mode(ctx)
    config_path = str(USER_CONFIG_FILE)

    # Load configuration
    try:
        config = load_config()
    except ConfigError as e:
        message = f"Error loading config: {e}"
        if json_mode:
            json_response(
                ctx,
                "error",
                params={},
                message=message,
                code=1,
                config_path=config_path,
            )
        else:
            rich_print(f"[red]{message}[/red]")
        raise typer.Abort()

    # Display configuration
    if json_mode:
        json_response(
            ctx,
            "success",
            params={},
            config=config,
            config_path=config.get("config_file", config_path),
        )
    else:
        rich_print(display_config(config))


@app.command("init")
def init_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force overwrite of existing config file.",
    ),
):
    """Initialize a new configuration file with user-specific defaults.

    Creates ~/.altbuilder/config.toml with sensible defaults personalized for
    the current user (username, home directory paths, etc.).

    By default, will not overwrite an existing configuration file unless
    --force is specified.

    Examples:
        altbuilder config init              # Create new config if none exists
        altbuilder config init --force      # Overwrite existing config
    """
    json_mode = is_json_mode(ctx)
    params = {"force": force}
    config_path = str(USER_CONFIG_FILE)

    try:
        initialized = ensure_config_file(force=force)

        if not initialized and not force:
            # File already exists and force not specified
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
            else:
                rich_print(f"[yellow]{message}[/yellow]")
            raise typer.Abort()

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
        else:
            rich_print(f"[red]{message}[/red]")
        raise typer.Abort()

    message = f"Generated user-specific config at {USER_CONFIG_FILE}"
    if json_mode:
        json_response(
            ctx,
            "success",
            params=params,
            message=message,
            config_path=config_path,
        )
    else:
        rich_print(f"[green]{message}[/green]")


@app.command("edit")
def edit_cmd(
    ctx: typer.Context,
    field: str | None = typer.Option(
        None,
        "--field",
        "-f",
        help="Specific configuration field to edit (e.g., 'mirror', 'packager').",
    ),
    value: str | None = typer.Argument(
        None,
        help="New value for the field. Supports environment variable expansion ($VAR, ${VAR}).",
    ),
):
    """Edit the configuration file or a specific field.

    Without --field: Opens the configuration file in your default editor ($EDITOR).

    With --field: Updates a specific configuration field with automatic environment
    variable expansion. Supports $VAR and ${VAR} syntax.

    Environment variables that are commonly used:
        $USER, $HOME, $SHELL, etc.

    Examples:
        altbuilder config edit
            # Opens config in $EDITOR (vim, nano, etc.)

        altbuilder config edit --field mirror "file:/mnt/repo"
            # Set mirror to local repository

        altbuilder config edit --field packager "$USER <$USER@altlinux.org>"
            # Set packager with automatic username expansion

        altbuilder config edit --field environment_dir "$HOME/.altbuilder/environments"
            # Set environment directory with home directory expansion

        altbuilder config edit --field base_dir "/custom/path"
            # Set base directory to custom path
    """
    json_mode = is_json_mode(ctx)
    params = {"field": field, "value": value}
    config_path = str(USER_CONFIG_FILE)

    # Field-specific edit mode
    if field is not None:
        if value is None:
            message = "You must provide a value when using --field option."
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    config_path=config_path,
                )
            else:
                rich_print(f"[red]Error: {message}[/red]")
                rich_print("[yellow]Usage: altbuilder config edit --field <field> <value>[/yellow]")
            raise typer.Abort()

        # Update the specific field (auto-creates config if needed)
        try:
            expanded_value, was_created = update_config_field(field, value)
        except ConfigError as e:
            message = str(e)
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    config_path=config_path,
                )
            else:
                rich_print(f"[red]Error: {message}[/red]")
            raise typer.Abort()

        # Field updated successfully
        if was_created and not json_mode:
            rich_print(
                f"[green]Created user-specific config at {USER_CONFIG_FILE}[/green]"
            )

        message = f"Updated {field} to '{expanded_value}'"
        if json_mode:
            extra = {
                "config_path": config_path,
                "field": field,
                "value": expanded_value,
                "original_value": value,
            }
            if was_created:
                extra["created"] = True
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                **extra,
            )
        else:
            rich_print(f"[green]{message}[/green]")
            if value != expanded_value:
                rich_print(f"[cyan]  Original: {value}[/cyan]")
                rich_print(f"[cyan]  Expanded: {expanded_value}[/cyan]")
    
    # Full file edit mode (when field is None)
    else:
        # Ensure config file exists
        try:
            initialized = ensure_config_file()
            created = bool(initialized)
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
            else:
                rich_print(f"[red]{message}[/red]")
            raise typer.Abort()
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
            else:
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
            else:
                rich_print(f"[red]{message}[/red]")
            raise typer.Abort()


if __name__ == "__main__":
    app()
