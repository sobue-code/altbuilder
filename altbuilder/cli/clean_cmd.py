import os
import shutil
import subprocess
import typer
from rich import print as rich_print
from altbuilder.config import load_config, get_sandbox_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger, run_logged_command
from altbuilder.utils.json_utils import is_json_mode, json_response

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
    json_mode = is_json_mode(ctx)
    config = load_config()
    environment_dir = config["environment_dir"]
    logger.debug(f"Cleaning or all sandboxes in {environment_dir}")
    logger.debug(f"{os.listdir(environment_dir)}")

    def suggest_manual_removal(sandbox_path):
        manual_cmd = f"sudo rm -rf {sandbox_path}"
        if not json_mode:
            rich_print(
                f"[yellow]Permission issue detected. Please remove the sandbox manually: \n\t {manual_cmd}[/yellow]"
            )

    if all:
        logger.info("Cleaning all sandboxes")
        if not os.path.exists(environment_dir):
            message = "No sandboxes to clean."
            logger.info("No sandboxes found")
            if json_mode:
                json_response(ctx, "success", message=message, cleaned=[], failed=[])
            else:
                rich_print("[yellow]No sandboxes to clean.[/yellow]")
            return
        sandboxes = [
            d
            for d in os.listdir(environment_dir)
            if os.path.isdir(os.path.join(environment_dir, d))
        ]
        cleaned = []
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
                    if not json_mode:
                        rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                    cleaned.append(sandbox_name)
                else:
                    cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
                    run_logged_command(cmd, check=True)
                    shutil.rmtree(sandbox_path)
                    if os.path.exists(sandbox_path):
                        suggest_manual_removal(sandbox_path)
                        raise OSError(f"Failed to remove directory {sandbox_path}")
                    if not json_mode:
                        rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                    cleaned.append(sandbox_name)
            except (subprocess.CalledProcessError, OSError) as e:
                if not json_mode:
                    rich_print(f"[red]Error cleaning {sandbox_name}: {e}[/red]")
                logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
                suggest_manual_removal(sandbox_path)
                failed.append(sandbox_name)

        if json_mode:
            if failed:
                json_response(
                    ctx,
                    "partial_success" if cleaned else "error",
                    message=f"Cleaned {len(cleaned)}/{len(sandboxes)} sandboxes. {len(failed)} failed.",
                    cleaned=cleaned,
                    failed=failed,
                    code=1 if not cleaned else 0,
                )
            else:
                json_response(
                    ctx,
                    "success",
                    message=f"All {len(cleaned)} sandboxes cleaned successfully.",
                    cleaned=cleaned,
                    failed=[],
                )
        else:
            if failed:
                rich_print(
                    f"[red]Failed to clean {len(failed)} sandboxes: {', '.join(failed)}[/red]"
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
                    if not json_mode:
                        rich_print(
                            f"[yellow]Sandbox {sandbox_name} exists but is not fully initialized. Cleaning ...[/yellow]"
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
                    success_msg = f"Sandbox {sandbox_name} cleaned."
                    logger.info(success_msg)
                    if json_mode:
                        json_response(ctx, "success", message=success_msg, sandbox=sandbox_name)
                    else:
                        rich_print(f"[green]{success_msg}[/green]")
                    return
                error_msg = f"Sandbox {sandbox_name} does not exist."
                if json_mode:
                    json_response(ctx, "error", message=error_msg, code=1)
                else:
                    rich_print(f"[red]{error_msg}[/red]")
                return
            env.clean()
            success_msg = f"Sandbox {sandbox_name} cleaned."
            logger.info(success_msg)
            if json_mode:
                json_response(ctx, "success", message=success_msg, sandbox=sandbox_name)
            else:
                rich_print(f"[green]{success_msg}[/green]")
        except (subprocess.CalledProcessError, EnvironmentError, OSError) as e:
            error_msg = f"Failed to clean sandbox {sandbox_name}: {e}"
            logger.error(error_msg)
            suggest_manual_removal(env.environment_dir)
            if json_mode:
                json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, code=1)
            else:
                rich_print(f"[red]Error: {e}[/red]")
                raise typer.Exit(code=1)
    else:
        error_msg = "Please specify a sandbox to clean or use --all."
        if json_mode:
            json_response(ctx, "error", message=error_msg, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")

if __name__ == "__main__":
    app()
