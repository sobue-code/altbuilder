import difflib
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from altbuilder.config import load_config
from altbuilder.utils import colorize, init_logger, logger, open_with_file_manager

app = typer.Typer(
    name="logs",
    help="Display or manage build logs for sandboxes and packages.",
)


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


def get_spec_path(log_path, package):
    """Find the spec file in the log directory."""
    possible_specs = [
        f"{package}.spec",
        "package.spec",
    ]
    for spec_name in possible_specs:
        spec_path = os.path.join(log_path, spec_name)
        if os.path.exists(spec_path):
            return spec_path
    # Search for any .spec file if not found
    for file in os.listdir(log_path):
        if file.endswith(".spec"):
            return os.path.join(log_path, file)
    return None


def display_spec_diff(build1, build2):
    """Display colorized diff between two spec files using colorize."""
    spec1_path = get_spec_path(build1["log_path"], build1["package"])
    spec2_path = get_spec_path(build2["log_path"], build2["package"])

    if not spec1_path:
        typer.echo(
            colorize(f"No spec file found for build {build1['build_dir']}", color="red")
        )
        return
    if not spec2_path:
        typer.echo(
            colorize(f"No spec file found for build {build2['build_dir']}", color="red")
        )
        return

    with open(spec1_path, "r") as f1, open(spec2_path, "r") as f2:
        lines1 = f1.readlines()
        lines2 = f2.readlines()

    diff = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=f"{build1['build_dir']}/{os.path.basename(spec1_path)}",
        tofile=f"{build2['build_dir']}/{os.path.basename(spec2_path)}",
    )

    for line in diff:
        line = line.rstrip("\n")
        if line.startswith("---") or line.startswith("+++"):
            typer.echo(colorize(line, color="yellow"))
        elif line.startswith("@@"):
            typer.echo(colorize(line, color="cyan"))
        elif line.startswith("-"):
            typer.echo(colorize(line, color="red"))
        elif line.startswith("+"):
            typer.echo(colorize(line, color="green"))
        else:
            typer.echo(line)


def get_build_by_id(builds, id_str):
    """Get build by index (number) or directory name, preferring 'build_{id}' for numeric ids if exists."""
    try:
        idx = int(id_str)
        # First, check if there is a build with build_dir == f"build_{id_str}"
        for build in builds:
            if build["build_dir"] == f"build_{id_str}":
                return build
        # If not, use as index
        if 1 <= idx <= len(builds):
            return builds[idx - 1]
        else:
            typer.echo(
                colorize(f"Index {idx} out of range (1-{len(builds)}).", color="red")
            )
            return None
    except ValueError:
        # Assume directory name
        for build in builds:
            if build["build_dir"] == id_str:
                return build
        typer.echo(colorize(f"Build directory '{id_str}' not found.", color="red"))
        return None


@app.command()
def logs_cmd(
    ctx: typer.Context,
    sandbox: str = typer.Option(
        None, "--sandbox", "-s", help="Filter logs by sandbox name."
    ),
    package: str = typer.Option(
        None, "--package", "-p", help="Filter logs by package name."
    ),
    json_output: bool = typer.Option(
        False, "--json-output", "-j", help="Output logs in JSON format instead of tree."
    ),
    limit: int = typer.Option(None, "--limit", help="Limit number of builds."),
    f: bool = typer.Option(False, "-f", help="Open log directory in file manager."),
    file_manager: str = typer.Option(
        None,
        "--file-manager",
        help="Specify file manager (e.g., mc or ranger) to use with -f.",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Remove logs for the specified sandbox or all logs if no sandbox is specified.",
    ),
    expand_history: bool = typer.Option(
        False,
        "--expand-history",
        "-e",
        help="Expand build history to show all attempts.",
    ),
    diff_spec: bool = typer.Option(
        False,
        "--diff-spec",
        "-d",
        help="Enable spec diff mode. Compares last two builds if no IDs provided, or the specified two builds (directories or indices). Requires --package.",
    ),
    diff_ids: List[str] = typer.Argument(
        None, help="Build IDs or indices to compare for --diff-spec."
    ),
):
    """Display or manage build logs for sandboxes and packages."""
    config = load_config()
    init_logger(config=config)
    console = Console()

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    # Determine the log directory
    log_dir = config["build_logs_dir"]
    if sandbox:
        log_dir = os.path.join(log_dir, sandbox)
    if package:
        log_dir = os.path.join(log_dir, package)

    # Handle --clean option
    if clean:
        if not os.path.exists(log_dir):
            typer.echo(
                colorize(f"Log directory {log_dir} does not exist.", color="yellow")
            )
            logger.info(f"No logs found at {log_dir}")
            return
        if typer.confirm(
            colorize(f"Are you sure you want to remove logs at {log_dir}?", color="red")
        ):
            try:
                shutil.rmtree(log_dir, ignore_errors=True)
                typer.echo(
                    colorize(f"Logs at {log_dir} removed successfully.", color="green")
                )
                logger.info(f"Removed logs at {log_dir}")
            except OSError as e:
                typer.echo(
                    colorize(f"Error removing logs at {log_dir}: {e}", color="red")
                )
                logger.error(f"Failed to remove logs at {log_dir}: {e}")
            return

    # Handle log viewing (default behavior)
    if not os.path.exists(log_dir):
        typer.echo(colorize(f"Log directory {log_dir} does not exist.", color="red"))
        logger.info(f"No logs found at {log_dir}")
        return

    # If -f is used, open the log directory with specified or default file manager
    if f:
        open_with_file_manager(log_dir, file_manager)
        typer.echo(
            colorize(f"Opened log directory {log_dir} in file manager.", color="green")
        )
        logger.info(f"Opened log directory {log_dir} in file manager")
        return

    # Collect and display build logs
    builds = collect_build_logs(config["build_logs_dir"], sandbox, package)
    if not builds:
        typer.echo(
            colorize("No build logs found matching the criteria.", color="yellow")
        )
        logger.info("No build logs found.")
        return

    if diff_spec:
        if not package:
            typer.echo(
                colorize(
                    "Error: --diff-spec requires --package to be specified.",
                    color="red",
                )
            )
            return

        # Check if diff_ids is provided and handle default case
        if diff_ids is None or len(diff_ids) == 0:
            # Default: compare last two builds
            if len(builds) < 2:
                typer.echo(
                    colorize(
                        "Error: At least two builds are required to compare spec files.",
                        color="red",
                    )
                )
                logger.info("Insufficient builds for spec diff.")
                return
            build1 = builds[1]  # Older (second latest)
            build2 = builds[0]  # Newer (latest)
        elif len(diff_ids) == 2:
            id1, id2 = diff_ids
            build1 = get_build_by_id(builds, id1)
            build2 = get_build_by_id(builds, id2)
            if not build1 or not build2:
                return
        else:
            typer.echo(
                colorize(
                    "Error: --diff-spec with IDs expects exactly two arguments.",
                    color="red",
                )
            )
            return

        typer.echo(
            colorize(
                f"Comparing spec files (older to newer): {build1['build_dir']} to {build2['build_dir']}",
                bold=True,
                color="cyan",
            )
        )
        display_spec_diff(build1, build2)
        return

    if json_output:
        if limit:
            limited_builds = builds[:limit]
            typer.echo(json.dumps(limited_builds, indent=2, ensure_ascii=False))
        else:
            typer.echo(json.dumps(builds, indent=2, ensure_ascii=False))
    else:
        if limit:
            builds = builds[:limit]
        format_build_logs(builds, expand_history)


if __name__ == "__main__":
    app()
