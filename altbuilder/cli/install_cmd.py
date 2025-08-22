import typer

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import colorize, init_logger

app = typer.Typer(
    name="install",
    help="Install packages into specified sandbox.",
)


@app.command()
def install_cmd(
    packages: list[str] = typer.Argument(
        None,
        help="Names of packages to install into the sandbox.",
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
):
    """Install packages into specified sandbox."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    # Initialize logger
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    # Setup environment
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        typer.echo(colorize(f"Sandbox {sandbox_name} does not exist.", color="red"))
        raise typer.Exit(code=1)

    if packages:
        typer.echo(
            colorize(f"Installing packages in sandbox: {sandbox_name}", bold=True)
        )
        env.install(packages)
    else:
        typer.echo(colorize("No packages specified for installation.", color="yellow"))


if __name__ == "__main__":
    app()
