import os
import glob
import click
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.text import Text
from ..config import load_config
from ..utils import logger, colorize, read_sandbox_info, open_with_file_manager


@click.command("list")
@click.option("--sandbox", "-s", help="Show details for the specified sandbox only.")
@click.option(
    "-f",
    is_flag=True,
    help="Open sandbox directory (or all sandboxes dir) in file manager provided by "
    "ALTBUILDER_FILE_MANAGER env variable or default to mc.",
)
@click.option("--file-manager", help="Specify file manager (e.g., mc or ranger).")
@click.help_option("--help", "-h")
def list_cmd(sandbox, f, file_manager):
    """List all existing sandboxes with their metadata and optional RPM details."""
    config = load_config()
    logger.info("Listing all existing sandboxes")
    console = Console()
    environment_dir = config["environment_dir"]

    if not os.path.exists(environment_dir):
        console.print(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    sandboxes = [
        d
        for d in os.listdir(environment_dir)
        if os.path.isdir(os.path.join(environment_dir, d))
    ]

    if sandbox:
        if sandbox not in sandboxes:
            console.print(colorize(f"Sandbox '{sandbox}' not found.", color="red"))
            logger.info(f"Sandbox '{sandbox}' not found")
            return
        sandboxes = [sandbox]

    if not sandboxes:
        console.print(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    # Create tree for sandboxes
    sandbox_tree = Tree(f"[bold blue]Sandboxes[/] ([cyan]{len(sandboxes)} found[/])")

    for sandbox_name in sorted(sandboxes):
        sandbox_path = os.path.join(environment_dir, sandbox_name)
        info = read_sandbox_info(sandbox_path)
        branch = info.get("branch", colorize("<unknown>", color="red"))
        arch = info.get("arch", colorize("<unknown>", color="red"))
        task_id = info.get("task_id", None)

        # Handle task_id safely
        task_id_str = f", {task_id}" if task_id and task_id != "<unknown>" else ""
        sandbox_label = f"[cyan]📍 {sandbox_name}[/] " f"[{branch}-{arch}{task_id_str}]"
        sandbox_node = sandbox_tree.add(sandbox_label)

        # If --sandbox is specified, show RPM details
        if sandbox and sandbox_name == sandbox:
            # Source RPMs
            srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
            if os.path.exists(srpms_dir):
                # Render path as plain text to avoid markup errors
                srpm_node = sandbox_node.add(
                    Text(f"📦 Source RPMs [{srpms_dir}]", no_wrap=True)
                )
                for srpm in sorted(glob.glob(os.path.join(srpms_dir, "*.rpm"))):
                    rpm_name = os.path.basename(srpm)
                    srpm_node.add(f"[yellow]{rpm_name}[/]")

            # Binary RPMs by architecture
            arch_dirs = sorted(
                glob.glob(
                    os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")
                )
            )
            for arch_dir in arch_dirs:
                arch_name = os.path.basename(os.path.dirname(arch_dir))
                # Render path as plain text to avoid markup errors
                arch_node = sandbox_node.add(
                    Text(f"📦 {arch_name} RPMs [{arch_dir}]", no_wrap=True)
                )
                for rpm in sorted(glob.glob(os.path.join(arch_dir, "*.rpm"))):
                    rpm_name = os.path.basename(rpm)
                    arch_node.add(f"[green]{rpm_name}[/]")

    # Print tree in a panel
    console.print(Panel(sandbox_tree, title="Sandboxes", border_style="blue"))
    console.print(f"\n[bold]Total:[/] {len(sandboxes)} sandboxes")

    logger.info(f"Found {len(sandboxes)} sandboxes")
    logger.debug(f"Sandboxes: {', '.join(sandboxes)}")

    # Open sandbox directory in file manager if -f is specified
    if f:
        if sandbox:
            open_with_file_manager(os.path.join(environment_dir, sandbox), file_manager)
        else:
            open_with_file_manager(environment_dir, file_manager)
