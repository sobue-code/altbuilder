import os
import shutil
import subprocess
import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger, logger
from ..utils.helpers import colorize, run_logged_command


@click.command("clean")
@click.option(
    "--sandbox",
    "-s",
    help="Sandbox name to clean. Defaults to <branch>-<arch> from config.",
)
@click.option("--all", is_flag=True, help="Clean all sandboxes.")
@click.help_option("--help", "-h")
def clean_cmd(sandbox, all):
    """Clean the specified sandbox or all sandboxes."""
    config = load_config()
    environment_dir = config["environment_dir"]
    sandboxes_dir = os.path.join(environment_dir, ".sandboxes")
    logger.debug(f"Cleaning or all sandboxes in {sandboxes_dir}")
    logger.debug(f"{os.listdir(sandboxes_dir)}")

    if all:
        logger.info("Cleaning all sandboxes")
        if not os.path.exists(sandboxes_dir):
            click.echo(colorize("No sandboxes to clean.", color="yellow"))
            logger.info("No sandboxes found")
            return
        sandboxes = [
            d
            for d in os.listdir(sandboxes_dir)
            if os.path.isdir(os.path.join(sandboxes_dir, d))
        ]
        failed = []
        for sandbox in sandboxes:
            sandbox_path = os.path.join(sandboxes_dir, sandbox)
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
            if not env.exists():
                click.echo(
                    colorize(f"Sandbox {sandbox_name} does not exist.", color="red")
                )
                return
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
