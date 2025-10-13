import json
import os
import signal

import typer

from altbuilder.config import load_config
from altbuilder.utils.logger import logger
from altbuilder.utils.metrics import Metrics
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="stop",
    help="Stop the currently running task.",
)


@app.command(name="stop")
def stop_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", "-f", help="Forcefully stop the task without confirmation."
    ),
):
    """Stop the current running task."""
    json_mode = is_json_mode(ctx)
    config = load_config()
    metrics = Metrics(base_dir=config["base_dir"])
    task = metrics.get_current_task()

    if not task:
        message = "No tasks are currently running."
        logger.info(message)
        if json_mode:
            json_response(ctx, "success", message=message, task=None)
        else:
            typer.echo(message)
        return

    # Show task details
    logger.info("Current task details:")
    if not json_mode:
        typer.echo(json.dumps(task, indent=2, ensure_ascii=False))

    # Ask for confirmation if not forced
    if not force and not json_mode:
        typer.echo(
            f"\nYou are about to stop the task (PID: {task['pid']}, Command: {task['command']})."
        )
        confirm = typer.confirm("Do you want to proceed?", default=False)
        if not confirm:
            logger.info("Task termination cancelled.")
            typer.echo("Task termination cancelled.")
            raise typer.Exit()

    # В JSON mode --force автоматически применяется
    pid = task["pid"]
    temp_json_path = os.path.join(config["base_dir"], "current_task.json")

    try:
        os.kill(pid, signal.SIGTERM)
        success_msg = f"Task (PID: {pid}) terminated."
        logger.info(f"Sent termination signal to task (PID: {pid})")

        # Clean up task state file
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

        if json_mode:
            json_response(
                ctx,
                "success",
                message=success_msg,
                task=task,
                pid=pid,
            )
        else:
            typer.echo(success_msg)

    except ProcessLookupError:
        warning_msg = f"Process with PID {pid} does not exist."
        logger.warning(warning_msg)

        # Remove stale task file
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

        if json_mode:
            json_response(
                ctx,
                "error",
                message=warning_msg,
                task=task,
                pid=pid,
                code=1,
            )
        else:
            typer.echo(warning_msg)

    except OSError as e:
        error_msg = f"Failed to terminate process with PID {pid}: {e}"
        logger.error(error_msg)
        if json_mode:
            json_response(
                ctx,
                "error",
                message=error_msg,
                task=task,
                pid=pid,
                code=1,
            )
        else:
            typer.echo(error_msg)
            raise typer.Abort()


if __name__ == "__main__":
    app()
