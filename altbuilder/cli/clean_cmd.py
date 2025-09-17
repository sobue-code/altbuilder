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
    all: bool = typer.Option(False, "--all", help="Clean all sandboxes."),
):
    """Clean the specified sandbox or all sandboxes."""
    json_mode = is_json_mode(ctx)
    params = {"sandbox": sandbox, "all": all}

    config = load_config()
    environment_dir = config["environment_dir"]
    logger.debug(f"Cleaning or all sandboxes in {environment_dir}")
    logger.debug(f"{os.listdir(environment_dir)}")

    def suggest_manual_removal(sandbox_path, collector):
        manual_cmd = f"sudo rm -rf {sandbox_path}"
        message = f"Permission issue detected. Please remove the sandbox manually:\n\t {manual_cmd}"
        if json_mode:
            collector.append({"sandbox_path": sandbox_path, "command": manual_cmd})
        else:
            rich_print(f"[yellow]{message}[/yellow]")

    if all:
        manual_actions = []
        cleaned = []
        failed = []

        logger.info("Cleaning all sandboxes")
        if not os.path.exists(environment_dir):
            message = "No sandboxes to clean."
            if json_mode:
                json_response(
                    ctx,
                    "success",
                    params=params,
                    message=message,
                    cleaned=[],
                    failed=[],
                )
            else:
                rich_print("[yellow]No sandboxes to clean.[/yellow]")
            logger.info("No sandboxes found")
            return
        sandboxes = [
            d
            for d in os.listdir(environment_dir)
            if os.path.isdir(os.path.join(environment_dir, d))
        ]
        if not sandboxes:
            message = "No sandboxes to clean."
            if json_mode:
                json_response(
                    ctx,
                    "success",
                    params=params,
                    message=message,
                    cleaned=[],
                    failed=[],
                )
            else:
                rich_print("[yellow]No sandboxes to clean.[/yellow]")
            logger.info("No sandboxes found")
            return
        for sandbox_name in sandboxes:
            sandbox_path = os.path.join(environment_dir, sandbox_name)
            env = Environment(sandbox_name, get_sandbox_config(sandbox_name, config))
            try:
                if env.is_partially_initialized() and not env.exists():
                    logger.info(
                        f"Removing partially initialized sandbox {sandbox_name}"
                    )
                    shutil.rmtree(sandbox_path)
                    if os.path.exists(sandbox_path):
                        suggest_manual_removal(sandbox_path, manual_actions)
                        raise OSError(f"Failed to remove directory {sandbox_path}")
                    cleaned.append(sandbox_name)
                    if not json_mode:
                        rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                else:
                    cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
                    run_logged_command(cmd, check=True)
                    shutil.rmtree(sandbox_path)
                    if os.path.exists(sandbox_path):
                        suggest_manual_removal(sandbox_path, manual_actions)
                        raise OSError(f"Failed to remove directory {sandbox_path}")
                    cleaned.append(sandbox_name)
                    if not json_mode:
                        rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
                    logger.info(f"Cleaned sandbox {sandbox_name}")
            except (subprocess.CalledProcessError, OSError) as e:
                if not json_mode:
                    rich_print(f"[red]Error cleaning {sandbox_name}: {e}[/red]")
                logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
                suggest_manual_removal(sandbox_path, manual_actions)
                failed.append(sandbox_name)
        if json_mode:
            message = (
                f"Failed to clean {len(failed)} sandboxes: {', '.join(failed)}"
                if failed
                else "All sandboxes cleaned successfully."
            )
            extra = {"cleaned": cleaned, "failed": failed}
            if manual_actions:
                extra["manual_cleanup"] = manual_actions
            json_response(ctx, "success", params=params, message=message, **extra)
            return
        if failed:
            rich_print(
                f"[red]Failed to clean {len(failed)} sandboxes: {', '.join(failed)}[/red]"
            )
            logger.error(f"Failed sandboxes: {', '.join(failed)}")
        else:
            logger.info("All sandboxes cleaned successfully")
    elif sandbox:
        manual_actions = []
        sandbox_name = (
            sandbox or ctx.obj.get("sandbox") or f"{config['branch']}-{config['arch']}"
        )
        params["sandbox"] = sandbox_name
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
                        suggest_manual_removal(env.environment_dir, manual_actions)
                        raise OSError(
                            f"Failed to remove directory {env.environment_dir}"
                        )
                    if json_mode:
                        extra = {"cleaned": [sandbox_name]}
                        if manual_actions:
                            extra["manual_cleanup"] = manual_actions
                        json_response(
                            ctx,
                            "success",
                            params=params,
                            message=f"Sandbox {sandbox_name} cleaned.",
                            **extra,
                        )
                    else:
                        rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
                    logger.info(f"Cleaned sandbox {sandbox_name}")
                    return
                message = f"Sandbox {sandbox_name} does not exist."
                if json_mode:
                    json_response(
                        ctx,
                        "error",
                        params=params,
                        message=message,
                        code=1,
                        cleaned=[],
                        failed=[sandbox_name],
                    )
                else:
                    rich_print(f"[red]{message}[/red]")
                return
            env.clean()
            logger.info(f"Cleaned sandbox {sandbox_name}")
            if json_mode:
                json_response(
                    ctx,
                    "success",
                    params=params,
                    message=f"Sandbox {sandbox_name} cleaned.",
                    cleaned=[sandbox_name],
                )
            else:
                rich_print(f"[green]Sandbox {sandbox_name} cleaned.[/green]")
        except (subprocess.CalledProcessError, EnvironmentError, OSError) as e:
            message = f"Error: {e}"
            if not json_mode:
                rich_print(f"[red]{message}[/red]")
            logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
            suggest_manual_removal(env.environment_dir, manual_actions)
            if json_mode:
                extra = {"sandbox": sandbox_name}
                if manual_actions:
                    extra["manual_cleanup"] = manual_actions
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    **extra,
                )
            else:
                raise typer.Exit(code=1)
    else:
        message = "Please specify a sandbox to clean or use --all."
        if json_mode:
            json_response(
                ctx,
                "error",
                params=params,
                message=message,
                code=1,
            )
        else:
            rich_print("[red]Please specify a sandbox to clean or use --all.[/red]")


if __name__ == "__main__":
    app()
