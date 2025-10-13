import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="install",
    help="Install packages into specified sandbox.",
)


@app.command()
def install_cmd(
    ctx: typer.Context,
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
    json_mode = is_json_mode(ctx)
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    # Initialize logger
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    # Setup environment
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        error_msg = f"Sandbox {sandbox_name} does not exist."
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")
            raise typer.Exit(code=1)
        return

    if not packages:
        error_msg = "No packages specified for installation."
        if json_mode:
            json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, code=1)
        else:
            rich_print("[yellow]No packages specified for installation.[/yellow]")
        return

    try:
        if not json_mode:
            rich_print(f"[bold]Installing packages in sandbox: {sandbox_name}[/bold]")
        env.install(packages)
        success_msg = f"Successfully installed {len(packages)} package(s) in sandbox {sandbox_name}."
        logger.info(success_msg)
        if json_mode:
            json_response(
                ctx,
                "success",
                message=success_msg,
                sandbox=sandbox_name,
                packages=packages,
            )
        else:
            rich_print(f"[green]{success_msg}[/green]")
    except Exception as e:
        error_msg = f"Failed to install packages in sandbox {sandbox_name}: {e}"
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, packages=packages, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
