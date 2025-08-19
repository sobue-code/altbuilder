import os
import subprocess

import click

from ..config import get_sandbox_config, load_config
from ..core.environment import Environment
from ..utils import colorize, init_logger, logger
from ..utils.metrics import Metrics


@click.command("npm-update-vendor")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize sandbox if it already exists."
)
@click.argument("tag", required=False, default="")
@click.help_option("--help", "-h")
def npm_update_vendor(sandbox, reinit, tag):
    """Update NPM vendor dependencies, optionally using a specific tag."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating NPM vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
    )
    if env.exists() and reinit:
        logger.info(f"Reinitializing sandbox {sandbox_name} due to --reinit flag")
        env.clean()
        env.init()
    elif not env.exists():
        logger.info(f"Initializing new sandbox {sandbox_name}")
        env.init()
    else:
        logger.info(f"Using existing sandbox {sandbox_name}")

    env.enable_internet()
    env.install(["npm", "nodejs", "git"])

    try:
        subprocess.run(["git", "rev-parse", "--verify", "upstream"], check=True)
    except subprocess.CalledProcessError:
        logger.info("Restoring upstream branch...")
        subprocess.run(["gear-remotes-restore"], check=True)

    upstream_url = (
        subprocess.check_output(["git", "config", "--get", "remote.upstream.url"])
        .decode()
        .strip()
    )
    if not upstream_url:
        raise ValueError("Upstream URL is empty.")

    tag_cmd = f"git switch -c alt_vendor_nodejs '{tag}';" if tag else ""
    env_vars = os.environ.copy()
    env_vars["share_ipc"] = "yes"
    env_vars["share_network"] = "yes"

    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        f"""
        set -e;
        cd /usr/src;
        rm -rf package_nodejs;
        git clone '{upstream_url}' package_nodejs;
        cd package_nodejs;
        {tag_cmd}
        
        rm -rf node_modules;
        
        # Install dependencies using appropriate npm command
        if [ -s package-lock.json ]; then
            npm ci || npm install;
        else
            npm install;
        fi
        """,
    ]
    metrics = Metrics(base_dir=config["base_dir"])
    with metrics.track_command(command=" ".join(cmd), sandbox_name=sandbox_name):
        subprocess.run(cmd, env=env_vars, check=True)

    # Copy node_modules from sandbox to host using copy_from
    try:
        env.copy_from("/usr/src/package_nodejs/node_modules", "./node_modules")
        # Check if node_modules directory is already tracked in git
        node_modules_tracked = False
        try:
            subprocess.run(
                ["git", "ls-files", "node_modules"],
                capture_output=True,
                check=True,
                text=True,
            )
            node_modules_tracked = True
        except subprocess.CalledProcessError:
            node_modules_tracked = False

        # Stage the node_modules directory
        subprocess.run(["git", "add", "node_modules"], check=True)

        # Commit with appropriate message
        commit_message = (
            "Update NPM dependencies"
            if node_modules_tracked
            else "Vendoring NPM dependencies"
        )
        subprocess.run(["git", "commit", "-m", commit_message], check=True)

        click.echo(
            colorize(
                f"""NPM vendor dependencies updated and committed successfully.
                    Don't forget to add the following line to your .gear/rules:

                    tar: node_modules name=node_modules

                    And this to your .spec:

                    SourceX: node_modules.tar

                    %setup -a X
                """,
                color="green",
            )
        )
        logger.info(
            f"NPM vendor dependencies updated and committed in sandbox {sandbox_name}"
        )
    except EnvironmentError as e:
        logger.error(f"Failed to update NPM vendor dependencies: {e}")
        click.echo(
            colorize(f"Failed to update NPM vendor dependencies: {e}", color="red")
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit NPM vendor dependencies: {e}")
        click.echo(
            colorize(f"Failed to commit NPM vendor dependencies: {e}", color="red")
        )
        raise
