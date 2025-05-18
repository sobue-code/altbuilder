import click
import os
import shutil
import subprocess
from .config import load_config, get_sandbox_config
from .core.environment import Environment
from .core.build_manager import BuildManager
from .utils.logger import init_logger, logger
from .utils.helpers import colorize, run_logged_command


@click.group()
@click.option(
    "--sandbox",
    help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
)
def cli(sandbox):
    """Command-line interface for managing ALT Linux sandboxes."""
    ctx = click.get_current_context()
    ctx.obj = {"sandbox": sandbox}
    config = load_config()
    init_logger(config=config)
    logger.info(f"Loaded config from {config.get('config_file', 'default')}")


@cli.command()
@click.option("--branch", help="Branch name (e.g., Sisyphus). Overrides config.")
@click.option("--arch", help="Architecture (e.g., x86_64). Overrides config.")
@click.option("--task", type=int, help="Attach task repository by ID.")
@click.option("--sandbox", help="Sandbox name. Defaults to <branch>-<arch> or config.")
def init(branch, arch, task, sandbox):
    """Initialize a new sandbox environment."""
    config = load_config()
    default_sandbox = f"{branch or config['branch']}-{arch or config['arch']}"
    sandbox_name = sandbox or default_sandbox
    if task:
        sandbox_name += f"-{task}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=task)
    click.echo(colorize(f"Initializing sandbox: {sandbox_name}", bold=True))
    env.init()
    click.echo(
        colorize(f"Sandbox {sandbox_name} initialized successfully.", color="green")
    )


@cli.command()
@click.argument("source_dir", required=False)
@click.option(
    "--sandbox", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
def build(source_dir, sandbox):
    """Build a package in the specified sandbox."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    builder = BuildManager(env)
    click.echo(colorize(f"Building in sandbox: {sandbox_name}", bold=True))
    builder.build(source_dir, env.apt_conf)
    click.echo(colorize(f"Build completed in sandbox {sandbox_name}.", color="green"))


@cli.command()
def list():
    """List all existing sandboxes."""
    config = load_config()
    logger.info("Listing all existing sandboxes")
    environment_dir = config["environment_dir"]
    altbuilder_dir = os.path.join(environment_dir, ".sandboxes")
    if not os.path.exists(altbuilder_dir):
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return
    sandboxes = [
        d
        for d in os.listdir(altbuilder_dir)
        if os.path.isdir(os.path.join(altbuilder_dir, d))
    ]
    if not sandboxes:
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
    else:
        click.echo(colorize("Existing sandboxes:", bold=True))
        for sandbox in sandboxes:
            sandbox_path = os.path.join(altbuilder_dir, sandbox)
            click.echo(
                f"{colorize(sandbox, color='cyan', bold=True)} -> {colorize(sandbox_path, color='green')}"
            )
        logger.info(f"Found {len(sandboxes)} sandboxes")
        logger.debug(f"Sandboxes: {', '.join(sandboxes)}")


@cli.command()
@click.option(
    "--sandbox", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option("--root", is_flag=True, help="Run shell as root.")
@click.option("--internet", is_flag=True, help="Enable internet in the shell.")
def shell(sandbox, root, internet):
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


@cli.command()
@click.option(
    "--sandbox", help="Sandbox name to clean. Defaults to <branch>-<arch> from config."
)
@click.option("--all", is_flag=True, help="Clean all sandboxes.")
def clean(sandbox, all):
    """Clean the specified sandbox or all sandboxes."""
    config = load_config()
    base_dir = config["base_dir"]
    altbuilder_dir = os.path.join(base_dir, ".altbuilder")

    if all:
        logger.info("Cleaning all sandboxes")
        if not os.path.exists(altbuilder_dir):
            click.echo(colorize("No sandboxes to clean.", color="yellow"))
            logger.info("No sandboxes found")
            return
        sandboxes = [
            d
            for d in os.listdir(altbuilder_dir)
            if os.path.isdir(os.path.join(altbuilder_dir, d))
        ]
        failed = []
        for sandbox in sandboxes:
            sandbox_path = os.path.join(altbuilder_dir, sandbox)
            cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
            try:
                run_logged_command(cmd, check=True)
                shutil.rmtree(sandbox_path, ignore_errors=True)
                click.echo(colorize(f"Sandbox {sandbox} cleaned.", color="green"))
                logger.info(f"Cleaned sandbox {sandbox}")
            except (subprocess.CalledProcessError, OSError) as e:
                click.echo(colorize(f"Error cleaning {sandbox}: {e}", color="red"))
                logger.error(f"Failed to clean sandbox {sandbox}: {e}")
                failed.append(sandbox)
        if failed:
            click.echo(
                colorize(
                    f"Failed to clean {len(failed)} sandboxes: {', '.join(failed)}",
                    color="red",
                )
            )
            logger.error(f"Failed sandboxes: {', '.join(failed)}")
        else:
            logger.info("All sandboxes cleaned successfully")
    elif sandbox:
        sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
        sandbox_config = get_sandbox_config(sandbox_name, config)
        init_logger(sandbox_name, config["build_logs_dir"], config)
        env = Environment(sandbox_name, sandbox_config)
        try:
            cmd = ["hsh", "--cleanup-only", env.hasher_dir]
            run_logged_command(cmd, check=True)
            env.clean()
            click.echo(colorize(f"Sandbox {sandbox_name} cleaned.", color="green"))
            logger.info(f"Cleaned sandbox {sandbox_name}")
        except (subprocess.CalledProcessError, EnvironmentError) as e:
            click.echo(colorize(f"Error: {e}", color="red"))
            logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
    else:
        click.echo(
            colorize("Please specify a sandbox to clean or use --all.", color="red")
        )


if __name__ == "__main__":
    cli()
