import os
import subprocess

import click

from ..config import get_sandbox_config, load_config
from ..core.environment import Environment
from ..utils import colorize, init_logger, logger


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

        # Check if pyproject_deps.json is already tracked in git
        pyproject_tracked = False
        try:
            subprocess.run(
                ["git", "ls-files", ".gear/pyproject_deps.json"],
                capture_output=True,
                check=True,
                text=True,
            )
            pyproject_tracked = True
        except subprocess.CalledProcessError:
            pyproject_tracked = False

        # Stage the pyproject_deps.json file
        subprocess.run(["git", "add", ".gear/pyproject_deps.json"], check=True)

        # Commit only if the file was already tracked
        if pyproject_tracked:
            commit_message = "Update pyproject_deps.json"
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            logger.info(
                f"pyproject_deps.json updated and committed in sandbox {sandbox_name}"
            )
        else:
            logger.info(
                f"""pyproject_deps.json added to git index but not committed in sandbox {sandbox_name}.
                Don't forget to add this line to your .gear/rules file:

                copy: .gear/pyproject_deps.json

                And this to your .spec:

                SourceX: %pyproject_deps_config_name
                """
            )

        click.echo(colorize(f"pyproject_deps.json copied to .gear/", color="green"))
        logger.info(f"pyproject_deps.json copied to .gear/ in sandbox {sandbox_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy or commit pyproject_deps.json: {e}")
        click.echo(
            colorize(f"Failed to copy or commit pyproject_deps.json: {e}", color="red")
        )
        raise
