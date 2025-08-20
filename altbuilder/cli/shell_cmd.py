import typer

from ..config import get_sandbox_config, load_config
from ..core.environment import Environment
from ..utils import colorize, init_logger

app = typer.Typer(
    name="shell",
    help="Enter the shell of the specified sandbox.",
)


@app.command()
def shell_cmd(
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    root: bool = typer.Option(
        False,
        "--root",
        help="Run shell as root.",
    ),
    internet: bool = typer.Option(
        False,
        "--internet",
        help="Enable internet in the shell.",
    ),
):
    """Enter the shell of the specified sandbox.

    The sandbox can be specified using the global --sandbox option
    (e.g., `altbuilder --sandbox Sisyphus-x86_64 shell`)
    """
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    # Initialize logging
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    # Setup environment
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        typer.echo(colorize(f"Sandbox {sandbox_name} does not exist.", color="red"))
        raise typer.Exit(code=1)

    typer.echo(colorize(f"Entering shell for sandbox: {sandbox_name}", bold=True))

    try:
        env.shell(root, internet)
    except EnvironmentError as e:
        typer.echo(colorize(f"Error: {e}", color="red"))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
