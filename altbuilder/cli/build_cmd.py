import os

import typer
from rich import print as rich_print

from altbuilder.config import load_config
from altbuilder.core.build_manager import BuildManager
from altbuilder.exceptions import ToolError
from altbuilder.utils import get_spec_metadata, init_logger, logger
from altbuilder.utils.setup_sandbox import setup_sandbox
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="build",
    help="Build a package in the specified sandbox.",
)


@app.command()
def build_cmd(
    ctx: typer.Context,
    build_target: str = typer.Argument(
        None, help="Source directory or src.rpm file to build."
    ),
    arch: str = typer.Option(
        None, "--arch", "-a", help="Architecture (e.g., x86_64). Overrides config."
    ),
    branch: str = typer.Option(
        None, "--branch", "-b", help="Branch name (e.g., Sisyphus). Overrides config."
    ),
    task: int = typer.Option(
        None, "--task", "-t", help="Attach task repository by ID."
    ),
    reinit: bool = typer.Option(
        False, "--reinit", "-r", help="Reinitialize the sandbox before building."
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    no_check: bool = typer.Option(
        False, "--no-check", help="Do not run package tests (rpmbuild --without=check)."
    ),
    hsh_extra: str = typer.Option(
        "", "--hsh-extra", help="Extra flags to pass to hsh."
    ),
    rpmbuild_extra: str = typer.Option(
        "",
        "--rpmbuild-extra",
        help="Extra flags to pass to rpmbuild (via --rpmbuild-args).",
    ),
):
    """Build a package in the specified sandbox. BUILD_TARGET can be a source directory or an src.rpm file."""
    json_mode = is_json_mode(ctx)
    config = load_config()

    # Use sandbox from context if not provided
    sandbox = sandbox or ctx.obj.get("sandbox")

    # Determine if build_target is an src.rpm file
    if (
        build_target
        and os.path.isfile(build_target)
        and build_target.endswith(".src.rpm")
    ):
        is_src_rpm = True
    else:
        is_src_rpm = False
        if not build_target:
            build_target = os.getcwd()

    # Set up sandbox environment
    env = setup_sandbox(sandbox, branch, arch, reinit, config, task_id=task)
    if env is None:
        error_msg = "Failed to initialize sandbox."
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", message=error_msg, code=1)
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)
        return

    # Get package metadata
    package_name, version, release = get_spec_metadata(build_target, is_src_rpm)
    if not package_name:
        package_name = (
            os.path.basename(build_target).replace(".src.rpm", "")
            if is_src_rpm
            else os.path.basename(os.path.abspath(build_target))
        )
        version = "unknown"
        release = "unknown"

    # Log package metadata
    build_message = f"Building {package_name} (Version: {version}, Release: {release}) in sandbox: {env.name}"
    logger.info(build_message)
    if not json_mode:
        rich_print(f"[bold]{build_message}[/bold]")

    log_dir = os.path.join(config["build_logs_dir"], env.name, package_name)

    # Create build-specific log directory
    build_number = 1
    while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
        build_number += 1
    built_log_dir = os.path.join(log_dir, f"build_{build_number}")
    os.makedirs(built_log_dir, exist_ok=True)

    # Setup build-specific logger
    build_log = os.path.join(built_log_dir, "build.log")
    cmd_log = os.path.join(built_log_dir, "commands.log")
    init_logger(env.name, built_log_dir, config, build_log=build_log, cmd_log=cmd_log)

    # Perform the build
    builder = BuildManager(env)
    try:
        builder.build(
            build_target=build_target,
            is_src_rpm=is_src_rpm,
            apt_conf=env.apt_conf,
            build_log_dir=built_log_dir,
            no_check=no_check,
            hsh_extra=hsh_extra,
            rpmbuild_extra=rpmbuild_extra,
        )
        success_msg = f"Build completed in sandbox {env.name}."
        logger.info(success_msg)

        if json_mode:
            json_response(
                ctx,
                "success",
                message=success_msg,
                log_path=built_log_dir,
                package={
                    "name": package_name,
                    "version": version,
                    "release": release,
                },
                sandbox=env.name,
            )
        else:
            rich_print(f"[green]{success_msg}[/green]")
            rich_print(f"[cyan]Build logs available at: {built_log_dir}[/cyan]")
    except ToolError as e:
        error_msg = f"Error building package {package_name}: {str(e)}"
        logger.error(error_msg)

        if json_mode:
            json_response(
                ctx,
                "error",
                message=error_msg,
                log_path=built_log_dir,
                package={
                    "name": package_name,
                    "version": version,
                    "release": release,
                },
                sandbox=env.name,
                code=1,
            )
        else:
            rich_print(f"[red]{error_msg}. Logs available at: {built_log_dir}[/red]")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
