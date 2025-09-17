import json
import time

import typer
from rich.console import Console
from rich.live import Live
from rich.text import Text

from altbuilder.config import load_config
from altbuilder.utils.json_utils import is_json_mode, json_response
from altbuilder.utils.logger import logger
from altbuilder.utils.metrics import Metrics

app = typer.Typer(name="track", help="Display information about the current task.")


@app.command()
def track_cmd(
    ctx: typer.Context,
    watch: bool = typer.Option(
        False,
        "--watch",
        help="Continuously monitor the current task, updating every second.",
    ),
):
    """Display information about the current task."""
    json_mode = is_json_mode(ctx)
    params = {"watch": watch}
    config = load_config()
    console = Console()

    # Initialize Metrics with base directory
    metrics = Metrics(base_dir=config["base_dir"])  # Adjust key if needed

    if not watch:
        # Default behavior: display task info once
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
            return

        logger.info("Current task details:")
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                task=task,
            )
        else:
            typer.echo(json.dumps(task, indent=2, ensure_ascii=False))
        return

    # Watch mode: continuously monitor task with smooth updates
    if json_mode:
        json_response(
            ctx,
            "error",
            params=params,
            message="--watch is not supported with JSON output.",
            code=1,
        )
        return
    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                task = metrics.get_current_task()
                if not task:
                    text = Text("No tasks are currently running.", style="bold red")
                else:
                    text = Text(
                        json.dumps(task, indent=2, ensure_ascii=False), style="white"
                    )
                live.update(text)
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopped monitoring tasks.")
        console.print("\nStopped monitoring tasks.")


if __name__ == "__main__":
    app()
