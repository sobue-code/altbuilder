import os

import typer

from ..config import load_config
from ..core.build_manager import BuildManager
from ..exceptions import ToolError
from ..utils import colorize, get_spec_metadata, init_logger
from ..utils.setup_sandbox import setup_sandbox

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
        typer.echo(
            colorize(
                "Error: Failed to initialize sandbox.",
                color="red",
            )
        )
        raise typer.Exit(code=1)

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
    typer.echo(
        colorize(
            f"Building {package_name} (Version: {version}, Release: {release}) in sandbox: {env.name}",
            bold=True,
        )
    )
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
        typer.echo(colorize(f"Build completed in sandbox {env.name}.", color="green"))
        typer.echo(colorize(f"Build logs available at: {built_log_dir}", color="cyan"))
    except ToolError as e:
        typer.echo(
            colorize(
                f"Error building package {package_name}: {str(e)}. Logs available at: {built_log_dir}",
                color="red",
            )
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
