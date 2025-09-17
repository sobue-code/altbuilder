import json
import os
import signal

import typer

from altbuilder.config import load_config
from altbuilder.utils.json_utils import is_json_mode, json_response
from altbuilder.utils.logger import logger
from altbuilder.utils.metrics import Metrics

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
    params = {"force": force}
    config = load_config()
    metrics = Metrics(base_dir=config["base_dir"])
    task = metrics.get_current_task()

    if not task:
        logger.info("No tasks are currently running.")
        message = "No tasks are currently running."
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                task=None,
            )
        else:
            typer.echo(message)
        raise typer.Exit()

    # Show task details
    logger.info("Current task details:")
    if not json_mode:
        typer.echo(json.dumps(task, indent=2, ensure_ascii=False))

    # Ask for confirmation if not forced
    if not force:
        if json_mode:
            json_response(
                ctx,
                "error",
                params=params,
                message="Use --force with --json to skip confirmation.",
                code=1,
                task=task,
            )
            return
        typer.echo(
            f"\nYou are about to stop the task (PID: {task['pid']}, Command: {task['command']})."
        )
        confirm = typer.confirm("Do you want to proceed?", default=False)
        if not confirm:
            logger.info("Task termination cancelled.")
            typer.echo("Task termination cancelled.")
            raise typer.Exit()

    pid = task["pid"]
    temp_json_path = os.path.join(config["base_dir"], "current_task.json")

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Sent termination signal to task (PID: {pid})")
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)
        message = f"Task (PID: {pid}) terminated."
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                task=task,
            )
        else:
            typer.echo(message)

    except ProcessLookupError:
        logger.warning(f"Process with PID {pid} does not exist.")
        message = f"Process with PID {pid} does not exist."
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                task=task,
            )
        else:
            typer.echo(message)

        # Remove stale task file
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

    except OSError as e:
        logger.error(f"Failed to terminate process with PID {pid}: {e}")
        message = f"Failed to terminate process with PID {pid}: {e}"
        if json_mode:
            json_response(
                ctx,
                "error",
                params=params,
                message=message,
                code=1,
                task=task,
            )
        else:
            raise typer.Abort()


if __name__ == "__main__":
    app()
