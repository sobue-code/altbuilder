import click
from rich import print as rich_print
from ..config import get_sandbox_config
from ..core.environment import Environment
from .logger import init_logger, logger
from .get_sandbox_info import get_sandbox_info
from .check_task_info import fetch_task_info


def derive_sandbox_name(branch, arch, task_id=None):
    """Build a sandbox name from branch, architecture, and optional task ID."""

    branch_part = (branch or "").strip()
    arch_part = (arch or "").strip()
    if not branch_part or not arch_part:
        raise click.ClickException(
            "Cannot derive sandbox name without both branch and architecture."
        )

    base_name = f"{branch_part}-{arch_part}"
    if task_id:
        return f"{base_name}-{task_id}"
    return base_name


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
    branch_override = branch is not None
    arch_override = arch is not None
    resolved_branch = branch.strip() if branch else None
    resolved_arch = arch.strip() if arch else None
    resolved_task_id = task_id
    task_info = None

    if task_id:
        if branch_override:
            raise click.ClickException(
                "Cannot use --branch together with --task. The branch is determined from the task info in RDB."
            )
        task_info = fetch_task_info(task_id, config["rdb_url"])
        if not task_info:
            raise click.ClickException(
                f"Failed to fetch task info for task {task_id} from {config['rdb_url']}."
            )
        task_branch = (task_info.get("branch") or "").strip()
        if not task_branch:
            raise click.ClickException(
                f"Task {task_id} does not provide branch information in RDB."
            )
        resolved_branch = task_branch
        branch_override = True

    sandbox_name = sandbox.strip() if sandbox else None
    existing_info = get_sandbox_info(sandbox_name, config) if sandbox_name else None

    if resolved_branch is None:
        resolved_branch = (
            existing_info.branch if existing_info else config["branch"]
        )
    if resolved_arch is None:
        resolved_arch = existing_info.arch if existing_info else config["arch"]

    if not sandbox_name:
        sandbox_name = derive_sandbox_name(
            resolved_branch, resolved_arch, resolved_task_id
        )
        existing_info = get_sandbox_info(sandbox_name, config)
        if existing_info:
            if not branch_override and resolved_task_id is None:
                resolved_branch = existing_info.branch
            if not arch_override:
                resolved_arch = existing_info.arch
            if resolved_task_id is None:
                resolved_task_id = existing_info.task_id
    elif existing_info and resolved_task_id is None:
        resolved_task_id = existing_info.task_id

    logger.info(f"Resolved sandbox name: {sandbox_name}")
    logger.info(f"Resolved task ID: {resolved_task_id}")

    if not resolved_branch or not resolved_arch:
        raise click.ClickException("--branch and --arch are required for initialization.")

    if resolved_task_id:
        if not task_info or resolved_task_id != task_id:
            task_info = fetch_task_info(resolved_task_id, config["rdb_url"])
        if not task_info:
            raise click.ClickException(
                f"Failed to fetch task info for task {resolved_task_id} from {config['rdb_url']}."
            )
        task_branch = (task_info.get("branch") or "").strip()
        if not task_branch:
            raise click.ClickException(
                f"Task {resolved_task_id} does not provide branch information in RDB."
            )
        logger.debug(
            f"Task {resolved_task_id} branch: {task_branch.lower()}, expected branch: {resolved_branch.lower()}"
        )
        if task_branch.lower() != resolved_branch.lower():
            rich_print(
                f"[yellow]Warning: Task {resolved_task_id} branch does not match sandbox branch {resolved_branch}.[/yellow]"
            )
            return None

    sandbox_config = get_sandbox_config(
        sandbox_name, config, branch=resolved_branch, arch=resolved_arch
    )
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=resolved_task_id)

    existing_task_id = existing_info.task_id if existing_info else None
    task_mismatch = existing_info and existing_task_id != resolved_task_id
    if task_mismatch and resolved_task_id is None:
        task_mismatch = existing_task_id is not None

    if resolved_task_id is None:
        target_description = "no task"
    else:
        target_description = f"task {resolved_task_id}"
    if existing_task_id is None:
        current_description = "no task"
    else:
        current_description = f"task {existing_task_id}"

    details_suffix = f", {resolved_task_id}" if resolved_task_id is not None else ""
    details = f"{resolved_branch}-{resolved_arch}{details_suffix}"

    # Handle sandbox initialization or reinitialization
    if env.exists():
        effective_reinit = reinit or task_mismatch
        if effective_reinit:
            if task_mismatch and not reinit:
                rich_print(
                    f"[yellow]Sandbox {sandbox_name} is associated with {current_description}. "
                    f"Reinitializing for {target_description}.[/yellow]"
                )
            rich_print(
                f"[bold]Reinitializing sandbox: {sandbox_name} [{details}][/bold]"
            )
            env.clean()
            env.init()
            rich_print(f"[green]Sandbox {sandbox_name} reinitialized successfully.[/green]")
        else:
            rich_print(f"[yellow]Sandbox {sandbox_name} already exists.[/yellow]")
    else:
        rich_print(f"[bold]Initializing sandbox: {sandbox_name} [{details}][/bold]")
        env.init()
        rich_print(f"[green]Sandbox {sandbox_name} initialized successfully.[/green]")

    return env
