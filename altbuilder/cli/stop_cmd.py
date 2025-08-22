import json
import os
import signal

import typer

from altbuilder.config import load_config
from altbuilder.utils.logger import logger
from altbuilder.utils.metrics import Metrics

app = typer.Typer(
    name="stop",
    help="Stop the currently running task.",
)


@app.command(name="stop")
def stop_cmd(
    force: bool = typer.Option(
        False, "--force", "-f", help="Forcefully stop the task without confirmation."
    ),
):
    """Stop the current running task."""
    config = load_config()
    metrics = Metrics(base_dir=config["base_dir"])
    task = metrics.get_current_task()

    if not task:
        logger.info("No tasks are currently running.")
        typer.echo("No tasks are currently running.")
        raise typer.Exit()

    # Show task details
    logger.info("Current task details:")
    typer.echo(json.dumps(task, indent=2, ensure_ascii=False))

    # Ask for confirmation if not forced
    if not force:
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
        typer.echo(f"Task (PID: {pid}) terminated.")

        # Clean up task state file
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

    except ProcessLookupError:
        logger.warning(f"Process with PID {pid} does not exist.")
        typer.echo(f"Process with PID {pid} does not exist.")

        # Remove stale task file
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

    except OSError as e:
        logger.error(f"Failed to terminate process with PID {pid}: {e}")
        raise typer.Abort()


if __name__ == "__main__":
    app()
