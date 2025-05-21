import os
import glob
import click
from ..config import load_config
from ..utils import (
    logger,
    colorize,
    read_sandbox_info,
    open_with_file_manager,
)


@click.command("list")
@click.option("--sandbox", "-s", help="Show details for the specified sandbox only.")
@click.option(
    "--open",
    "-o",
    is_flag=True,
    help="""Open sandbox directory (or all sandboxes dir) in file manager provided by 
    ALTBUILDER_FILE_MANAGER env variable or default to mc.""",
)
@click.option("--file-manager", "-fm", help="Specify file manager (e.g. mc or ranger).")
@click.help_option("--help", "-h")
def list_cmd(sandbox, open, file_manager):
    """List all existing sandboxes."""
    config = load_config()
    logger.info("Listing all existing sandboxes")
    environment_dir = config["environment_dir"]
    if not os.path.exists(environment_dir):
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    sandboxes = [
        d
        for d in os.listdir(environment_dir)
        if os.path.isdir(os.path.join(environment_dir, d))
    ]

    if sandbox:
        # Only show the specified sandbox (or error)
        if sandbox not in sandboxes:
            click.echo(colorize(f"Sandbox '{sandbox}' not found.", color="red"))
            logger.info(f"Sandbox '{sandbox}' not found")
            return
        sandboxes = [sandbox]

    if not sandboxes:
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    for sandbox_name in sandboxes:
        sandbox_path = os.path.join(environment_dir, sandbox_name)
        info = read_sandbox_info(sandbox_path)
        branch = info.get("branch", colorize("<unknown>", color="red"))
        arch = info.get("arch", colorize("<unknown>", color="red"))
        task_id = info.get("task_id", colorize("<unknown>", color="red"))
        click.echo(
            f"{colorize(sandbox_name, color='cyan', bold=True)}"
            f"\t [{branch}-{arch}"
            f" {task_id or '\b'}]"
            f"\n\t {colorize(sandbox_path, color='green')}"
        )
        # If -s/--sandbox, show additional info
        if sandbox and sandbox_name == sandbox:
            # Show SRPMS
            srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
            if os.path.exists(srpms_dir):
                click.echo(colorize("  Source RPMs:", color="yellow", bold=True))
                for srpm in glob.glob(os.path.join(srpms_dir, "*.rpm")):
                    click.echo(
                        f"  {colorize(os.path.basename(srpm), color='yellow')} \n\t {srpm}"
                    )

            # Show binary RPMs for each architecture
            arch_dirs = glob.glob(
                os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")
            )
            for arch_dir in arch_dirs:
                arch_name = os.path.basename(os.path.dirname(arch_dir))
                click.echo(colorize(f"  {arch_name} RPMs:", color="green", bold=True))
                for rpm in glob.glob(os.path.join(arch_dir, "*.rpm")):
                    click.echo(
                        f"  {colorize(os.path.basename(rpm), color='green')} \n\t {rpm}"
                    )

    logger.info(f"Found {len(sandboxes)} sandboxes")
    logger.debug(f"Sandboxes: {', '.join(sandboxes)}")

    # Open sandbox directory (or all sandboxes dir) in file manager
    if open:
        if sandbox:
            open_with_file_manager(os.path.join(environment_dir, sandbox), file_manager)
        else:
            open_with_file_manager(environment_dir, file_manager)
