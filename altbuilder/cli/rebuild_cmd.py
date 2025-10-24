import os
import subprocess
from typing import Any, Dict, Optional

import typer
from rich import print as rich_print

from altbuilder.adapters.hasher import HasherAdapter
from altbuilder.config import load_config
from altbuilder.core.build_manager import BuildManager
from altbuilder.core.remote import RemoteRepository
from altbuilder.utils import get_spec_metadata, logger
from altbuilder.utils.check_task_info import fetch_task_info
from altbuilder.utils.json_utils import is_json_mode, json_response
from altbuilder.utils.setup_sandbox import derive_sandbox_name, setup_sandbox

CLI_ERROR_EXIT_CODE = 1
REBUILD_FAILURE_EXIT_CODE = 2
DEFAULT_ERROR_TYPE = "altbuilder_error"
REBUILD_ERROR_TYPE = "rebuild_failed"
VERSION_MISMATCH_ERROR_TYPE = "version_mismatch"
PACKAGE_NOT_FOUND_ERROR_TYPE = "package_not_found"

app = typer.Typer(
    name="rebuild",
    help="Rebuild a package in the specified sandbox by fetching its src.rpm from a repository.",
)


@app.command()
def rebuild_cmd(
    ctx: typer.Context,
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
    rebuild_id: str = typer.Option(
        None,
        "--rebuild-id",
        help="Unique identifier for the rebuild operation.",
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
    autoclean: bool = typer.Option(
        False,
        "--autoclean",
        "-c",
        help="Clean sandbox after rebuild.",
    ),
    version: str = typer.Option(
        None,
        "--version",
        "-v",
        help="Specific version to check for (e.g., 1.0.0). If specified, the package version must match exactly.",
    ),
    release: str = typer.Option(
        None,
        "--release",
        help="Specific release to check for (e.g., alt1). If specified, the package release must match exactly.",
    ),
):
    """Rebuild a package by fetching its corresponding src.rpm and building it in sandbox."""
    json_mode = is_json_mode(ctx)
    params = {
        "package_name": package_name,
        "sandbox": sandbox,
        "branch": branch,
        "arch": arch,
        "task": task,
        "rebuild_id": rebuild_id,
        "reinit": reinit,
        "no_check": no_check,
        "rpmbuild_extra": rpmbuild_extra,
        "autoclean": autoclean,
        "version": version,
        "release": release,
    }
    log_path = None

    def emit_error(
        message: str,
        *,
        code: int = CLI_ERROR_EXIT_CODE,
        log: bool = True,
        error_type: str = DEFAULT_ERROR_TYPE,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if log:
            logger.error(message)
        if json_mode:
            payload: Dict[str, Any] = extra.copy() if extra else {}
            if error_type and "error_type" not in payload:
                payload["error_type"] = error_type
            json_response(
                ctx,
                "error",
                params=params,
                message=message,
                log_path=log_path,
                code=code,
                **payload,
            )
        else:
            rich_print(f"[red]{message}[/red]")
            raise typer.Exit(code=code)

    build_started = False

    try:
        config = load_config()
    except Exception as e:
        emit_error(f"Failed to load configuration: {e}")

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
                task_branch_hint = (info.get("branch") or "").strip() if info else ""
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
            skip_hsh_init=True,
        )
    except Exception as e:
        resolved_sandbox_name = resolve_sandbox_name_hint()
        emit_error(f"Failed to set up sandbox {resolved_sandbox_name}: {e}")

    if env is None:
        resolved_sandbox_name = resolve_sandbox_name_hint()
        emit_error(f"Error: Failed to initialize sandbox {resolved_sandbox_name}.")

    sandbox_name = env.name
    sandbox_config = env.config
    params["sandbox"] = sandbox_name

    mirror = sandbox_config.get("mirror")
    sandbox_branch = sandbox_config.get("branch")
    if not branch:
        params["branch"] = sandbox_branch
    if not arch:
        params["arch"] = sandbox_config.get("arch")
    if not mirror or not sandbox_branch:
        emit_error("Mirror or branch not specified in configuration.")

    temp_file, src_rpm_path = None, None
    try:
        remote_repo = RemoteRepository(config)
        src_rpm_url_or_path, src_rpm_filename, found_version, found_release = remote_repo.find_src_rpm(
            package_name, mirror, sandbox_branch, version, release
        )
        if not src_rpm_url_or_path or not src_rpm_filename:
            emit_error(
                f"No matching src.rpm found for {package_name} in {mirror} (branch: {sandbox_branch}).",
                error_type=PACKAGE_NOT_FOUND_ERROR_TYPE,
            )
        if mirror.startswith("file:"):
            src_rpm_path = src_rpm_url_or_path
        elif mirror.startswith("http"):
            temp_file = remote_repo.download_src_rpm(
                src_rpm_url_or_path, src_rpm_filename
            )
            src_rpm_path = temp_file
        else:
            emit_error(f"Unsupported mirror type: {mirror}")

        # Check version and release if specified
        if version or release:
            if found_version is None or found_release is None:
                # Try to get version/release from spec file as fallback
                meta_name, spec_version, spec_release = get_spec_metadata(src_rpm_path, is_src_rpm=True)
                if spec_version and spec_release:
                    found_version = spec_version
                    found_release = spec_release

            version_mismatch = False
            version_error_msg = ""

            if version and found_version != version:
                version_mismatch = True
                version_error_msg += f"Version mismatch: requested '{version}', found '{found_version}'"

            if release and found_release != release:
                version_mismatch = True
                if version_error_msg:
                    version_error_msg += "; "
                version_error_msg += f"Release mismatch: requested '{release}', found '{found_release}'"

            if version_mismatch:
                error_msg = f"Package {package_name} found but {version_error_msg}."
                emit_error(
                    error_msg,
                    error_type=VERSION_MISMATCH_ERROR_TYPE,
                    extra={
                        "requested_version": version,
                        "requested_release": release,
                        "found_version": found_version,
                        "found_release": found_release,
                    }
                )

        meta_name, version, release = get_spec_metadata(src_rpm_path, is_src_rpm=True)
        if not meta_name:
            meta_name = os.path.basename(src_rpm_path).replace(".src.rpm", "")
            version, release = "unknown", "unknown"

        rebuild_suffix = f" [rebuild id: {rebuild_id}]" if rebuild_id else ""
        rebuild_message = (
            f"Rebuilding package: {meta_name} (Version: {version}, Release: {release}) "
            f"in sandbox: {sandbox_name}{rebuild_suffix}"
        )
        logger.info(rebuild_message)
        if not json_mode:
            rich_print(f"[bold]{rebuild_message}[/bold]")
        log_dir = os.path.join(
            sandbox_config["build_logs_dir"], sandbox_name, meta_name
        )
        build_number = 1
        while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
            build_number += 1
        build_log_dir = os.path.join(log_dir, f"build_{build_number}")
        os.makedirs(build_log_dir, exist_ok=True)
        log_path = build_log_dir

        hasher = HasherAdapter(base_dir=config.get("base_dir"))
        builder = BuildManager(env, hasher_adapter=hasher)
        build_started = True
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
            rebuild_id=rebuild_id,
        )

        if autoclean:
            try:
                env.clean()
                logger.info(f"Sandbox {sandbox_name} cleaned after rebuild")
                if not json_mode:
                    rich_print(
                        f"[green]Sandbox {sandbox_name} cleaned after rebuild.[/green]"
                    )
            except (subprocess.CalledProcessError, OSError) as e:
                logger.error(f"Autoclean failed for sandbox {sandbox_name}: {e}")
                if not json_mode:
                    rich_print(f"[red]Autoclean failed for {sandbox_name}: {e}[/red]")

        if json_mode:
            json_response(
                ctx,
                "success",
                params=params,
                log_path=log_path,
                package={
                    "name": meta_name,
                    "version": version,
                    "release": release,
                },
                sandbox=sandbox_name,
                rebuild_id=rebuild_id,
            )
            return
        else:
            success_message = (
                f"Successfully rebuilt {meta_name} (Version: {version}, Release: {release}) "
                f"(sandbox: {sandbox_name}){rebuild_suffix}."
            )
            rich_print(f"[green]{success_message}[/green]")

    except typer.Exit:
        raise
    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError):
            logger.error(
                "Command failed (exit %s): %s",
                getattr(e, "returncode", "unknown"),
                " ".join(getattr(e, "cmd", [])) if getattr(e, "cmd", None) else str(e),
            )
            extra: Dict[str, Any] = {}
            if getattr(e, "returncode", None) is not None:
                extra.setdefault("error_details", {})["returncode"] = e.returncode
            if getattr(e, "cmd", None):
                extra.setdefault("error_details", {})["command"] = " ".join(e.cmd)
            error_type = REBUILD_ERROR_TYPE if build_started else DEFAULT_ERROR_TYPE
            exit_code = (
                REBUILD_FAILURE_EXIT_CODE
                if build_started
                else CLI_ERROR_EXIT_CODE
            )
            emit_error(
                f"Failed to rebuild {package_name}: {e}",
                log=False,
                code=exit_code,
                error_type=error_type,
                extra=extra or None,
            )
        else:
            logger.error("Unexpected error during rebuild: %s", e)
            emit_error(
                f"Failed to rebuild {package_name}: {e}",
                log=False,
            )
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                warning_msg = (
                    f"Warning: Failed to remove temporary file {temp_file}: {e}"
                )
                logger.warning(warning_msg)
                if not json_mode:
                    rich_print(f"[yellow]{warning_msg}[/yellow]")


if __name__ == "__main__":
    app()
