import os
import subprocess
import tempfile

import typer
from rich import print as rich_print

from altbuilder.config import load_config
from altbuilder.utils import init_logger, logger

app = typer.Typer(
    name="update-submodules",
    help="Update submodules from upstream repository for a specified tag.",
)


def remove_nested_git_files(path: str) -> None:
    """Remove .git files copied from submodule worktrees."""
    for dirpath, dirnames, filenames in os.walk(path):
        if ".git" in filenames:
            os.remove(os.path.join(dirpath, ".git"))
        if ".git" in dirnames:
            subprocess.run(["rm", "-rf", os.path.join(dirpath, ".git")], check=True)
            dirnames.remove(".git")


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
        rich_print(f"[red]There is no such git object: {tag}[/red]")
        raise typer.Exit(code=1)

    # Check for uncommitted changes
    if (
        subprocess.call(["git", "diff", "--quiet"]) != 0
        or subprocess.call(["git", "diff", "--cached", "--quiet"]) != 0
    ):
        logger.error("There are uncommitted changes, exiting")
        rich_print("[red]There are uncommitted changes, exiting[/red]")
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
        rich_print("[red]Please set 'upstream' repo url[/red]")
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
        rich_print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    # Switch/create alt_submodules branch
    try:
        subprocess.run(
            ["git", "switch", "-q", "alt_submodules"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["git", "switch", "-q", "--orphan", "alt_submodules"], check=True
        )
        subprocess.run(
            ["git", "rm", "-rf", "--quiet", "--ignore-unmatch", "."], check=True
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
        remove_nested_git_files(modules_dir)

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
        rich_print("[yellow]Submodules were not changed[/yellow]")

    # Switch back & merge alt_submodules branch
    if current_branch:
        subprocess.run(["git", "switch", "--quiet", current_branch], check=True)
    else:
        logger.warning("Current branch is detached HEAD, skipping switch back.")
        rich_print(
            "[yellow]Warning: Current branch is detached HEAD, skipping switch back.[/yellow]"
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
    rich_print("[yellow]\n******** How to apply ********[/yellow]")
    typer.echo(
        "Add 'tar: alt_submodules:modules name=modules base=.' to your gear rules"
    )
    typer.echo("Add 'SourceX: modules.tar' and '%setup -aX' to your RPM specfile")
    rich_print("[yellow]\n******** REMINDER ********[/yellow]")
    typer.echo("Don't forget to update tags, e.g. by running `gear-store-tags -ac`")
    logger.info("Submodules update completed successfully")
    rich_print("[green]Submodules updated successfully.[/green]")


if __name__ == "__main__":
    app()
