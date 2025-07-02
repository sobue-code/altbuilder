import click
import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict
from rich.console import Console
from rich.tree import Tree
from rich.text import Text
from rich.panel import Panel
from ..config import load_config
from ..utils import init_logger, colorize, open_with_file_manager, logger


def collect_build_logs(
    log_dir: str, sandbox: str = None, package: str = None
) -> List[Dict[str, Any]]:
    """Collect and group build logs from build_result.json files."""
    builds = []
    for root, _, files in os.walk(log_dir):
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
                    builds.append(
                        {
                            "sandbox": sandbox_name,
                            "package": build_info.get("package", package_name),
                            "version": build_info.get("version", "unknown"),
                            "release": build_info.get("release", "unknown"),
                            "start_time": build_info.get("start_time", "N/A"),
                            "duration": build_info.get("duration", 0.0),
                            "success": build_info.get("success", False),
                            "command": build_info.get("command", "N/A"),
                            "build_dir": build_dir,
                            "log_path": root,
                        }
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON in {os.path.join(root, 'build_result.json')}"
                    )

    def sort_key(build):
        start_time = build["start_time"]
        timestamp = (
            datetime.fromisoformat(start_time).timestamp()
            if start_time != "N/A"
            else float("-inf")
        )
        return (build["sandbox"] or "", build["package"] or "", -timestamp)

    return sorted(builds, key=sort_key)


def format_build_logs(
    builds: List[Dict[str, Any]], expand_history: bool = False
) -> None:
    """Format and print build logs as a compact tree, optionally expanding build history."""
    console = Console()
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    # Group builds by sandbox, package, and version-release
    for build in builds:
        sandbox = build["sandbox"]
        package = build["package"] or "N/A"
        version_release = (build["version"], build["release"])
        grouped[sandbox][package][version_release].append(build)

    total_builds = 0
    total_success = 0
    total_failed = 0

    for sandbox in sorted(grouped.keys()):
        sandbox_builds = grouped[sandbox]
        sandbox_stats = {"builds": 0, "success": 0, "failed": 0}

        # Calculate sandbox statistics
        for package in sandbox_builds:
            for version_release in sandbox_builds[package]:
                for build in sandbox_builds[package][version_release]:
                    sandbox_stats["builds"] += 1
                    if build["success"]:
                        sandbox_stats["success"] += 1
                    else:
                        sandbox_stats["failed"] += 1

        total_builds += sandbox_stats["builds"]
        total_success += sandbox_stats["success"]
        total_failed += sandbox_stats["failed"]

        # Create tree for sandbox
        sandbox_tree = Tree(
            f"[bold blue]Sandbox: {sandbox}[/] "
            f"([green]{sandbox_stats['success']} success[/], "
            f"[red]{sandbox_stats['failed']} failed[/], "
            f"{sandbox_stats['builds']} builds)"
        )

        # Add packages to tree
        for package in sorted(sandbox_builds.keys()):
            package_node = sandbox_tree.add(f"[cyan]📦 {package}[/]")
            versions = sorted(
                sandbox_builds[package].keys(),
                key=lambda vr: (
                    datetime.fromisoformat(
                        sandbox_builds[package][vr][0]["start_time"]
                    ).timestamp()
                    if sandbox_builds[package][vr][0]["start_time"] != "N/A"
                    else float("-inf")
                ),
                reverse=True,
            )

            for version, release in versions:
                builds_list = sandbox_builds[package][(version, release)]
                latest_build = builds_list[0]  # Latest build
                success_count = sum(1 for b in builds_list if b["success"])
                failed_count = len(builds_list) - success_count

                # Format time
                start_time = latest_build["start_time"]
                if start_time != "N/A":
                    start_time = datetime.fromisoformat(start_time).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                # Latest build status
                status_text = (
                    "[green]Success[/]" if latest_build["success"] else "[red]Failed[/]"
                )
                version_label = (
                    f"[yellow]{version}-{release}[/] "
                    f"({len(builds_list)} builds: {status_text}, "
                    f"{latest_build['duration']:.2f}s, {start_time})"
                )
                version_node = package_node.add(version_label)

                # Expand history if requested
                if expand_history and len(builds_list) > 0:
                    for build in builds_list:
                        build_time = build["start_time"]
                        if build_time != "N/A":
                            build_time = datetime.fromisoformat(build_time).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        build_status = (
                            "[green]Success[/]"
                            if build["success"]
                            else "[red]Failed[/]"
                        )
                        build_label = (
                            f"Build: {build_status}, {build['duration']:.2f}s, "
                            f"{build_time}, {build['build_dir']}"
                        )
                        version_node.add(build_label)

                # Add history summary
                if len(builds_list) > 1:
                    history_text = Text(
                        f"↳ History: {success_count} success, {failed_count} failed",
                        style="dim",
                    )
                    version_node.add(history_text)

        # Print tree in a panel
        console.print(
            Panel(sandbox_tree, title=f"Sandbox: {sandbox}", border_style="blue")
        )

    # Print total statistics
    console.print(
        f"\n[bold]Total:[/] {total_builds} builds, "
        f"[green]{total_success} success[/], [red]{total_failed} failed[/]"
    )


@click.command("logs")
@click.option("--sandbox", "-s", help="Filter logs by sandbox name.")
@click.option("--package", "-p", help="Filter logs by package name.")
@click.option(
    "--json-output",
    "-j",
    is_flag=True,
    help="Output logs in JSON format instead of tree.",
)
@click.option("--limit", type=int, help="Limit number of builds.")
@click.option("-f", is_flag=True, help="Open log directory in file manager.")
@click.option(
    "--file-manager",
    default=None,
    type=str,
    help="Specify file manager (e.g., mc or ranger) to use with -f.",
)
@click.option(
    "--clean",
    is_flag=True,
    help="Remove logs for the specified sandbox or all logs if no sandbox is specified.",
)
@click.option(
    "--expand-history",
    "-e",
    is_flag=True,
    help="Expand build history to show all attempts.",
)
@click.help_option("--help", "-h")
def logs_cmd(
    sandbox, package, json_output, limit, f, file_manager, clean, expand_history
):
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
        if click.confirm(
            colorize(f"Are you sure you want to remove logs at {log_dir}?", color="red")
        ):
            try:
                shutil.rmtree(log_dir, ignore_errors=True)
                click.echo(
                    colorize(f"Logs at {log_dir} removed successfully.", color="green")
                )
                logger.info(f"Removed logs at {log_dir}")
            except OSError as e:
                click.echo(
                    colorize(f"Error removing logs at {log_dir}: {e}", color="red")
                )
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
        click.echo(
            colorize("No build logs found matching the criteria.", color="yellow")
        )
        logger.info("No build logs found.")
        return

    if json_output:
        if limit:
            limited_builds = builds[:limit]
            click.echo(json.dumps(limited_builds, indent=2, ensure_ascii=False))
        else:
            click.echo(json.dumps(builds, indent=2, ensure_ascii=False))
    else:
        if limit:
            builds = builds[:limit]
        format_build_logs(builds, expand_history)
