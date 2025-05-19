import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger
from ..utils.helpers import colorize


@click.command("shell")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option("--root", is_flag=True, help="Run shell as root.")
@click.option("--internet", is_flag=True, help="Enable internet in the shell.")
@click.help_option("--help", "-h")
def shell_cmd(sandbox, root, internet):
    """Enter the shell of the specified sandbox.

    The sandbox can be specified using the global --sandbox option
    (e.g., `altbuilder --sandbox Sisyphus-x86_64 shell`) or the
    command-specific --sandbox option (e.g., `altbuilder shell --sandbox Sisyphus-x86_64`).
    """
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    click.echo(colorize(f"Entering shell for sandbox: {sandbox_name}", bold=True))
    try:
        env.shell(root, internet)
    except EnvironmentError as e:
        click.echo(colorize(f"Error: {e}", color="red"))
