import os
import shutil
import subprocess
import typer
from altbuilder.config import load_config, get_sandbox_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger, colorize, run_logged_command

app = typer.Typer(
    name="clean",
    help="Clean the specified sandbox or all sandboxes.",
)

@app.command()
def clean_cmd(
    ctx: typer.Context,
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name to clean. Defaults to <branch>-<arch> from config.",
    ),
    all: bool = typer.Option(
        False, "--all", help="Clean all sandboxes."
    ),
):
    """Clean the specified sandbox or all sandboxes."""
    config = load_config()
    environment_dir = config["environment_dir"]
    logger.debug(f"Cleaning or all sandboxes in {environment_dir}")
    logger.debug(f"{os.listdir(environment_dir)}")

    def suggest_manual_removal(sandbox_path):
        manual_cmd = f"sudo rm -rf {sandbox_path}"
        typer.echo(
            colorize(
                f"Permission issue detected. Please remove the sandbox manually: \n\t {manual_cmd}",
                color="yellow",
            )
        )

    if all:
        logger.info("Cleaning all sandboxes")
        if not os.path.exists(environment_dir):
            typer.echo(colorize("No sandboxes to clean.", color="yellow"))
            logger.info("No sandboxes found")
            return
        sandboxes = [
            d
            for d in os.listdir(environment_dir)
            if os.path.isdir(os.path.join(environment_dir, d))
        ]
        failed = []
        for sandbox_name in sandboxes:
            sandbox_path = os.path.join(environment_dir, sandbox_name)
            env = Environment(sandbox_name, get_sandbox_config(sandbox_name, config))
            try:
                if env.is_partially_initialized() and not env.exists():
                    logger.info(f"Removing partially initialized sandbox {sandbox_name}")
                    shutil.rmtree(sandbox_path)
                    if os.path.exists(sandbox_path):
                        suggest_manual_removal(sandbox_path)
                        raise OSError(f"Failed to remove directory {sandbox_path}")
                    typer.echo(colorize(f"Sandbox {sandbox_name} cleaned.", color="green"))
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                else:
                    cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
                    run_logged_command(cmd, check=True)
                    shutil.rmtree(sandbox_path)
                    if os.path.exists(sandbox_path):
                        suggest_manual_removal(sandbox_path)
                        raise OSError(f"Failed to remove directory {sandbox_path}")
                    typer.echo(colorize(f"Sandbox {sandbox_name} cleaned.", color="green"))
                    logger.info(f"Cleaned sandbox {sandbox_name}")
            except (subprocess.CalledProcessError, OSError) as e:
                typer.echo(colorize(f"Error cleaning {sandbox_name}: {e}", color="red"))
                logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
                suggest_manual_removal(sandbox_path)
                failed.append(sandbox_name)
        if failed:
            typer.echo(
                colorize(
                    f"Failed to clean {len(failed)} sandboxes: {', '.join(failed)}",
                    color="red",
                )
            )
            logger.error(f"Failed sandboxes: {', '.join(failed)}")
        else:
            logger.info("All sandboxes cleaned successfully")
    elif sandbox:
        sandbox_name = sandbox or ctx.obj.get("sandbox") or f"{config['branch']}-{config['arch']}"
        sandbox_config = get_sandbox_config(sandbox_name, config)
        init_logger(sandbox_name, config["build_logs_dir"], config)
        env = Environment(sandbox_name, sandbox_config)
        try:
            if not env.exists():
                if env.is_partially_initialized():
                    typer.echo(
                        colorize(
                            f"Sandbox {sandbox_name} exists but is not fully initialized. Cleaning ...",
                            color="yellow",
                        )
                    )
                    logger.info(
                        f"Removing partially initialized sandbox {sandbox_name}"
                    )
                    shutil.rmtree(env.environment_dir)
                    if os.path.exists(env.environment_dir):
                        suggest_manual_removal(env.environment_dir)
                        raise OSError(
                            f"Failed to remove directory {env.environment_dir}"
                        )
                    typer.echo(
                        colorize(f"Sandbox {sandbox_name} cleaned.", color="green")
                    )
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                    return
                typer.echo(
                    colorize(f"Sandbox {sandbox_name} does not exist.", color="red")
                )
                return
            env.clean()
            typer.echo(colorize(f"Sandbox {sandbox_name} cleaned.", color="green"))
            logger.info(f"Cleaned sandbox {sandbox_name}")
        except (subprocess.CalledProcessError, EnvironmentError, OSError) as e:
            typer.echo(colorize(f"Error: {e}", color="red"))
            logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
            suggest_manual_removal(env.environment_dir)
            raise typer.Exit(code=1)
    else:
        typer.echo(
            colorize("Please specify a sandbox to clean or use --all.", color="red")
        )

if __name__ == "__main__":
    app()
