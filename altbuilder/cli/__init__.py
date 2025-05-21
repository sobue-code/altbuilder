import click
from .init_cmd import init_cmd
from .build_cmd import build_cmd
from .list_cmd import list_cmd
from .shell_cmd import shell_cmd
from .clean_cmd import clean_cmd
from .config_cmd import config_cmd
from .install_cmd import install_cmd
from .run_cmd import run_cmd
from .auxiliary_cmd import copy_pyproject_deps, rust_update_vendor
from .copy_cmd import copy_group
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
cli.add_command(install_cmd)
cli.add_command(run_cmd)
cli.add_command(copy_pyproject_deps)
cli.add_command(rust_update_vendor)
cli.add_command(copy_group)


if __name__ == "__main__":
    cli()
