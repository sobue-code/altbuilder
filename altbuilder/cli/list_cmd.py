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
    config = load_config()
    logger.info("Listing all existing sandboxes")
    console = Console()
    environment_dir = config["environment_dir"]

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    if not os.path.exists(environment_dir):
        message = "No sandboxes found."
        logger.info(message)
        if json_mode:
            json_response(ctx, "success", message=message, sandboxes=[])
            return
        console.print("[yellow]No sandboxes found.[/yellow]")
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
                json_response(ctx, "error", message=message, code=1)
            else:
                console.print(f"[red]{message}[/red]")
                raise typer.Exit(code=1)
            return
        sandboxes = [sandbox]

    if not sandboxes:
        message = "No sandboxes found."
        logger.info(message)
        if json_mode:
            json_response(ctx, "success", message=message, sandboxes=[])
            return
        console.print("[yellow]No sandboxes found.[/yellow]")
        return

    # Collect sandbox data
    sandboxes_data = []

    for sandbox_name in sorted(sandboxes):
        sandbox_path = os.path.join(environment_dir, sandbox_name)
        info = read_sandbox_info(sandbox_path)
        branch_value = info.get("branch")
        arch_value = info.get("arch")
        task_id = info.get("task_id")

        sandbox_info = {
            "name": sandbox_name,
            "branch": branch_value or "<unknown>",
            "arch": arch_value or "<unknown>",
            "task_id": task_id if task_id not in (None, "<unknown>") else None,
        }

        # If specific sandbox is requested, include RPM details
        if sandbox and sandbox_name == sandbox:
            srpms = []
            srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
            if os.path.exists(srpms_dir):
                srpms = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(srpms_dir, "*.rpm")))]

            arch_rpms = {}
            arch_dirs = sorted(
                glob.glob(
                    os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")
                )
            )
            for arch_dir in arch_dirs:
                arch_name = os.path.basename(os.path.dirname(arch_dir))
                rpms = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(arch_dir, "*.rpm")))]
                arch_rpms[arch_name] = rpms

            sandbox_info["srpms"] = srpms
            sandbox_info["rpms"] = arch_rpms

        sandboxes_data.append(sandbox_info)

    # JSON mode output
    if json_mode:
        json_response(
            ctx,
            "success",
            message=f"Found {len(sandboxes_data)} sandbox(es).",
            sandboxes=sandboxes_data,
            count=len(sandboxes_data),
        )
        return

    # Create tree for sandboxes (non-JSON mode)
    sandbox_tree = Tree(f"[bold blue]Sandboxes[/] ([cyan]{len(sandboxes)} found[/])")

    for sandbox_info in sandboxes_data:
        sandbox_name = sandbox_info["name"]
        branch_value = sandbox_info["branch"]
        arch_value = sandbox_info["arch"]
        task_id = sandbox_info["task_id"]

        sandbox_label = Text()
        sandbox_label.append("📍 ", style="cyan")
        sandbox_label.append(sandbox_name, style="cyan")
        sandbox_label.append(" [", style="cyan")

        if branch_value != "<unknown>":
            sandbox_label.append(str(branch_value), style="cyan")
        else:
            sandbox_label.append("<unknown>", style="red")

        sandbox_label.append("-", style="cyan")

        if arch_value != "<unknown>":
            sandbox_label.append(str(arch_value), style="cyan")
        else:
            sandbox_label.append("<unknown>", style="red")

        if task_id is not None:
            sandbox_label.append(", ", style="cyan")
            sandbox_label.append(str(task_id), style="cyan")

        sandbox_label.append("]", style="cyan")
        sandbox_node = sandbox_tree.add(sandbox_label)

        # If --sandbox is specified, show RPM details
        if sandbox and sandbox_name == sandbox_info["name"]:
            if "srpms" in sandbox_info and sandbox_info["srpms"]:
                sandbox_path = os.path.join(environment_dir, sandbox_name)
                srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
                srpm_node = sandbox_node.add(
                    Text(f"📦 Source RPMs [{srpms_dir}]", no_wrap=True)
                )
                for rpm_name in sandbox_info["srpms"]:
                    srpm_node.add(f"[yellow]{rpm_name}[/]")

            if "rpms" in sandbox_info:
                sandbox_path = os.path.join(environment_dir, sandbox_name)
                for arch_name, rpm_list in sandbox_info["rpms"].items():
                    arch_dir = os.path.join(sandbox_path, "hasher", "repo", arch_name, "RPMS.hasher")
                    arch_node = sandbox_node.add(
                        Text(f"📦 {arch_name} RPMs [{arch_dir}]", no_wrap=True)
                    )
                    for rpm_name in rpm_list:
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


if __name__ == "__main__":
    app()
