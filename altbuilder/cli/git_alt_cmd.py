import typer

from altbuilder.config import load_config
from altbuilder.core.remote import RemoteError, RemoteRepository
from altbuilder.utils import colorize, init_logger, logger

app = typer.Typer(
    name="git.alt",
    help="""Search or clone a package's git repository from git.altlinux.org or a custom URL.""",
)


@app.command()
def git_alt_cmd(
    package_name: str = typer.Argument(
        ..., help="Name of the package to search or clone (e.g., 'guacamole-auth-duo')."
    ),
    clone: bool = typer.Option(
        False, "--clone", "-c", help="Clone the repository to the current directory."
    ),
    gitalt_clone: bool = typer.Option(
        False, "--gitalt-clone", "-g", help="Clone the repository to git.alt."
    ),
    url: str = typer.Option(
        None, "--url", "-u", help="Custom repository URL to clone (e.g., from GitHub)."
    ),
    gitalt_dir: str = typer.Option(
        "packages",
        "--gitalt-dir",
        "-d",
        help="Directory on git.alt to clone into (e.g., 'private'). Defaults to 'packages'.",
    ),
):
    """Search or clone a package's git repository from git.altlinux.org or a custom URL."""
    config = load_config()
    init_logger("git_alt", config["build_logs_dir"], config)

    logger.info(f"Running git command for package {package_name}")
    remote = RemoteRepository(config)

    try:
        repo_url = url if url else remote.search_git_repository(package_name)
        if not repo_url:
            typer.echo(colorize(f"No repository found for {package_name}", color="red"))
            logger.error(f"No repository found for {package_name}")
            raise typer.Exit(code=1)

        typer.echo(colorize(f"Found repository: {repo_url}", color="green"))

        if clone or gitalt_clone:
            repo_path = remote.clone_git_repository(
                package_name,
                clone=clone,
                gitalt_clone=gitalt_clone,
                custom_url=url,
                gitalt_dir=gitalt_dir,
            )
            if clone:
                typer.echo(colorize(f"Repository cloned to {repo_path}", color="green"))
                logger.info(f"Repository cloned to {repo_path}")
            if gitalt_clone:
                typer.echo(
                    colorize(
                        f"Repository cloned to git.alt:{gitalt_dir}/{package_name}",
                        color="green",
                    )
                )
                logger.info(f"Repository cloned to git.alt:{gitalt_dir}/{package_name}")
    except RemoteError as e:
        logger.error(f"Error running git command: {e}")
        typer.echo(colorize(f"Error: {e}", color="red"))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
