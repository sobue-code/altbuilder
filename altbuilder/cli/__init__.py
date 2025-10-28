import importlib.metadata
import json

import typer

from ..config import load_config
from ..utils.logger import init_logger, logger
# Temporarily commented out until converted to Typer
from .build_cmd import build_cmd
from .clean_cmd import clean_cmd
from .config_cmd import config_cmd
from .copy_cmd import copy_app
from .copy_pyproject_deps_cmd import copy_pyproject_deps
from .init_cmd import init_cmd
from .install_cmd import install_cmd
from .list_cmd import list_cmd
from .logs_cmd import logs_cmd
from .merge_tag_cmd import merge_tag
from .rebuild_cmd import rebuild_cmd
from .rpmdiff_cmd import rpmdiff_cmd
from .run_cmd import run_cmd
from .shell_cmd import shell_cmd
from .stop_cmd import stop_cmd
from .track_cmd import track_cmd
from .update_submodules_cmd import update_submodules
from .git_alt_cmd import git_alt_cmd
from .vendor_cmd import vendor_app

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


# Add commands (only init_cmd is Typer-based for now)
app.command("init")(init_cmd)
# Placeholder for other commands (to be converted)
app.command("list")(list_cmd)
app.command("shell")(shell_cmd)
app.command("clean")(clean_cmd)
app.command("config")(config_cmd)
app.command("install")(install_cmd)
app.command("run")(run_cmd)
app.command("track")(track_cmd)
app.command("stop")(stop_cmd)
app.command("logs")(logs_cmd)
app.command("build")(build_cmd)
app.command("rebuild")(rebuild_cmd)
app.command("copy-pyproject-deps")(copy_pyproject_deps)
app.command("cpd")(copy_pyproject_deps)
app.command("update-submodules")(update_submodules)
app.command("merge-tag")(merge_tag)
app.command("rpmdiff")(rpmdiff_cmd)
app.command("git.alt")(git_alt_cmd)
app.add_typer(copy_app, name="copy")
app.add_typer(vendor_app, name="vendor")

if __name__ == "__main__":
    app()
