import click
import os
import json
import shutil
from datetime import datetime
from rich.console import Console
from rich.table import Table
from ..config import load_config
from ..utils import init_logger, colorize, open_with_file_manager, logger


def collect_build_logs(log_dir, sandbox=None, package=None):
    """Collect build logs from build_result.json files."""
    builds = []
    for root, dirs, files in os.walk(log_dir):
        if "build_result.json" in files:
            # Extract sandbox and package from path
            path_parts = root.split(os.sep)
            sandbox_name = path_parts[-3] if len(path_parts) >= 3 else "unknown"
            package_name = path_parts[-2] if len(path_parts) >= 2 else None
            build_dir = path_parts[-1]

            # Apply filters
            if sandbox and sandbox_name != sandbox:
                continue
            if package and package_name != package:
                continue

            with open(os.path.join(root, "build_result.json"), "r") as f:
                try:
                    build_info = json.load(f)
                    builds.append({
                        "sandbox": sandbox_name,
                        "package": build_info.get("package", package_name),
                        "start_time": build_info.get("start_time", "N/A"),
                        "end_time": build_info.get("end_time", "N/A"),
                        "duration": build_info.get("duration", 0.0),
                        "success": build_info.get("success", False),
                        "command": build_info.get("command", "N/A"),
                        "build_dir": build_dir,
                        "log_path": root
                    })
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {os.path.join(root, 'build_result.json')}")
    # Sort by package name (alphabetically) and then by start_time (descending)
    return sorted(builds, key=lambda x: (x["package"] or "", -(datetime.fromisoformat(x["start_time"]).timestamp() if x["start_time"] != "N/A" else 0)))


def format_build_logs(builds):
    """Format build logs into a rich Table with colored Status."""
    table = Table(title="Build Logs", show_header=True, header_style="bold magenta")
    table.add_column("Sandbox", style="cyan")
    table.add_column("Package", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("CMD", style="white")
    table.add_column("Duration (s)", style="white")
    table.add_column("Start Time", style="white")
    table.add_column("End Time", style="white")
    table.add_column("Build Directory", style="white")

    for build in builds:
        status = "Success" if build["success"] else "Failed"
        status_style = "green" if build["success"] else "red"
        table.add_row(
            build["sandbox"],
            build["package"] or "N/A",
            f"[{status_style}]{status}[/{status_style}]",
            build["command"],
            f"{build['duration']:.2f}",
            build["start_time"],
            build["end_time"],
            build["build_dir"]
        )
    return table


@click.command("logs")
@click.option(
    "--sandbox", "-s", help="Filter logs by sandbox name."
)
@click.option(
    "--package", "-p", help="Filter logs by package name."
)
@click.option(
    "--json-output", is_flag=True, help="Output logs in JSON format instead of a table."
)
@click.option(
    "-f", is_flag=True, help="Open log directory in file manager."
)
@click.option(
    "--file-manager", default=None, type=str, help="Specify file manager (e.g., mc or ranger) to use with -f. If omitted, uses default file manager."
)
@click.option(
    "--clean",
    is_flag=True,
    help="Remove logs for the specified sandbox or all logs if no sandbox is specified."
)
@click.help_option("--help", "-h")
def logs_cmd(sandbox, package, json_output, f, file_manager, clean):
    """Display or manage build logs for sandboxes and packages."""
    config = load_config()
    init_logger(config=config)
    console = Console()

    # Determine the log directory
    log_dir = config["build_logs_dir"]
    if sandbox:
        log_dir = os.path.join(log_dir, sandbox)

    # Handle --clean option
    if clean:
        if not os.path.exists(log_dir):
            click.echo(
                colorize(f"Log directory {log_dir} does not exist.", color="yellow")
            )
            logger.info(f"No logs found at {log_dir}")
            return
        try:
            shutil.rmtree(log_dir, ignore_errors=True)
            click.echo(
                colorize(f"Logs at {log_dir} removed successfully.", color="green")
            )
            logger.info(f"Removed logs at {log_dir}")
        except OSError as e:
            click.echo(colorize(f"Error removing logs at {log_dir}: {e}", color="red"))
            logger.error(f"Failed to remove logs at {log_dir}: {e}")
        return

    # Handle log viewing (default behavior)
    if not os.path.exists(log_dir):
        click.echo(colorize(f"Log directory {log_dir} does not exist.", color="red"))
        logger.info(f"No logs found at {log_dir}")
        return

    # If -f is used, open the log directory with specified or default file manager
    if f:
        open_with_file_manager(log_dir, file_manager)
        click.echo(
            colorize(f"Opened log directory {log_dir} in file manager.", color="green")
        )
        logger.info(f"Opened log directory {log_dir} in file manager")
        return

    # Collect and display build logs
    builds = collect_build_logs(config["build_logs_dir"], sandbox, package)
    if not builds:
        click.echo(colorize("No build logs found matching the criteria.", color="yellow"))
        logger.info("No build logs found.")
        return

    if json_output:
        click.echo(json.dumps(builds, indent=2, ensure_ascii=False))
    else:
        console.print(format_build_logs(builds))
