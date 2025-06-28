import os
import click
import subprocess
from ..config import load_config
from ..core.build_manager import BuildManager
from ..utils import init_logger, colorize, get_spec_metadata
from ..utils.setup_sandbox import setup_sandbox


@click.command("build")
@click.argument("build_target", required=False)
@click.option(
    "--arch",
    "-a",
    required=False,
    help="Architecture (e.g., x86_64). Overrides config.",
)
@click.option(
    "--branch",
    "-b",
    required=False,
    help="Branch name (e.g., Sisyphus). Overrides config.",
)
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize the sandbox before building."
)
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--no-check",
    is_flag=True,
    help="Do not run package tests (rpmbuild --without=check).",
)
@click.option("--hsh-extra", default="", help="Extra flags to pass to hsh.")
@click.option(
    "--rpmbuild-extra",
    default="",
    help="Extra flags to pass to rpmbuild (via --rpmbuild-args).",
)
@click.help_option("--help", "-h")
def build_cmd(
    build_target, arch, branch, reinit, sandbox, no_check, hsh_extra, rpmbuild_extra
):
    """Build a package in the specified sandbox. BUILD_TARGET can be a source directory or an src.rpm file."""
    config = load_config()

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
    env = setup_sandbox(sandbox, branch, arch, reinit, config)

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
    click.echo(
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
    build_log_dir = os.path.join(log_dir, f"build_{build_number}")
    os.makedirs(build_log_dir, exist_ok=True)

    # Setup build-specific logger
    build_log = os.path.join(build_log_dir, "build.log")
    cmd_log = os.path.join(build_log_dir, "commands.log")
    init_logger(env.name, build_log_dir, config, build_log=build_log, cmd_log=cmd_log)

    # Perform the build
    builder = BuildManager(env)
    builder.build(
        build_target=build_target,
        is_src_rpm=is_src_rpm,
        apt_conf=env.apt_conf,
        build_log_dir=build_log_dir,
        no_check=no_check,
        hsh_extra=hsh_extra,
        rpmbuild_extra=rpmbuild_extra,
    )
    click.echo(colorize(f"Build completed in sandbox {env.name}.", color="green"))
    click.echo(colorize(f"Build logs available at: {build_log_dir}", color="cyan"))
