import os
import subprocess
import tempfile

import typer

from altbuilder.config import load_config
from altbuilder.utils import colorize, init_logger, logger

app = typer.Typer(
    name="update-submodules",
    help="Update submodules from upstream repository for a specified tag.",
)


@app.command()
def update_submodules(
    tag: str = typer.Argument(..., help="Git tag to use for updating submodules")
):
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
        typer.echo(colorize(f"There is no such git object: {tag}", color="red"))
        raise typer.Exit(code=1)

    # Check for uncommitted changes
    if (
        subprocess.call(["git", "diff", "--quiet"]) != 0
        or subprocess.call(["git", "diff", "--cached", "--quiet"]) != 0
    ):
        logger.error("There are uncommitted changes, exiting")
        typer.echo(colorize("There are uncommitted changes, exiting", color="red"))
        raise typer.Exit(code=1)

    # Get upstream URL
    try:
        upstream_url = (
            subprocess.check_output(["git", "remote", "get-url", "upstream"])
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        logger.error("Please set 'upstream' repo url")
        typer.echo(colorize("Please set 'upstream' repo url", color="red"))
        raise typer.Exit(code=1)

    logger.info(f"Using upstream URL: {upstream_url}")

    # Root dir
    root_dir = (
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode()
        .strip()
    )
    os.chdir(root_dir)

    # Current branch
    current_branch = (
        subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
    )
    if current_branch == "alt_submodules":
        msg = (
            "Already on branch: alt_submodules, please switch manually to target branch"
        )
        logger.error(msg)
        typer.echo(colorize(msg, color="red"))
        raise typer.Exit(code=1)

    # Switch/create alt_submodules branch
    try:
        subprocess.run(["git", "switch", "-q", "alt_submodules"], check=True)
    except subprocess.CalledProcessError:
        subprocess.run(
            ["git", "switch", "-q", "--orphan", "alt_submodules"], check=True
        )

    # Cleanup modules dir
    modules_dir = os.path.join(root_dir, "modules")
    if os.path.exists(modules_dir):
        subprocess.run(["rm", "-rf", modules_dir], check=True)
    os.makedirs(modules_dir)

    # Clone upstream + update submodules
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"Cloning upstream from {upstream_url} into tmp dir")
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

        # Copy submodules into modules/
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

        # Save submodule status
        submodules_status = subprocess.check_output(
            ["git", "submodule", "status"]
        ).decode()

    os.chdir(root_dir)

    # Stage modules
    subprocess.run(["git", "add", "-f", "modules"], check=True)

    # Commit only if there are changes
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", "modules"], capture_output=True
    )

    if diff_result.returncode != 0:
        logger.info("Committing updated submodules")
        commit_msg = (
            f"Update submodules from {upstream_url} for {tag}\n\n"
            f"Submodules:\n{submodules_status}\n"
            f"Updated with `update-submodules {tag}`"
        )
        subprocess.run(["git", "commit", "--quiet", "-m", commit_msg], check=True)
    else:
        logger.info("Submodules were not changed")
        typer.echo(colorize("Submodules were not changed", color="yellow"))

    # Switch back & merge alt_submodules branch
    if current_branch:
        subprocess.run(["git", "switch", "--quiet", current_branch], check=True)
    else:
        logger.warning("Current branch is detached HEAD, skipping switch back.")
        typer.echo(
            colorize(
                "Warning: Current branch is detached HEAD, skipping switch back.",
                color="yellow",
            )
        )

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

    # Instructions
    typer.echo(colorize("\n******** How to apply ********", color="yellow"))
    typer.echo(
        "Add 'tar: alt_submodules:modules name=modules base=.' to your gear rules"
    )
    typer.echo("Add 'SourceX: modules.tar' and '%setup -aX' to your RPM specfile")
    typer.echo(colorize("\n******** REMINDER ********", color="yellow"))
    typer.echo("Don't forget to update tags, e.g. by running `gear-store-tags -ac`")
    logger.info("Submodules update completed successfully")
    typer.echo(colorize("Submodules updated successfully.", color="green"))


if __name__ == "__main__":
    app()
