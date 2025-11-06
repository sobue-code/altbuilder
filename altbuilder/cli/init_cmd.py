import typer
from rich import print as rich_print

from altbuilder.config import load_config
from altbuilder.utils.json_utils import is_json_mode, json_response
from altbuilder.utils.setup_sandbox import setup_sandbox
from altbuilder.utils import logger

app = typer.Typer(
    name="init",
    help="Initialize a new sandbox environment.",
)

@app.command()
def init_cmd(
    ctx: typer.Context,
    branch: str = typer.Option(
        None, "--branch", "-b", help="Branch name (e.g., Sisyphus). Overrides config."
    ),
    arch: str = typer.Option(
        None, "--arch", "-a", help="Architecture (e.g., x86_64). Overrides config."
    ),
    task: int = typer.Option(
        None, "--task", "-t", help="Attach task repository by ID."
    ),
    reinit: bool = typer.Option(
        False, "--reinit", "-r", help="Reinitialize the sandbox before building."
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> or config.",
    ),
):
    """Initialize a new sandbox environment."""
    json_mode = is_json_mode(ctx)

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    params = {
        "sandbox": sandbox,
        "branch": branch,
        "arch": arch,
        "task": task,
        "reinit": reinit,
    }

    try:
        config = load_config()
        env = setup_sandbox(sandbox, branch, arch, reinit, config, task_id=task)

        if env is None:
            error_msg = "Failed to initialize sandbox."
            logger.error(error_msg)
            if json_mode:
                json_response(ctx, "error", params=params, message=error_msg, code=1)
            else:
                rich_print(f"[red]{error_msg}[/red]")
                raise typer.Exit(code=1)

        sandbox_name = env.name
        params["sandbox"] = sandbox_name
        params["branch"] = env.config.get("branch")
        params["arch"] = env.config.get("arch")

        success_msg = f"Sandbox {sandbox_name} initialized successfully."
        logger.info(success_msg)

        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=success_msg,
                sandbox=sandbox_name,
            )
        else:
            rich_print(f"[green]{success_msg}[/green]")

    except Exception as e:
        error_msg = f"Failed to initialize sandbox: {e}"
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", params=params, message=error_msg, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
