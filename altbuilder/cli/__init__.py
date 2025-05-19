import click
from .init_cmd import init_cmd
from .build_cmd import build_cmd
from .list_cmd import list_cmd
from .shell_cmd import shell_cmd
from .clean_cmd import clean_cmd
from .config_cmd import config_cmd
from ..config import load_config
from ..utils.logger import init_logger, logger


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


# Register commands
cli.add_command(init_cmd)
cli.add_command(build_cmd)
cli.add_command(list_cmd)
cli.add_command(shell_cmd)
cli.add_command(clean_cmd)
cli.add_command(config_cmd)


if __name__ == "__main__":
    cli()
