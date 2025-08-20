from typing import List

import typer
import subprocess

from ..config import get_sandbox_config, load_config
from ..core.environment import Environment
from ..utils import colorize, init_logger

app = typer.Typer()


@app.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
def run_cmd(
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
    if not command:
        typer.echo(
            colorize(
                "Error: No command provided. Usage: altbuilder run -s SANDBOX -- COMMAND",
                color="red",
            )
        )
        raise typer.Exit(code=1)

    command_str = " ".join(command)

    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        typer.echo(colorize(f"Sandbox {sandbox_name} does not exist.", color="red"))
        raise typer.Exit(code=1)

    try:
        env.run(command_str)
    except subprocess.CalledProcessError as e:
        if e.output:
            typer.echo(e.output.decode() if isinstance(e.output, bytes) else e.output)
        else:
            typer.echo(f"Command failed with exit code {e.returncode}")
        raise typer.Exit(code=e.returncode)


if __name__ == "__main__":
    app()
