import os
import subprocess
import typer

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import colorize, init_logger, logger

app = typer.Typer(name="copy-pyproject-deps", help="Copy pyproject_deps.json from sandbox to .gear/ directory.")


@app.command()
def copy_pyproject_deps(
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    force_commit: bool = typer.Option(
        False,
        "--force-commit",
        "-f",
        help="Force commit of pyproject_deps.json without confirmation prompt.",
    ),
):
    """Copy pyproject_deps.json from sandbox to .gear/ directory."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    if not env.exists():
        logger.warning(f"Sandbox {sandbox_name} does not exist, initializing...")
        env.init()

    logger.info(f"Copying pyproject_deps.json from sandbox {sandbox_name} to .gear/")
    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        'cat "$(rpm --eval %pyproject_deps_config)"',
    ]
    try:
        os.makedirs(".gear", exist_ok=True)
        with open(".gear/pyproject_deps.json", "w") as f:
            subprocess.run(cmd, stdout=f, check=True)

        # Check if pyproject_deps.json is already tracked in git
        pyproject_tracked = False
        try:
            subprocess.run(
                ["git", "ls-files", ".gear/pyproject_deps.json"],
                capture_output=True,
                check=True,
                text=True,
            )
            pyproject_tracked = True
        except subprocess.CalledProcessError:
            pyproject_tracked = False

        # Stage the pyproject_deps.json file
        subprocess.run(["git", "add", ".gear/pyproject_deps.json"], check=True)

        # Check if there are changes to commit
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", ".gear/pyproject_deps.json"],
            capture_output=True,
            text=True,
            check=True,
        )
        has_changes = bool(status_proc.stdout.strip())

        # Commit logic: prompt for confirmation unless force_commit is True
        commit_message = "Update pyproject_deps.json" if pyproject_tracked else "Add pyproject_deps.json"
        if has_changes:
            if force_commit:
                subprocess.run(["git", "commit", "-m", commit_message], check=True)
                logger.info(
                    f"pyproject_deps.json {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}"
                )
                typer.echo(
                    colorize(
                        f"pyproject_deps.json {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}",
                        color="green",
                    )
                )
            elif typer.confirm(
                f"Commit changes to pyproject_deps.json with message '{commit_message}'?",
                default=True,
            ):
                subprocess.run(["git", "commit", "-m", commit_message], check=True)
                logger.info(
                    f"pyproject_deps.json {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}"
                )
                typer.echo(
                    colorize(
                        f"pyproject_deps.json {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}",
                        color="green",
                    )
                )
            else:
                logger.info(
                    f"""pyproject_deps.json added to git index but not committed in sandbox {sandbox_name}.
                    Don't forget to add this line to your .gear/rules file:

                    copy: .gear/pyproject_deps.json

                    And this to your .spec:

                    SourceX: %pyproject_deps_config_name
                    """
                )
                typer.echo(
                    colorize(
                        f"""pyproject_deps.json added to git index but not committed in sandbox {sandbox_name}.
                        Don't forget to add this line to your .gear/rules file:

                        copy: .gear/pyproject_deps.json

                        And this to your .spec:

                        SourceX: %pyproject_deps_config_name
                        """,
                        color="yellow",
                    )
                )
        else:
            logger.info(f"pyproject_deps.json is unchanged in sandbox {sandbox_name}, no commit needed")
            typer.echo(
                colorize(
                    f"pyproject_deps.json is unchanged in sandbox {sandbox_name}, no commit needed",
                    color="yellow",
                )
            )

        typer.echo(colorize(f"pyproject_deps.json copied to .gear/", color="green"))
        logger.info(f"pyproject_deps.json copied to .gear/ in sandbox {sandbox_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy or stage pyproject_deps.json: {e}")
        typer.echo(
            colorize(f"Failed to copy or stage pyproject_deps.json: {e}", color="red")
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
