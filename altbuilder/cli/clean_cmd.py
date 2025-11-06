import os
import shutil
import subprocess

import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger, run_logged_command
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="clean",
    help="Clean sandboxes and/or logs.",
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
        False, "--all", help="Clean all sandboxes (or all logs if --logs is specified)."
    ),
    logs: bool = typer.Option(
        False, "--logs", help="Clean logs instead of (or in addition to) sandboxes."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompts."
    ),
):
    """Clean sandboxes and/or logs.

    \b
    Examples:
      altbuilder clean -s test          # Clean sandbox "test"
      altbuilder clean --all            # Clean all sandboxes
      altbuilder clean --logs           # Clean all logs
      altbuilder clean --logs -s test   # Clean logs for sandbox "test"
      altbuilder clean -s test --logs   # Clean sandbox "test" AND its logs
      altbuilder clean --all --logs     # Clean everything
      altbuilder clean --logs -f        # Clean all logs without confirmation
    """
    json_mode = is_json_mode(ctx)
    config = load_config()
    environment_dir = config["environment_dir"]
    build_logs_dir = config["build_logs_dir"]

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    def suggest_manual_removal(sandbox_path):
        manual_cmd = f"sudo rm -rf {sandbox_path}"
        if not json_mode:
            rich_print(
                f"[yellow]Permission issue detected. Please remove the sandbox manually: \n\t {manual_cmd}[/yellow]"
            )

    # Validate that at least something is specified to clean
    if not all and not sandbox and not logs:
        error_msg = "Please specify what to clean: use --sandbox/-s, --all, or --logs."
        if json_mode:
            json_response(ctx, "error", message=error_msg, code=1)
        else:
            rich_print(f"[red]{error_msg}[/red]")
        return

    result = {
        "sandboxes_cleaned": [],
        "sandboxes_failed": [],
        "logs_cleaned": [],
        "logs_failed": [],
    }

    # PART 1: Clean sandboxes (if --logs is not the only flag)
    if not logs or (logs and (sandbox or all)):
        if all:
            # Clean all sandboxes
            logger.info("Cleaning all sandboxes")
            if not os.path.exists(environment_dir):
                message = "No sandboxes to clean."
                logger.info("No sandboxes found")
                if not logs:  # If only cleaning sandboxes, return here
                    if json_mode:
                        json_response(ctx, "success", message=message, **result)
                    else:
                        rich_print("[yellow]No sandboxes to clean.[/yellow]")
                    return
            else:
                sandboxes = [
                    d
                    for d in os.listdir(environment_dir)
                    if os.path.isdir(os.path.join(environment_dir, d))
                ]
                for sandbox_name in sandboxes:
                    sandbox_path = os.path.join(environment_dir, sandbox_name)
                    env = Environment(
                        sandbox_name, get_sandbox_config(sandbox_name, config)
                    )
                    try:
                        if env.is_partially_initialized() and not env.exists():
                            logger.info(
                                f"Removing partially initialized sandbox {sandbox_name}"
                            )
                            shutil.rmtree(sandbox_path)
                            if os.path.exists(sandbox_path):
                                suggest_manual_removal(sandbox_path)
                                raise OSError(
                                    f"Failed to remove directory {sandbox_path}"
                                )
                            if not json_mode:
                                rich_print(
                                    f"[green]Sandbox {sandbox_name} cleaned.[/green]"
                                )
                            logger.info(f"Cleaned sandbox {sandbox_name}")
                            result["sandboxes_cleaned"].append(sandbox_name)
                        else:
                            cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
                            run_logged_command(cmd, check=True)
                            shutil.rmtree(sandbox_path)
                            if os.path.exists(sandbox_path):
                                suggest_manual_removal(sandbox_path)
                                raise OSError(
                                    f"Failed to remove directory {sandbox_path}"
                                )
                            if not json_mode:
                                rich_print(
                                    f"[green]Sandbox {sandbox_name} cleaned.[/green]"
                                )
                            logger.info(f"Cleaned sandbox {sandbox_name}")
                            result["sandboxes_cleaned"].append(sandbox_name)
                    except (subprocess.CalledProcessError, OSError) as e:
                        if not json_mode:
                            rich_print(f"[red]Error cleaning {sandbox_name}: {e}[/red]")
                        logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
                        suggest_manual_removal(sandbox_path)
                        result["sandboxes_failed"].append(sandbox_name)

        elif sandbox:
            # Clean specific sandbox
            sandbox_name = sandbox
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
                        if not json_mode:
                            rich_print(f"[green]{success_msg}[/green]")
                        result["sandboxes_cleaned"].append(sandbox_name)
                    else:
                        error_msg = f"Sandbox {sandbox_name} does not exist."
                        if not logs:  # If only cleaning sandbox, this is an error
                            if json_mode:
                                json_response(ctx, "error", message=error_msg, code=1)
                            else:
                                rich_print(f"[red]{error_msg}[/red]")
                            return
                        else:
                            # If also cleaning logs, just warn
                            logger.warning(error_msg)
                            if not json_mode:
                                rich_print(f"[yellow]{error_msg}[/yellow]")
                else:
                    env.clean()
                    success_msg = f"Sandbox {sandbox_name} cleaned."
                    logger.info(success_msg)
                    if not json_mode:
                        rich_print(f"[green]{success_msg}[/green]")
                    result["sandboxes_cleaned"].append(sandbox_name)
            except (subprocess.CalledProcessError, EnvironmentError, OSError) as e:
                error_msg = f"Failed to clean sandbox {sandbox_name}: {e}"
                logger.error(error_msg)
                suggest_manual_removal(env.environment_dir)
                result["sandboxes_failed"].append(sandbox_name)
                if not logs:  # If only cleaning sandbox, raise error
                    if json_mode:
                        json_response(
                            ctx,
                            "error",
                            message=error_msg,
                            sandbox=sandbox_name,
                            code=1,
                        )
                    else:
                        rich_print(f"[red]Error: {e}[/red]")
                        raise typer.Exit(code=1)
                else:
                    # If also cleaning logs, continue
                    if not json_mode:
                        rich_print(f"[red]Error: {e}[/red]")

    # PART 2: Clean logs
    if logs:
        if all:
            # Clean all logs
            if not os.path.exists(build_logs_dir):
                message = "No logs to clean."
                logger.info("No logs found")
                if not json_mode and not result["sandboxes_cleaned"]:
                    rich_print("[yellow]No logs to clean.[/yellow]")
            else:
                try:
                    if force or typer.confirm(
                        f"Are you sure you want to remove all logs at {build_logs_dir}?"
                    ):
                        shutil.rmtree(build_logs_dir, ignore_errors=True)
                        os.makedirs(
                            build_logs_dir, exist_ok=True
                        )  # Recreate empty directory
                        if not json_mode:
                            rich_print(f"[green]All logs removed successfully.[/green]")
                        logger.info(f"Removed all logs at {build_logs_dir}")
                        result["logs_cleaned"].append("all")
                    else:
                        if not json_mode:
                            rich_print("[yellow]Log cleanup cancelled.[/yellow]")
                except OSError as e:
                    error_msg = f"Error removing logs at {build_logs_dir}: {e}"
                    if not json_mode:
                        rich_print(f"[red]{error_msg}[/red]")
                    logger.error(error_msg)
                    result["logs_failed"].append("all")
        elif sandbox:
            # Clean logs for specific sandbox
            sandbox_name = sandbox
            log_dir = os.path.join(build_logs_dir, sandbox_name)
            if not os.path.exists(log_dir):
                message = f"No logs found for sandbox {sandbox_name}."
                logger.info(message)
                if not json_mode and not result["sandboxes_cleaned"]:
                    rich_print(f"[yellow]{message}[/yellow]")
            else:
                try:
                    if force or typer.confirm(
                        f"Are you sure you want to remove logs for sandbox {sandbox_name} at {log_dir}?"
                    ):
                        shutil.rmtree(log_dir, ignore_errors=True)
                        if not json_mode:
                            rich_print(
                                f"[green]Logs for sandbox {sandbox_name} removed successfully.[/green]"
                            )
                        logger.info(
                            f"Removed logs for sandbox {sandbox_name} at {log_dir}"
                        )
                        result["logs_cleaned"].append(sandbox_name)
                    else:
                        if not json_mode:
                            rich_print("[yellow]Log cleanup cancelled.[/yellow]")
                except OSError as e:
                    error_msg = f"Error removing logs at {log_dir}: {e}"
                    if not json_mode:
                        rich_print(f"[red]{error_msg}[/red]")
                    logger.error(error_msg)
                    result["logs_failed"].append(sandbox_name)

    # Final summary
    if json_mode:
        has_failures = result["sandboxes_failed"] or result["logs_failed"]
        has_success = result["sandboxes_cleaned"] or result["logs_cleaned"]

        if has_failures and not has_success:
            status = "error"
            code = 1
        elif has_failures and has_success:
            status = "partial_success"
            code = 0
        else:
            status = "success"
            code = 0

        json_response(ctx, status, code=code, **result)
    else:
        if result["sandboxes_failed"]:
            rich_print(
                f"[red]Failed to clean {len(result['sandboxes_failed'])} sandboxes: {', '.join(result['sandboxes_failed'])}[/red]"
            )
        if result["logs_failed"]:
            rich_print(
                f"[red]Failed to clean logs: {', '.join(result['logs_failed'])}[/red]"
            )


if __name__ == "__main__":
    app()
