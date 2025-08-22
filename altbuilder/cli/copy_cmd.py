from typing import Optional

import typer

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import colorize, init_logger

app = typer.Typer(help="Copy files or directories between host and sandbox.")
copy_app = typer.Typer(help="Copy commands group.")

app.add_typer(copy_app, name="copy")


def get_env(sandbox: Optional[str]) -> Environment:
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        typer.echo(
            colorize(
                f"Sandbox {sandbox_name} does not exist. Please initialize it first.",
                color="red",
            )
        )
        raise typer.Exit(code=1)
    return env


@copy_app.command("to")
def copy_to_sandbox(
    host_path: str = typer.Argument(
        ..., exists=True, help="Path on the host to copy from."
    ),
    sandbox_path: str = typer.Argument(
        ..., help="Destination path inside the sandbox."
    ),
    sandbox: Optional[str] = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
):
    """Copy files or directories from host to sandbox."""
    env = get_env(sandbox)
    try:
        env.copy_to(host_path, sandbox_path)
        typer.echo(
            colorize(
                f"Copied {host_path} to {sandbox_path} in sandbox {env.name}",
                color="green",
            )
        )
    except EnvironmentError as e:
        typer.echo(colorize(f"Error: {e}", color="red"))
        raise typer.Exit(code=1)


@copy_app.command("from")
def copy_from_sandbox(
    sandbox_path: str = typer.Argument(
        ..., help="Path inside the sandbox to copy from."
    ),
    host_path: str = typer.Argument(..., help="Destination path on the host."),
    sandbox: Optional[str] = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
):
    """Copy files or directories from sandbox to host."""
    env = get_env(sandbox)
    try:
        env.copy_from(sandbox_path, host_path)
        typer.echo(
            colorize(
                f"Copied {sandbox_path} from sandbox {env.name} to {host_path}",
                color="green",
            )
        )
    except EnvironmentError as e:
        typer.echo(colorize(f"Error: {e}", color="red"))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
