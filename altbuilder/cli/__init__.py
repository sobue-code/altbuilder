import importlib.metadata
import json

import typer

from ..config import load_config
from ..utils.logger import init_logger, logger
from .clean_cmd import clean_cmd
from .config_cmd import app as config_app
from .list_cmd import list_cmd
from .logs_cmd import logs_cmd
from .rebuild_cmd import rebuild_cmd
from .stop_cmd import stop_cmd
from .track_cmd import track_cmd

app = typer.Typer(
    name="altbuilder",
    help="Command-line interface for managing ALT Linux sandboxes.",
    context_settings={"obj": {}, "help_option_names": ["-h", "--help"]},
)


def get_version() -> str:
    """Returns the project version from metadata."""
    try:
        return importlib.metadata.version("altbuilder")
    except importlib.metadata.PackageNotFoundError:
        try:
            import tomli

            with open("pyproject.toml", "rb") as f:
                config = tomli.load(f)
            return config["project"]["version"]
        except (FileNotFoundError, KeyError):
            return "unknown"


# Add global sandbox option
@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Enable JSON-formatted output.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=lambda value: (
            typer.echo(f"{get_version()}") or typer.Exit() if value else None
        ),
        is_eager=True,
    ),
):
    """Command-line interface for managing ALT Linux sandboxes."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output

    if ctx.invoked_subcommand is None and not version:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "status": "error",
                        "message": "No command provided.",
                        "code": 1,
                    },
                    ensure_ascii=False,
                )
            )
        raise typer.Exit(code=1)
    if not version:
        ctx.obj["sandbox"] = sandbox
        config = load_config()
        init_logger(config=config)
        logger.info(f"Loaded config from {config.get('config_file', 'default')}")


app.command("list")(list_cmd)
app.add_typer(config_app, name="config")
app.command("track")(track_cmd)
app.command("stop")(stop_cmd)
app.command("clean")(clean_cmd)
app.command("logs")(logs_cmd)
app.command("rebuild")(rebuild_cmd)

if __name__ == "__main__":
    app()
