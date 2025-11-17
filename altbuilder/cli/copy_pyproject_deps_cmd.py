import os
import subprocess
import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger

app = typer.Typer(name="copy-pyproject-deps", help="Copy pyproject_deps.json from sandbox to .gear/ directory.")


def _copy_deps_from_sandbox(env: Environment, output_path: str) -> bool:
    """
    Copy pyproject_deps.json from sandbox to specified path.

    Args:
        env: Environment object for the sandbox
        output_path: Path where to save the file

    Returns:
        bool: True if copy was successful, False otherwise

    Raises:
        subprocess.CalledProcessError: If hsh-run command fails
    """
    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        'cat "$(rpm --eval %pyproject_deps_config)"',
    ]

    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w") as f:
        subprocess.run(cmd, stdout=f, check=True)

    logger.info(f"Copied pyproject_deps.json to {output_path}")
    return True


def _stage_pyproject_deps(file_path: str) -> bool:
    """
    Stage pyproject_deps.json file in git (git add).

    Args:
        file_path: Path to the file to stage

    Returns:
        bool: True if file was staged and has changes, False if no changes or not in git repo
    """
    # Check if we're in a git repository
    try:
        subprocess.run(["git", "status"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.info("Not in a git repository, skipping git operations")
        return False

    # Stage the file
    try:
        subprocess.run(["git", "add", file_path], check=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to stage file in git: {e}")
        return False

    # Check if there are changes
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        has_changes = bool(status_proc.stdout.strip())
        return has_changes
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to check git status: {e}")
        return False


@app.command()
def copy_pyproject_deps(
    ctx: typer.Context,
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
    output: str = typer.Option(
        ".gear/pyproject_deps.json",
        "--output",
        "-o",
        help="Output path for the pyproject_deps.json file. Defaults to .gear/pyproject_deps.json",
    ),
):
    """Copy pyproject_deps.json from sandbox to specified output path."""
    config = load_config()
    sandbox_name = sandbox or ctx.obj.get("sandbox") or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    if not env.exists():
        logger.warning(f"Sandbox {sandbox_name} does not exist, initializing...")
        env.init()

    # Handle case where output is a directory - append default filename
    if output.endswith('/') or (os.path.exists(output) and os.path.isdir(output)):
        output = os.path.join(output, "pyproject_deps.json")
    elif not output.endswith('.json') and not os.path.splitext(output)[1]:
        # If no extension provided, assume it's a directory and append filename
        output = os.path.join(output, "pyproject_deps.json")

    logger.info(f"Copying pyproject_deps.json from sandbox {sandbox_name} to {output}")

    try:
        # Use the extracted function to copy deps
        _copy_deps_from_sandbox(env, output)

        # Use the extracted function to stage the file in git
        has_changes = _stage_pyproject_deps(output)
        git_available = has_changes or os.path.exists(os.path.join(os.getcwd(), '.git'))

        # Check if file is already tracked (for commit message)
        pyproject_tracked = False
        if git_available:
            try:
                subprocess.run(
                    ["git", "ls-files", output],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                pyproject_tracked = True
            except subprocess.CalledProcessError:
                pyproject_tracked = False

        # Commit logic: prompt for confirmation unless force_commit is True
        if git_available:
            commit_message = f"Update {os.path.basename(output)}" if pyproject_tracked else f"Add {os.path.basename(output)}"
            if has_changes:
                if force_commit:
                    try:
                        subprocess.run(["git", "commit", "-m", commit_message], check=True)
                        logger.info(
                            f"{os.path.basename(output)} {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}"
                        )
                        rich_print(
                            f"[green]{os.path.basename(output)} {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}[/green]"
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to commit changes: {e}")
                        rich_print(f"[yellow]File copied but commit failed: {e}[/yellow]")
                elif typer.confirm(
                    f"Commit changes to {os.path.basename(output)} with message '{commit_message}'?",
                    default=True,
                ):
                    try:
                        subprocess.run(["git", "commit", "-m", commit_message], check=True)
                        logger.info(
                            f"{os.path.basename(output)} {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}"
                        )
                        rich_print(
                            f"[green]{os.path.basename(output)} {'updated and committed' if pyproject_tracked else 'added and committed'} in sandbox {sandbox_name}[/green]"
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to commit changes: {e}")
                        rich_print(f"[yellow]File copied but commit failed: {e}[/yellow]")
                else:
                    logger.info(
                        f"""{os.path.basename(output)} added to git index but not committed in sandbox {sandbox_name}.
                        Don't forget to add this line to your .gear/rules file:

                        copy: {output}

                        And this to your .spec:

                        SourceX: %pyproject_deps_config_name
                        """
                    )
                    rich_print(
                        f"""[yellow]{os.path.basename(output)} added to git index but not committed in sandbox {sandbox_name}.
                            Don't forget to add this line to your .gear/rules file:

                            copy: {output}

                            And this to your .spec:

                            SourceX: %pyproject_deps_config_name
                            [/yellow]"""
                    )
            else:
                logger.info(f"{os.path.basename(output)} is unchanged in sandbox {sandbox_name}, no commit needed")
                rich_print(
                    f"[yellow]{os.path.basename(output)} is unchanged in sandbox {sandbox_name}, no commit needed[/yellow]"
                )
        else:
            logger.info(f"{os.path.basename(output)} copied successfully (not in git repository)")
            rich_print(f"[green]{os.path.basename(output)} copied successfully (not in git repository)[/green]")

        rich_print(f"[green]{os.path.basename(output)} copied to {output}[/green]")
        logger.info(f"{os.path.basename(output)} copied to {output} in sandbox {sandbox_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy or stage {os.path.basename(output)}: {e}")
        rich_print(f"[red]Failed to copy or stage {os.path.basename(output)}: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
