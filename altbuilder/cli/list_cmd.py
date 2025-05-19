import os
import glob
import click
from ..config import load_config
from ..utils.logger import logger
from ..utils.helpers import colorize


@click.command("list")
@click.option("--sandbox", "-s", help="Show details for the specified sandbox.")
@click.help_option("--help", "-h")
def list_cmd(sandbox):
    """List all existing sandboxes."""
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

    if not sandboxes:
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
    else:
        click.echo(colorize("Existing sandboxes:", bold=True))
        for sandbox_name in sandboxes:
            sandbox_path = os.path.join(altbuilder_dir, sandbox_name)

            # Show basic info for all sandboxes
            click.echo(
                f"{colorize(sandbox_name, color='cyan', bold=True)} -> {colorize(sandbox_path, color='green')}"
            )

            # If a specific sandbox is specified, show its repository contents
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
                    click.echo(
                        colorize(f"  {arch_name} RPMs:", color="green", bold=True)
                    )
                    for rpm in glob.glob(os.path.join(arch_dir, "*.rpm")):
                        click.echo(
                            f"  {colorize(os.path.basename(rpm), color='green')} -> {rpm}"
                        )

        logger.info(f"Found {len(sandboxes)} sandboxes")
        logger.debug(f"Sandboxes: {', '.join(sandboxes)}")
