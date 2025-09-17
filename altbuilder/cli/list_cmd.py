import glob
import os

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from altbuilder.config import load_config
from altbuilder.utils import logger, open_with_file_manager, read_sandbox_info
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="list",
    help="List all existing sandboxes with their metadata and optional RPM details.",
)


@app.command()
def list_cmd(
    ctx: typer.Context,
    sandbox: str = typer.Option(
        None, "--sandbox", "-s", help="Show details for the specified sandbox only."
    ),
    f: bool = typer.Option(
        False,
        "-f",
        help="Open sandbox directory (or all sandboxes dir) in file manager provided by "
        "ALTBUILDER_FILE_MANAGER env variable or default to mc.",
    ),
    file_manager: str = typer.Option(
        None, "--file-manager", help="Specify file manager (e.g., mc or ranger)."
    ),
):
    """List all existing sandboxes with their metadata and optional RPM details."""
    json_mode = is_json_mode(ctx)
    params = {"sandbox": sandbox, "open": f, "file_manager": file_manager}
    config = load_config()
    logger.info("Listing all existing sandboxes")
    console = Console()
    environment_dir = config["environment_dir"]

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    if not os.path.exists(environment_dir):
        message = "No sandboxes found."
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                sandboxes=[],
                environment_dir=environment_dir,
            )
        else:
            console.print("[yellow]No sandboxes found.[/yellow]")
        logger.info("No sandboxes found")
        return

    sandboxes = [
        d
        for d in os.listdir(environment_dir)
        if os.path.isdir(os.path.join(environment_dir, d))
    ]

    if sandbox:
        if sandbox not in sandboxes:
            message = f"Sandbox '{sandbox}' not found."
            logger.info(message)
            if json_mode:
                json_response(
                    ctx,
                    "error",
                    params=params,
                    message=message,
                    code=1,
                    sandboxes=[],
                    environment_dir=environment_dir,
                )
            else:
                console.print(f"[red]{message}[/red]")
            return
        sandboxes = [sandbox]

    if not sandboxes:
        message = "No sandboxes found."
        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                message=message,
                sandboxes=[],
                environment_dir=environment_dir,
            )
        else:
            console.print("[yellow]No sandboxes found.[/yellow]")
        logger.info("No sandboxes found")
        return

    # Create tree for sandboxes
    sandbox_tree = Tree(f"[bold blue]Sandboxes[/] ([cyan]{len(sandboxes)} found[/])")
    sandbox_data = []

    for sandbox_name in sorted(sandboxes):
        sandbox_path = os.path.join(environment_dir, sandbox_name)
        info = read_sandbox_info(sandbox_path)
        branch_value = info.get("branch")
        arch_value = info.get("arch")
        task_id = info.get("task_id")

        sandbox_entry = {
            "name": sandbox_name,
            "path": sandbox_path,
            "branch": branch_value,
            "arch": arch_value,
            "task_id": task_id,
        }

        sandbox_label = Text()
        sandbox_label.append("📍 ", style="cyan")
        sandbox_label.append(sandbox_name, style="cyan")
        sandbox_label.append(" [", style="cyan")

        if branch_value:
            sandbox_label.append(str(branch_value), style="cyan")
        else:
            sandbox_label.append("<unknown>", style="red")

        sandbox_label.append("-", style="cyan")

        if arch_value:
            sandbox_label.append(str(arch_value), style="cyan")
        else:
            sandbox_label.append("<unknown>", style="red")

        if task_id not in (None, "<unknown>"):
            sandbox_label.append(", ", style="cyan")
            sandbox_label.append(str(task_id), style="cyan")

        sandbox_label.append("]", style="cyan")
        sandbox_node = sandbox_tree.add(sandbox_label)

        # If --sandbox is specified, show RPM details
        if sandbox and sandbox_name == sandbox:
            srpms_list = []
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
                    srpms_list.append(rpm_name)

            # Binary RPMs by architecture
            rpm_map = {}
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
                rpm_entries = []
                for rpm in sorted(glob.glob(os.path.join(arch_dir, "*.rpm"))):
                    rpm_name = os.path.basename(rpm)
                    arch_node.add(f"[green]{rpm_name}[/]")
                    rpm_entries.append(rpm_name)
                if rpm_entries:
                    rpm_map[arch_name] = rpm_entries
            if srpms_list:
                sandbox_entry["srpms"] = srpms_list
            if rpm_map:
                sandbox_entry["rpms"] = rpm_map

        sandbox_data.append(sandbox_entry)

    # Print tree in a panel
    if not json_mode:
        console.print(Panel(sandbox_tree, title="Sandboxes", border_style="blue"))
        console.print(f"\n[bold]Total:[/] {len(sandboxes)} sandboxes")

    logger.info(f"Found {len(sandboxes)} sandboxes")
    logger.debug(f"Sandboxes: {', '.join(sandboxes)}")

    # Open sandbox directory in file manager if -f is specified
    opened_path = None
    if f:
        if sandbox:
            opened_path = os.path.join(environment_dir, sandbox)
        else:
            opened_path = environment_dir
        open_with_file_manager(opened_path, file_manager)

    if json_mode:
        extra = {
            "sandboxes": sandbox_data,
            "environment_dir": environment_dir,
            "total": len(sandbox_data),
        }
        if opened_path:
            extra["opened_path"] = opened_path
        json_response(
            ctx,
            "success",
            params=params,
            **extra,
        )
        return


if __name__ == "__main__":
    app()
