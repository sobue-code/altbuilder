import click
from rich import print as rich_print
from ..config import get_sandbox_config
from ..core.environment import Environment
from .logger import init_logger, logger
from .get_sandbox_info import get_sandbox_info
from .check_task_info import fetch_task_info


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
    logger.info(f"Resolved task ID: {resolved_task_id}")

    # Validate branch and arch for initialization
    if not branch or not arch:
        raise click.ClickException("--branch and --arch are required for initialization.")
    # Validate task_id if provided
    if resolved_task_id:
        task_info = fetch_task_info(resolved_task_id, config["rdb_url"])
        task_branch = task_info.get("branch", "").lower() if task_info else None
        logger.debug(
            f"Task {resolved_task_id} branch: {task_branch}, expected branch: {branch.lower()}"
        )
        if task_branch != branch.lower():
            rich_print(
                f"[yellow]Warning: Task {resolved_task_id} branch does not match sandbox branch {branch}.[/yellow]"
            )
            return None

    # Configure sandbox and logger
    sandbox_config = get_sandbox_config(sandbox_name, config, branch=branch, arch=arch)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=resolved_task_id)

    # Handle sandbox initialization or reinitialization
    if env.exists():
        if reinit:
            reinit_info_str = f"[bold]Reinitializing sandbox: {sandbox_name} [{branch}-{arch}"
            reinit_info_str += f" {task_id if task_id else '\b'}]"
            rich_print(reinit_info_str + "[/bold]")
            env.clean()
            env.init()
            rich_print(f"[green]Sandbox {sandbox_name} reinitialized successfully.[/green]")
        else:
            rich_print(f"[yellow]Sandbox {sandbox_name} already exists.[/yellow]")
    else:
        init_info_str = f"[bold]Initializing sandbox: {sandbox_name} [{branch}-{arch}"
        init_info_str += f" {task_id if task_id else '\b'}]"
        rich_print(init_info_str + "[/bold]")
        env.init()
        rich_print(f"[green]Sandbox {sandbox_name} initialized successfully.[/green]")

    return env
