from typing import List

import typer
import subprocess

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.json_utils import is_json_mode, json_response
from rich import print as rich_print

app = typer.Typer()


@app.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
def run_cmd(
    ctx: typer.Context,
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    command: List[str] = typer.Argument(
        ..., help="Command to run inside sandbox (pass after --)."
    ),
):
    """Run command inside sandbox."""
    json_mode = is_json_mode(ctx)

    if not command:
        error_msg = "No command provided. Usage: altbuilder run -s SANDBOX -- COMMAND"
        if json_mode:
            json_response(ctx, "error", message=error_msg, code=1)
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)
        return

    command_str = " ".join(command)

    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

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

    try:
        env.run(command_str)
        success_msg = f"Command executed successfully in sandbox {sandbox_name}."
        logger.info(success_msg)
        if json_mode:
            json_response(
                ctx,
                "success",
                message=success_msg,
                sandbox=sandbox_name,
                command=command_str,
            )
        else:
            rich_print(f"[green]{success_msg}[/green]")
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed with exit code {e.returncode}"
        logger.error(error_msg)
        if json_mode:
            json_response(
                ctx,
                "error",
                message=error_msg,
                sandbox=sandbox_name,
                command=command_str,
                exit_code=e.returncode,
                code=e.returncode,
            )
        else:
            if e.output:
                typer.echo(e.output.decode() if isinstance(e.output, bytes) else e.output)
            else:
                typer.echo(error_msg)
            raise typer.Exit(code=e.returncode)


if __name__ == "__main__":
    app()
