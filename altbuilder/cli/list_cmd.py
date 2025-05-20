import os
import glob
import json
import subprocess
import click
import shutil
from ..config import load_config
from ..utils.logger import logger
from ..utils.helpers import colorize


def read_sandbox_info(sandbox_path):
    info_path = os.path.join(sandbox_path, "hasher", "sandbox_info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path) as f:
                info = json.load(f)
            return info
        except Exception:
            return {}
    return {}


def open_with_file_manager(path, file_manager=None):
    # Use MC, ranger, or default to MC if not specified and available
    cmd = []
    if not file_manager:
        file_manager = os.environ.get("ALTBUILDER_FILE_MANAGER")
        if not shutil.which(file_manager):
            file_manager = shutil.which("mc")
    if not file_manager:
        # Try to auto-detect
        if shutil.which("mc"):
            file_manager = "mc"
        else:
            file_manager = None

    if not file_manager:
        click.echo(
            colorize("No file manager (mc or ranger) found in PATH.", color="red")
        )
        return

    cmd = [file_manager, path]
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        click.echo(
            colorize(f"Failed to open {path} with {file_manager}: {e}", color="red")
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
    import shutil

    config = load_config()
    logger.info("Listing all existing sandboxes")
    environment_dir = config["environment_dir"]
    altbuilder_dir = os.path.join(environment_dir, ".sandboxes")
    if not os.path.exists(altbuilder_dir):
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    sandboxes = [
        d
        for d in os.listdir(altbuilder_dir)
        if os.path.isdir(os.path.join(altbuilder_dir, d))
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
        sandbox_path = os.path.join(altbuilder_dir, sandbox_name)
        info = read_sandbox_info(sandbox_path)
        branch = info.get("branch", colorize("<unknown>", color="red"))
        arch = info.get("arch", colorize("<unknown>", color="red"))
        click.echo(
            f"{colorize(sandbox_name, color='cyan', bold=True)}"
            f" [{colorize(branch, color='magenta')}-{colorize(arch, color='blue')}]"
            f" -> {colorize(sandbox_path, color='green')}"
        )
        # If -s/--sandbox, show additional info
        if sandbox and sandbox_name == sandbox:
            # Show SRPMS
            srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
            if os.path.exists(srpms_dir):
                click.echo(colorize("  Source RPMs:", color="yellow", bold=True))
                for srpm in glob.glob(os.path.join(srpms_dir, "*.rpm")):
                    click.echo(
                        f"  {colorize(os.path.basename(srpm), color='yellow')} -> {srpm}"
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
                        f"  {colorize(os.path.basename(rpm), color='green')} -> {rpm}"
                    )

    logger.info(f"Found {len(sandboxes)} sandboxes")
    logger.debug(f"Sandboxes: {', '.join(sandboxes)}")

    # Open sandbox directory (or all sandboxes dir) in file manager
    if open:
        if sandbox:
            open_with_file_manager(os.path.join(altbuilder_dir, sandbox), file_manager)
        else:
            open_with_file_manager(altbuilder_dir, file_manager)
