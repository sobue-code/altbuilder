import os
import click
import subprocess
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils import init_logger, logger, colorize


@click.command("copy-pyproject-deps")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.help_option("--help", "-h")
def copy_pyproject_deps(sandbox):
    """Copy pyproject_deps.json from sandbox to .gear/ directory."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    if not env.exists():
        logger.warning(f"Sandbox {sandbox_name} does not exist, initializing...")
        env.init()

    logger.info(f"Copying pyproject_deps.json from sandbox {sandbox_name} to .gear/")
    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        'cat "$(rpm --eval %pyproject_deps_config)"',
    ]
    try:
        os.makedirs(".gear", exist_ok=True)
        with open(".gear/pyproject_deps.json", "w") as f:
            subprocess.run(cmd, stdout=f, check=True)
        click.echo(colorize(f"pyproject_deps.json copied to .gear/", color="green"))
        logger.info(f"pyproject_deps.json copied to .gear/ in sandbox {sandbox_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy pyproject_deps.json: {e}")
        click.echo(colorize(f"Failed to copy pyproject_deps.json: {e}", color="red"))
        raise
