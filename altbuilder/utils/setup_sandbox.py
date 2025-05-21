import click
from ..config import get_sandbox_config
from ..core.environment import Environment
from .logger import init_logger
from .colorize import colorize
from .get_sandbox_info import get_sandbox_info


def setup_sandbox(sandbox, branch, arch, reinit, config, task_id=None):
    """Set up or reinitialize a sandbox environment.

    Args:
        sandbox (str): Sandbox name. If None, derived from branch and arch.
        branch (str): Branch name (e.g., Sisyphus). Can override config.
        arch (str): Architecture (e.g., x86_64). Can override config.
        reinit (bool): If True, reinitialize the sandbox if it exists.
        config (dict): Configuration dictionary.
        task_id (int, optional): Task ID to attach to the sandbox.

    Returns:
        Environment: Configured sandbox environment.

    Raises:
        click.ClickException: If branch or arch is missing when required.
    """
    # Resolve sandbox name
    if sandbox:
        sandbox_name = sandbox
    elif branch and arch:
        sandbox_name = f"{branch}-{arch}"
    else:
        sandbox_name = f"{config['branch']}-{config['arch']}"

    # Get existing sandbox info
    existing_info = get_sandbox_info(sandbox_name, config)
    branch = branch or (existing_info.branch if existing_info else config["branch"])
    arch = arch or (existing_info.arch if existing_info else config["arch"])
    resolved_task_id = task_id or (existing_info.task_id if existing_info else None)

    # Validate branch and arch for initialization
    if not branch or not arch:
        raise click.ClickException(
            colorize(
                "Error: --branch and --arch are required for initialization.",
                color="red",
            )
        )

    # Configure sandbox and logger
    sandbox_config = get_sandbox_config(sandbox_name, config, branch=branch, arch=arch)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=resolved_task_id)

    # Handle sandbox initialization or reinitialization
    if env.exists():
        if reinit:
            reinit_info_str = colorize(
                f"Reinitializing sandbox: {sandbox_name} [{branch}-{arch}", bold=True
            )
            reinit_info_str += colorize(f" {task_id if task_id else '\b'}]", bold=True)
            click.echo(reinit_info_str)
            env.clean()
            env.init()
            click.echo(
                colorize(
                    f"Sandbox {sandbox_name} reinitialized successfully.", color="green"
                )
            )
        else:
            click.echo(
                colorize(f"Sandbox {sandbox_name} already exists.", color="yellow")
            )
    else:
        init_info_str = colorize(
            f"Initializing sandbox: {sandbox_name} [{branch}-{arch}", bold=True
        )
        init_info_str += colorize(f" {task_id if task_id else '\b'}]")
        click.echo(init_info_str)
        env.init()
        click.echo(
            colorize(f"Sandbox {sandbox_name} initialized successfully.", color="green")
        )

    return env
