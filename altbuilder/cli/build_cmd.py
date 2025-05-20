import os
import json
import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..core.build_manager import BuildManager
from ..utils.logger import init_logger, logger
from ..utils.helpers import colorize


@click.command("build")
@click.argument("source_dir", required=False)
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
@click.help_option("--help", "-h")
def build_cmd(source_dir, arch, branch, reinit, sandbox):
    """Build a package in the specified sandbox."""
    config = load_config()

    if sandbox:
        sandbox_name = sandbox
    elif branch and arch:
        sandbox_name = f"{branch}-{arch}"
    else:
        sandbox_name = f"{config['branch']}-{config['arch']}"

    # Sandbox info file
    sandbox_info_file = os.path.join(
        config["environment_dir"],
        ".sandboxes",
        sandbox_name,
        "hasher",
        "sandbox_info.json",
    )

    # Get existing sandbox info
    existing_info = None
    if os.path.exists(sandbox_info_file):
        try:
            existing_info = Environment.from_info_file(sandbox_info_file)
        except Exception as e:
            existing_info = None

    branch = branch or (existing_info.branch if existing_info else None)
    arch = arch or (existing_info.arch if existing_info else None)
    task_id = existing_info.task_id if existing_info else None

    # Sandbox config
    sandbox_config = get_sandbox_config(sandbox_name, config, branch=branch, arch=arch)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=task_id)

    if reinit or not env.exists():
        click.echo(
            colorize(
                f"Initializing sandbox: {sandbox_name} [{branch}-{arch}]",
                bold=True,
            )
        )
        if not branch or not arch:
            click.echo(
                colorize("Error: --branch and --arch are required.", color="red")
            )
            return
        if env.exists():
            env.clean()
        env.init()

    builder = BuildManager(env)
    click.echo(colorize(f"Building in sandbox: {sandbox_name}", bold=True))

    # Get package name for logging purposes
    package_name = os.path.basename(os.path.abspath(source_dir or os.getcwd()))
    log_dir = os.path.join(config["build_logs_dir"], sandbox_name, package_name)

    # Create build-specific log directory
    build_number = 1
    while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
        build_number += 1
    build_log_dir = os.path.join(log_dir, f"build_{build_number}")
    os.makedirs(build_log_dir, exist_ok=True)

    # Setup build-specific logger
    build_log = os.path.join(build_log_dir, "build.log")
    cmd_log = os.path.join(build_log_dir, "commands.log")

    # Save current logger handlers and configure build-specific logging
    init_logger(
        sandbox_name, build_log_dir, config, build_log=build_log, cmd_log=cmd_log
    )

    builder.build(source_dir, env.apt_conf, build_log_dir=build_log_dir)
    click.echo(colorize(f"Build completed in sandbox {sandbox_name}.", color="green"))
    click.echo(colorize(f"Build logs available at: {build_log_dir}", color="cyan"))
