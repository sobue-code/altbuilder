import getpass
import os
import subprocess

import tomli_w
import typer
from rich import print as rich_print

from altbuilder.config import USER_CONFIG_DIR, USER_CONFIG_FILE, load_config
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
        for key in ["level", "file_level", "rotation", "format"]:
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
        "mirror_task": "http://git.altlinux.org",
        "rdb_url": "https://rdb.altlinux.org",
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

    # Handle --init
    if init:
        if USER_CONFIG_FILE.exists() and not force:
            error_msg = f"Config file already exists at {USER_CONFIG_FILE}. Use --force to overwrite."
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    message=error_msg,
                    config_file=str(USER_CONFIG_FILE),
                    code=1,
                )
            else:
                rich_print(f"[yellow]{error_msg}[/yellow]")
                raise typer.Abort()
            return

        try:
            initialized = ensure_config_file(force=force)
            if initialized:
                success_msg = f"Generated user-specific config at {USER_CONFIG_FILE}"
                if json_mode:
                    json_response(
                        ctx,
                        "success",
                        message=success_msg,
                        config_file=str(USER_CONFIG_FILE),
                    )
                else:
                    rich_print(f"[green]{success_msg}[/green]")
        except ConfigError as e:
            error_msg = f"Failed to initialize config: {e}"
            if json_mode:
                json_response(ctx, "error", message=error_msg, code=1)
            else:
                rich_print(f"[red]{error_msg}[/red]")
                raise typer.Abort()
        return

    # Load configuration
    try:
        config = load_config()
    except ConfigError as e:
        error_msg = f"Error loading config: {e}"
        if json_mode:
            json_response(ctx, "error", message=error_msg, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")
        raise typer.Abort()

    # Handle --edit
    if edit:
        # Ensure config file exists
        initialized = ensure_config_file()
        if initialized:
            rich_print(
                f"[green]Created user-specific config at {USER_CONFIG_FILE}[/green]"
            )

        # Determine editor
        editor = os.environ.get("EDITOR", "vim")
        try:
            subprocess.run([editor, str(USER_CONFIG_FILE)], check=True)
            rich_print(f"[green]Opened {USER_CONFIG_FILE} in {editor}[/green]")
            return
        except FileNotFoundError:
            rich_print(
                f"[red]Editor '{editor}' not found. Please set $EDITOR or install {editor}.[/red]"
            )
            raise typer.Abort()
        except subprocess.CalledProcessError as e:
            rich_print(f"[red]Failed to open editor: {e}[/red]")
            raise typer.Abort()

    # Default action: Display configuration
    if json_mode:
        # Prepare config for JSON output (remove internal keys)
        output_config = {k: v for k, v in config.items() if k != "config_file"}
        json_response(
            ctx,
            "success",
            message="Configuration loaded successfully",
            config_file=config.get("config_file", str(USER_CONFIG_FILE)),
            config=output_config,
        )
    else:
        rich_print(display_config(config))


if __name__ == "__main__":
    app()
