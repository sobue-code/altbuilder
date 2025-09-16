import os

import typer
from rich import print as rich_print

from altbuilder.adapters.hasher import HasherAdapter
from altbuilder.config import load_config
from altbuilder.core.build_manager import BuildManager
from altbuilder.core.remote import RemoteRepository
from altbuilder.utils import get_spec_metadata, logger
from altbuilder.utils.check_task_info import fetch_task_info
from altbuilder.utils.setup_sandbox import derive_sandbox_name, setup_sandbox

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
    branch: str = typer.Option(
        None,
        "--branch",
        "-b",
        help="Branch name (e.g., Sisyphus). Overrides config when initializing sandbox.",
    ),
    arch: str = typer.Option(
        None,
        "--arch",
        "-a",
        help="Architecture (e.g., x86_64). Overrides config when initializing sandbox.",
    ),
    task: int = typer.Option(
        None,
        "--task",
        "-t",
        help="Attach task repository by ID.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize the sandbox before rebuilding.",
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

    task_branch_hint = None

    def resolve_sandbox_name_hint() -> str:
        nonlocal task_branch_hint
        if sandbox:
            return sandbox

        branch_candidate = branch.strip() if branch else None
        arch_candidate = arch.strip() if arch else None

        if task and not branch_candidate:
            if task_branch_hint is None:
                info = fetch_task_info(task, config["rdb_url"])
                task_branch_hint = (
                    (info.get("branch") or "").strip() if info else ""
                )
            if task_branch_hint:
                branch_candidate = task_branch_hint

        branch_candidate = branch_candidate or config.get("branch", "Sisyphus")
        arch_candidate = arch_candidate or config.get("arch", "x86_64")

        return derive_sandbox_name(branch_candidate, arch_candidate, task)

    try:
        env = setup_sandbox(
            sandbox,
            branch,
            arch,
            reinit,
            config,
            task_id=task,
        )
    except Exception as e:
        resolved_sandbox_name = resolve_sandbox_name_hint()
        rich_print(
            f"[red]Failed to set up sandbox {resolved_sandbox_name}: {e}[/red]"
        )
        raise typer.Exit(code=1)

    if env is None:
        resolved_sandbox_name = resolve_sandbox_name_hint()
        rich_print(
            f"[red]Error: Failed to initialize sandbox {resolved_sandbox_name}.[/red]"
        )
        raise typer.Exit(code=1)

    sandbox_name = env.name
    sandbox_config = env.config

    mirror = sandbox_config.get("mirror")
    sandbox_branch = sandbox_config.get("branch")
    if not mirror or not sandbox_branch:
        rich_print("[red]Mirror or branch not specified in configuration.[/red]")
        raise typer.Exit(code=1)

    temp_file, src_rpm_path = None, None
    try:
        # Initialize RemoteRepository
        remote_repo = RemoteRepository(config)

        # Search for src.rpm using RemoteRepository
        src_rpm_url_or_path, src_rpm_filename = remote_repo.find_src_rpm(
            package_name, mirror, sandbox_branch
        )
        if not src_rpm_url_or_path or not src_rpm_filename:
            rich_print(
                f"[red]No matching src.rpm found for {package_name} in {mirror} (branch: {sandbox_branch})[/red]"
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
