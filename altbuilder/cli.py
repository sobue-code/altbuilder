import yaml
import click
import os
import shutil
import subprocess
import glob
from .config import load_config, get_sandbox_config
from .core.environment import Environment
from .core.build_manager import BuildManager
from .utils.logger import init_logger, logger
from .utils.helpers import colorize, run_logged_command


@click.group()
@click.option(
    "--sandbox",
    "-s",
    help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
)
@click.help_option("--help", "-h")
def cli(sandbox):
    """Command-line interface for managing ALT Linux sandboxes."""
    ctx = click.get_current_context()
    ctx.obj = {"sandbox": sandbox}
    config = load_config()
    init_logger(config=config)
    logger.info(f"Loaded config from {config.get('config_file', 'default')}")


@cli.command()
@click.option("--branch", help="Branch name (e.g., Sisyphus). Overrides config.")
@click.option("--arch", help="Architecture (e.g., x86_64). Overrides config.")
@click.option("--task", type=int, help="Attach task repository by ID.")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> or config."
)
@click.help_option("--help", "-h")
def init(branch, arch, task, sandbox):
    """Initialize a new sandbox environment."""
    config = load_config()
    default_sandbox = f"{branch or config['branch']}-{arch or config['arch']}"
    sandbox_name = sandbox or default_sandbox
    if task:
        sandbox_name += f"-{task}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=task)
    click.echo(colorize(f"Initializing sandbox: {sandbox_name}", bold=True))
    env.init()
    click.echo(
        colorize(f"Sandbox {sandbox_name} initialized successfully.", color="green")
    )


@cli.command()
@click.argument("source_dir", required=False)
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize the sandbox before building."
)
@click.help_option("--help", "-h")
def build(source_dir, sandbox, reinit):
    """Build a package in the specified sandbox."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    if reinit or not env.exists():
        click.echo(colorize(f"Initializing sandbox: {sandbox_name}", bold=True))
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


@cli.command()
@click.option("--sandbox", "-s", help="Show details for the specified sandbox.")
@click.help_option("--help", "-h")
def list(sandbox):
    """List all existing sandboxes."""
    config = load_config()
    logger.info("Listing all existing sandboxes")
    environment_dir = config["environment_dir"]
    altbuilder_dir = os.path.join(environment_dir, ".sandboxes")
    if not os.path.exists(altbuilder_dir):
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
        return

    sandboxes = [
        d
        for d in os.listdir(altbuilder_dir)
        if os.path.isdir(os.path.join(altbuilder_dir, d))
    ]

    if not sandboxes:
        click.echo(colorize("No sandboxes found.", color="yellow"))
        logger.info("No sandboxes found")
    else:
        click.echo(colorize("Existing sandboxes:", bold=True))
        for sandbox_name in sandboxes:
            sandbox_path = os.path.join(altbuilder_dir, sandbox_name)

            # Show basic info for all sandboxes
            click.echo(
                f"{colorize(sandbox_name, color='cyan', bold=True)} -> {colorize(sandbox_path, color='green')}"
            )

            # If a specific sandbox is specified, show its repository contents
            if sandbox and sandbox_name == sandbox:
                # Show SRPMS
                srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
                if os.path.exists(srpms_dir):
                    click.echo(colorize("  Source RPMs:", color="yellow", bold=True))
                    for srpm in glob.glob(os.path.join(srpms_dir, "*.rpm")):
                        click.echo(
                            f"  {colorize(os.path.basename(srpm), color='yellow')} -> {srpm}"
                        )

                # Show binary RPMs for each architecture
                arch_dirs = glob.glob(
                    os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")
                )
                for arch_dir in arch_dirs:
                    arch_name = os.path.basename(os.path.dirname(arch_dir))
                    click.echo(
                        colorize(f"  {arch_name} RPMs:", color="green", bold=True)
                    )
                    for rpm in glob.glob(os.path.join(arch_dir, "*.rpm")):
                        click.echo(
                            f"  {colorize(os.path.basename(rpm), color='green')} -> {rpm}"
                        )

        logger.info(f"Found {len(sandboxes)} sandboxes")
        logger.debug(f"Sandboxes: {', '.join(sandboxes)}")


@cli.command()
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option("--root", is_flag=True, help="Run shell as root.")
@click.option("--internet", is_flag=True, help="Enable internet in the shell.")
@click.help_option("--help", "-h")
def shell(sandbox, root, internet):
    """Enter the shell of the specified sandbox.

    The sandbox can be specified using the global --sandbox option
    (e.g., `altbuilder --sandbox Sisyphus-x86_64 shell`) or the
    command-specific --sandbox option (e.g., `altbuilder shell --sandbox Sisyphus-x86_64`).
    """
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)
    click.echo(colorize(f"Entering shell for sandbox: {sandbox_name}", bold=True))
    try:
        env.shell(root, internet)
    except EnvironmentError as e:
        click.echo(colorize(f"Error: {e}", color="red"))


@cli.command()
@click.option(
    "--sandbox",
    "-s",
    help="Sandbox name to clean. Defaults to <branch>-<arch> from config.",
)
@click.option("--all", is_flag=True, help="Clean all sandboxes.")
@click.help_option("--help", "-h")
def clean(sandbox, all):
    """Clean the specified sandbox or all sandboxes."""
    config = load_config()
    environment_dir = config["environment_dir"]
    sandboxes_dir = os.path.join(environment_dir, ".sandboxes")
    logger.debug(f"Cleaning or all sandboxes in {sandboxes_dir}")
    logger.debug(f"{os.listdir(sandboxes_dir)}")

    if all:
        logger.info("Cleaning all sandboxes")
        if not os.path.exists(sandboxes_dir):
            click.echo(colorize("No sandboxes to clean.", color="yellow"))
            logger.info("No sandboxes found")
            return
        sandboxes = [
            d
            for d in os.listdir(sandboxes_dir)
            if os.path.isdir(os.path.join(sandboxes_dir, d))
        ]
        failed = []
        for sandbox in sandboxes:
            sandbox_path = os.path.join(sandboxes_dir, sandbox)
            cmd = ["hsh", "--cleanup-only", sandbox_path + "/hasher"]
            try:
                run_logged_command(cmd, check=True)
                shutil.rmtree(sandbox_path, ignore_errors=True)
                click.echo(colorize(f"Sandbox {sandbox} cleaned.", color="green"))
                logger.info(f"Cleaned sandbox {sandbox}")
            except (subprocess.CalledProcessError, OSError) as e:
                click.echo(colorize(f"Error cleaning {sandbox}: {e}", color="red"))
                logger.error(f"Failed to clean sandbox {sandbox}: {e}")
                failed.append(sandbox)
        if failed:
            click.echo(
                colorize(
                    f"Failed to clean {len(failed)} sandboxes: {', '.join(failed)}",
                    color="red",
                )
            )
            logger.error(f"Failed sandboxes: {', '.join(failed)}")
        else:
            logger.info("All sandboxes cleaned successfully")
    elif sandbox:
        sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
        sandbox_config = get_sandbox_config(sandbox_name, config)
        init_logger(sandbox_name, config["build_logs_dir"], config)
        env = Environment(sandbox_name, sandbox_config)
        try:
            cmd = ["hsh", "--cleanup-only", env.hasher_dir]
            run_logged_command(cmd, check=True)
            env.clean()
            click.echo(colorize(f"Sandbox {sandbox_name} cleaned.", color="green"))
            logger.info(f"Cleaned sandbox {sandbox_name}")
        except (subprocess.CalledProcessError, EnvironmentError) as e:
            click.echo(colorize(f"Error: {e}", color="red"))
            logger.error(f"Failed to clean sandbox {sandbox_name}: {e}")
    else:
        click.echo(
            colorize("Please specify a sandbox to clean or use --all.", color="red")
        )


@cli.command()
def config():
    """Print the current config."""
    config = load_config()
    click.echo(yaml.dump(config))


if __name__ == "__main__":
    cli()
