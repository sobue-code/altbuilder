import os

import typer
from rich import print as rich_print

from altbuilder.adapters.hasher import HasherAdapter
from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.build_manager import BuildManager
from altbuilder.core.environment import Environment
from altbuilder.core.remote import RemoteRepository
from altbuilder.utils import get_spec_metadata, init_logger, logger

app = typer.Typer(
    name="rebuild",
    help="Rebuild a package in the specified sandbox by fetching its src.rpm from a repository.",
)


@app.command()
def rebuild_cmd(
    package_name: str = typer.Argument(
        ...,
        help="Exact package name to rebuild (e.g., python3-module-hypothesis).",
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
    ),
    no_check: bool = typer.Option(
        False,
        "--no-check",
        help="Do not run package tests (rpmbuild --without=check).",
    ),
    rpmbuild_extra: str = typer.Option(
        "",
        "--rpmbuild-extra",
        help="Extra flags to pass to rpmbuild (via --rpmbuild-args).",
    ),
):
    """Rebuild a package by fetching its corresponding src.rpm and building it in sandbox."""
    # Load config
    try:
        config = load_config()
    except Exception as e:
        rich_print(f"[red]Failed to load configuration: {e}")
        raise typer.Exit(code=1)

    sandbox_name = (
        sandbox or f"{config.get('branch', 'Sisyphus')}-{config.get('arch', 'x86_64')}"
    )
    try:
        sandbox_config = get_sandbox_config(sandbox_name, config)
    except Exception as e:
        rich_print(f"[red]Failed to get sandbox configuration for {sandbox_name}: {e}")
        raise typer.Exit(code=1)

    # Logging
    try:
        init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    except Exception as e:
        rich_print(f"[red]Failed to initialize logger: {e}")
        raise typer.Exit(code=1)

    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        rich_print(f"[red]Sandbox {sandbox_name} does not exist.[/red]")
        raise typer.Exit(code=1)

    mirror, branch = sandbox_config.get("mirror"), sandbox_config.get("branch")
    if not mirror or not branch:
        rich_print("[red]Mirror or branch not specified in configuration.[/red]")
        raise typer.Exit(code=1)

    temp_file, src_rpm_path = None, None
    try:
        # Initialize RemoteRepository
        remote_repo = RemoteRepository(config)

        # Search for src.rpm using RemoteRepository
        src_rpm_url_or_path, src_rpm_filename = remote_repo.find_src_rpm(
            package_name, mirror, branch
        )
        if not src_rpm_url_or_path or not src_rpm_filename:
            rich_print(
                f"[red]No matching src.rpm found for {package_name} in {mirror} (branch: {branch})[/red]"
            )
            raise typer.Exit(code=1)

        # Handle local or remote src.rpm
        if mirror.startswith("file:"):
            src_rpm_path = src_rpm_url_or_path
        elif mirror.startswith("http"):
            temp_file = remote_repo.download_src_rpm(
                src_rpm_url_or_path, src_rpm_filename
            )
            src_rpm_path = temp_file
        else:
            rich_print(f"[red]Unsupported mirror type: {mirror}[/red]")
            raise typer.Exit(code=1)

        # Metadata
        meta_name, version, release = get_spec_metadata(src_rpm_path, is_src_rpm=True)
        if not meta_name:
            meta_name = os.path.basename(src_rpm_path).replace(".src.rpm", "")
            version, release = "unknown", "unknown"

        logger.info(
            f"Rebuilding package: {meta_name} (Version: {version}, Release: {release}) in sandbox: {sandbox_name}"
        )
        rich_print(
            f"[bold]Rebuilding package: {meta_name} (Version: {version}, Release: {release}) in sandbox: {sandbox_name}[/bold]"
        )

        # Build log dir
        log_dir = os.path.join(
            sandbox_config["build_logs_dir"], sandbox_name, meta_name
        )
        build_number = 1
        while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
            build_number += 1
        build_log_dir = os.path.join(log_dir, f"build_{build_number}")
        os.makedirs(build_log_dir, exist_ok=True)

        hasher = HasherAdapter(base_dir=config.get("base_dir"))
        builder = BuildManager(env, hasher_adapter=hasher)
        builder.build(
            build_target=src_rpm_path,
            is_src_rpm=True,
            apt_conf=None,
            only_srpm=False,
            build_log_dir=build_log_dir,
            no_check=no_check,
            hsh_extra="",
            rpmbuild_extra=rpmbuild_extra,
            command="rebuild",
        )

        rich_print(
            f"[green]Successfully rebuilt {meta_name} (Version: {version}, Release: {release}) (sandbox: {sandbox_name}).[/green]"
        )

    except Exception as e:
        rich_print(f"[red]Failed to rebuild {package_name}: {e}[/red]")
        raise typer.Exit(code=1)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                rich_print(
                    f"[yellow]Warning: Failed to remove temporary file {temp_file}: {e}[/yellow]"
                )


if __name__ == "__main__":
    app()
