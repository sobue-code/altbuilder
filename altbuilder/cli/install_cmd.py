import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils import init_logger, colorize


@click.command("install")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.argument("packages", nargs=-1)
@click.help_option("--help", "-h")
def install_cmd(sandbox, packages):
    """Install packages into specified sandbox."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        click.echo(colorize(f"Sandbox {sandbox_name} does not exist.", color="red"))
        return

    if packages:
        click.echo(
            colorize(f"Installing packages in sandbox: {sandbox_name}", bold=True)
        )
        env.install(packages)
    else:
        click.echo(colorize("No packages specified for installation.", color="yellow"))
