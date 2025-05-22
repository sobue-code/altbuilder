import click
import os
import shutil
from ..config import load_config
from ..utils import init_logger, colorize, open_with_file_manager, logger


@click.command("logs")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--file-manager", "-fm", help="Specify file manager (e.g., mc or ranger)."
)
@click.option(
    "--clean",
    is_flag=True,
    help="Remove logs for the specified sandbox or all logs if no sandbox is specified.",
)
@click.help_option("--help", "-h")
def logs_cmd(sandbox, file_manager, clean):
    """Open the log directory for all sandboxes or a specific sandbox in a file manager, or clean logs."""
    config = load_config()
    init_logger(config=config)

    # Determine the log directory
    log_dir = config["build_logs_dir"]
    if sandbox:
        log_dir = os.path.join(log_dir, sandbox)

    # Handle --clean option
    if clean:
        if not os.path.exists(log_dir):
            click.echo(
                colorize(f"Log directory {log_dir} does not exist.", color="yellow")
            )
            logger.info(f"No logs found at {log_dir}")
            return
        try:
            shutil.rmtree(log_dir, ignore_errors=True)
            click.echo(
                colorize(f"Logs at {log_dir} removed successfully.", color="green")
            )
            logger.info(f"Removed logs at {log_dir}")
        except OSError as e:
            click.echo(colorize(f"Error removing logs at {log_dir}: {e}", color="red"))
            logger.error(f"Failed to remove logs at {log_dir}: {e}")
        return

    # Handle log viewing (default behavior)
    if not os.path.exists(log_dir):
        click.echo(colorize(f"Log directory {log_dir} does not exist.", color="red"))
        logger.info(f"No logs found at {log_dir}")
        return

    # Open the log directory in the file manager
    open_with_file_manager(log_dir, file_manager)
    click.echo(
        colorize(f"Opened log directory {log_dir} in file manager.", color="green")
    )
    logger.info(f"Opened log directory {log_dir} in file manager")
