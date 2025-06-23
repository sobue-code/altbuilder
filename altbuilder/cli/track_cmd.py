import click
import json
import time
from rich.console import Console
from rich.live import Live
from rich.text import Text
from ..config import load_config
from ..utils.metrics import Metrics
from ..utils.logger import logger


@click.command("track")
@click.option(
    "--watch",
    is_flag=True,
    help="Continuously monitor the current task, updating every second.",
)
@click.help_option("--help", "-h")
def track_cmd(watch):
    """Display information about the current task."""
    config = load_config()
    console = Console()

    # Initialize Metrics with base directory
    metrics = Metrics(base_dir=config["base_dir"])  # Adjust key if needed

    if not watch:
        # Default behavior: display task info once
        task = metrics.get_current_task()
        if not task:
            logger.info("No tasks are currently running.")
            click.echo("No tasks are currently running.")
            return

        logger.info("Current task details:")
        click.echo(json.dumps(task, indent=2, ensure_ascii=False))
        return

    # Watch mode: continuously monitor task with smooth updates
    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                task = metrics.get_current_task()
                if not task:
                    text = Text("No tasks are currently running.", style="bold red")
                else:
                    text = Text(json.dumps(task, indent=2, ensure_ascii=False), style="white")
                live.update(text)
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopped monitoring tasks.")
        console.print("\nStopped monitoring tasks.")
