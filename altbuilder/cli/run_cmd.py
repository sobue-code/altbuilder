import click
import sys
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger
from ..utils.helpers import colorize

import click
import sys
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger
from ..utils.helpers import colorize


@click.command(
    "run",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.help_option("--help", "-h")
@click.pass_context
def run_cmd(ctx, sandbox):
    """Run a command in the specified sandbox.

    Everything after -- will be passed as a command to the sandbox.
    Example: altbuilder run -- ls -lah
    """
    args = ctx.args

    if not args:
        click.echo(
            colorize(
                "Error: No command provided. Usage: altbuilder run -- COMMAND",
                color="red",
            )
        )
        ctx.exit(1)

    if args and args[0] == "--":
        args = args[1:]

    if not args:
        click.echo(colorize("Error: No command provided after --", color="red"))
        ctx.exit(1)

    command = " ".join(args)

    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        click.echo(colorize(f"Sandbox {sandbox_name} does not exist.", color="red"))
        return

    env.run(command)
