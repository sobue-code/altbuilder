import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger

app = typer.Typer(
    name="shell",
    help="Enter the shell of the specified sandbox.",
)


@app.command()
def shell_cmd(
    ctx: typer.Context,
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
    sandbox_name = sandbox or ctx.obj.get("sandbox") or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    # Initialize logging
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    # Setup environment
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        rich_print(f"[red]Sandbox {sandbox_name} does not exist.[/red]")
        raise typer.Exit(code=1)

    rich_print(f"[bold]Entering shell for sandbox: {sandbox_name}[/bold]")

    try:
        env.shell(root, internet)
    except EnvironmentError as e:
        rich_print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
