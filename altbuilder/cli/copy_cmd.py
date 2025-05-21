import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils import init_logger, colorize


@click.group("copy")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.pass_context
def copy_group(ctx, sandbox):
    """Copy files or directories between host and sandbox."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        click.echo(
            colorize(
                f"Sandbox {sandbox_name} does not exist. Please initialize it first.",
                color="red",
            )
        )
        raise click.Abort()
    ctx.obj = {"env": env}


@copy_group.command("to-sandbox")
@click.argument("host_path", type=click.Path(exists=True))
@click.argument("sandbox_path")
@click.pass_context
def copy_to_sandbox(ctx, host_path, sandbox_path):
    """Copy from host to sandbox: altbuilder copy to-sandbox <host_path> <sandbox_path>"""
    env = ctx.obj["env"]
    try:
        env.copy_to(host_path, sandbox_path)
        click.echo(
            colorize(
                f"Copied {host_path} to {sandbox_path} in sandbox {env.name}",
                color="green",
            )
        )
    except EnvironmentError as e:
        click.echo(colorize(f"Error: {e}", color="red"))
        raise


@copy_group.command("from-sandbox")
@click.argument("sandbox_path")
@click.argument("host_path", type=click.Path())
@click.pass_context
def copy_from_sandbox(ctx, sandbox_path, host_path):
    """Copy from sandbox to host: altbuilder copy from-sandbox <sandbox_path> <host_path>"""
    env = ctx.obj["env"]
    try:
        env.copy_from(sandbox_path, host_path)
        click.echo(
            colorize(
                f"Copied {sandbox_path} from sandbox {env.name} to {host_path}",
                color="green",
            )
        )
    except EnvironmentError as e:
        click.echo(colorize(f"Error: {e}", color="red"))
        raise
