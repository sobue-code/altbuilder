import click
import json
import os
import signal
from ..config import load_config
from ..utils.metrics import Metrics
from ..utils.logger import logger


@click.command("stop")
@click.option(
    "--force",
    is_flag=True,
    help="Forcefully stop the task without confirmation.",
)
@click.help_option("--help", "-h")
def stop_cmd(force):
    """Stop the current running task."""
    config = load_config()

    # Initialize Metrics with base directory
    metrics = Metrics(base_dir=config["base_dir"])
    task = metrics.get_current_task()

    if not task:
        logger.info("No tasks are currently running.")
        click.echo("No tasks are currently running.")
        return

    # Display task information
    logger.info("Current task details:")
    click.echo(json.dumps(task, indent=2, ensure_ascii=False))

    # Ask for confirmation unless --force is specified
    if not force:
        click.echo(
            f"\nYou are about to stop the task (PID: {task['pid']}, Command: {task['command']})."
        )
        confirm = click.confirm("Do you want to proceed?", default=False)
        if not confirm:
            logger.info("Task termination cancelled.")
            click.echo("Task termination cancelled.")
            return

    # Handle task termination
    pid = task["pid"]
    try:
        os.kill(pid, signal.SIGTERM)  # Send SIGTERM for graceful termination
        logger.info(f"Sent termination signal to task (PID: {pid})")
        click.echo(f"Task (PID: {pid}) terminated.")
        # Remove the task file to allow new tasks
        temp_json_path = os.path.join(config["base_dir"], "current_task.json")
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)
    except ProcessLookupError:
        logger.warning(f"Process with PID {pid} does not exist")
        click.echo(f"Process with PID {pid} does not exist.")
        # Remove stale task file
        temp_json_path = os.path.join(config["base_dir"], "current_task.json")
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)
    except OSError as e:
        logger.error(f"Failed to terminate process with PID {pid}: {e}")
        raise click.Abort()
