import os
import click
import subprocess
import tempfile
from ..config import load_config
from ..utils import init_logger, logger, colorize


@click.command("update-submodules")
@click.argument("tag", required=True)
@click.help_option("--help", "-h")
def update_submodules(tag):
    """Update submodules from upstream repository for a specified tag."""
    config = load_config()
    init_logger("update-submodules", config.get("build_logs_dir", "/tmp/logs"), config)

    logger.info(f"Starting submodules update from upstream for tag: {tag}")

    # Check if tag exists
    try:
        subprocess.run(
            ["git", "show", tag],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        logger.error(f"There is no such git object: {tag}")
        click.echo(colorize(f"There is no such git object: {tag}", color="red"))
        raise click.Abort()

    # Check for uncommitted changes
    if (
        subprocess.call(["git", "diff", "--quiet"]) != 0
        or subprocess.call(["git", "diff", "--cached", "--quiet"]) != 0
    ):
        logger.error("There are uncommitted changes, exiting")
        click.echo(colorize("There are uncommitted changes, exiting", color="red"))
        raise click.Abort()

    # Get upstream URL
    try:
        upstream_url = (
            subprocess.check_output(["git", "remote", "get-url", "upstream"])
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        logger.error("Please set 'upstream' repo url")
        click.echo(colorize("Please set 'upstream' repo url", color="red"))
        raise click.Abort()

    logger.info(f"Using upstream URL: {upstream_url}")

    # Переход в корневую директорию
    root_dir = (
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode()
        .strip()
    )
    os.chdir(root_dir)

    # Текущая ветка
    current_branch = (
        subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
    )
    if current_branch == "alt_submodules":
        logger.error(
            "Already on branch: alt_submodules, please switch manually to target branch"
        )
        click.echo(
            colorize(
                "Already on branch: alt_submodules, please switch manually to target branch",
                color="red",
            )
        )
        raise click.Abort()

    # Switch to alt_submodules
    try:
        subprocess.run(["git", "switch", "-q", "alt_submodules"], check=True)
    except subprocess.CalledProcessError:
        subprocess.run(
            ["git", "switch", "-q", "--orphan", "alt_submodules"], check=True
        )

    # Dir cleanup
    modules_dir = os.path.join(root_dir, "modules")
    if os.path.exists(modules_dir):
        subprocess.run(["rm", "-rf", modules_dir], check=True)
    os.makedirs(modules_dir)

    # Clone upstream
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"Cloning upstream from {upstream_url} into temporary directory")
        subprocess.run(["git", "clone", "-q", upstream_url, temp_dir], check=True)
        os.chdir(temp_dir)
        subprocess.run(
            ["git", "switch", "--quiet", "-C", "_alt_submodules", tag], check=True
        )
        logger.info("Initializing and updating submodules")
        subprocess.run(
            ["git", "submodule", "--quiet", "update", "--init", "--recursive"],
            check=True,
        )

        # Copy submodules to modules directory
        subprocess.run(
            [
                "git",
                "submodule",
                "--quiet",
                "foreach",
                "--recursive",
                f"cd $toplevel && cp -a --parents -t {modules_dir} $displaypath",
            ],
            check=True,
        )

        # Get submodule status
        submodules_status = subprocess.check_output(
            ["git", "submodule", "status"]
        ).decode()

    os.chdir(root_dir)

    # Add modules
    subprocess.run(["git", "add", "-f", "modules"], check=True)

    # Check if there are any changes
    if subprocess.call(["git", "diff", "--quiet", "--cached", "--", "modules"]) != 0:
        logger.info("Committing updated submodules")
        commit_msg = (
            f"Update submodules from {upstream_url} for {tag}\n\n"
            f"Submodules:\n{submodules_status}\n"
            f"Updated with `update-submodules {tag}`"
        )
        subprocess.run(["git", "commit", "--quiet", "-m", commit_msg], check=True)
    else:
        logger.info("Submodules were not changed")
        click.echo("Submodules were not changed")

    # Switch back to the original branch
    subprocess.run(["git", "switch", "--quiet", current_branch], check=True)
    subprocess.run(
        [
            "git",
            "merge",
            "--quiet",
            "-s",
            "ours",
            "alt_submodules",
            "--allow-unrelated-histories",
            "--no-edit",
        ],
        check=True,
    )
    if os.path.exists(modules_dir):
        subprocess.run(["rm", "-rf", modules_dir], check=True)

    # Users instructions
    click.echo(colorize("\n******** How to apply ********", color="yellow"))
    click.echo(
        "Add 'tar: alt_submodules:modules name=modules base=.' to your gear rules"
    )
    click.echo("Add 'SourceX: modules.tar' and '%setup -aX' to your RPM specfile")
    click.echo(colorize("\n******** REMINDER ********", color="yellow"))
    click.echo("Don't forget to update tags, e.g. by running `gear-store-tags -ac`")
    logger.info("Submodules update completed successfully")
    click.echo(colorize("Submodules updated successfully.", color="green"))
