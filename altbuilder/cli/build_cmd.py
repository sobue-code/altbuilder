import os
import click
from ..config import load_config
from ..core.build_manager import BuildManager
from ..utils import init_logger, colorize
from ..utils.setup_sandbox import setup_sandbox


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

    # Set up sandbox environment
    env = setup_sandbox(sandbox, branch, arch, reinit, config)

    # Proceed with build
    builder = BuildManager(env)

    # Get package name for logging purposes
    package_name = os.path.basename(os.path.abspath(source_dir or os.getcwd()))

    click.echo(colorize(f"Building {package_name} in sandbox: {env.name}", bold=True))
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
    builder.build(source_dir, env.apt_conf, build_log_dir=build_log_dir)
    click.echo(colorize(f"Build completed in sandbox {env.name}.", color="green"))
    click.echo(colorize(f"Build logs available at: {build_log_dir}", color="cyan"))
