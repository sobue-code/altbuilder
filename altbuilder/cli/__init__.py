import click
from .init_cmd import init_cmd
from .build_cmd import build_cmd
from .rebuild_cmd import rebuild_cmd
from .list_cmd import list_cmd
from .shell_cmd import shell_cmd
from .clean_cmd import clean_cmd
from .config_cmd import config_cmd
from .install_cmd import install_cmd
from .run_cmd import run_cmd
from .track_cmd import track_cmd
from .stop_cmd import stop_cmd
from .copy_pyproject_deps_cmd import copy_pyproject_deps
from .rust_update_vendor_cmd import rust_update_vendor
from .go_update_vendor_cmd import go_update_vendor
from .npm_update_vendor_cmd import npm_update_vendor
from .merge_tag_cmd import merge_tag_cmd
from .logs_cmd import logs_cmd
from .copy_cmd import copy_group
from .update_submodules_cmd import update_submodules
from .rpmdiff_cmd import rpmdiff_cmd
from ..config import load_config
from ..utils.logger import init_logger, logger


class GroupedHelpGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._commands = []
        self.command_groups = [
            (
                "Sandbox Management",
                [
                    init_cmd,
                    list_cmd,
                    shell_cmd,
                    clean_cmd,
                    config_cmd,
                    install_cmd,
                    run_cmd,
                    track_cmd,
                    stop_cmd,
                    logs_cmd,
                ],
            ),
            (
                "Build packages",
                [
                    build_cmd,
                    rebuild_cmd,
                ],
            ),
            (
                "Auxiliary",
                [
                    copy_pyproject_deps,
                    rust_update_vendor,
                    go_update_vendor,
                    npm_update_vendor,
                    copy_group,
                    update_submodules,
                    merge_tag_cmd,
                ],
            ),
            ("Package Management", [rpmdiff_cmd]),
        ]

    def add_command(self, cmd, name=None):
        super().add_command(cmd, name)
        self._commands.append(cmd.name)

    def list_commands(self, ctx):
        return self._commands

    def format_commands(self, ctx, formatter):
        for group_name, commands in self.command_groups:
            with formatter.section(group_name):
                rows = []
                for cmd in commands:
                    cmd_obj = self.get_command(ctx, cmd.name)
                    if cmd_obj is None:
                        continue
                    help_text = cmd_obj.get_short_help_str()
                    rows.append((cmd.name, help_text))
                formatter.write_dl(rows)


@click.group(cls=GroupedHelpGroup)
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


cli.add_command(init_cmd)
cli.add_command(list_cmd)
cli.add_command(shell_cmd)
cli.add_command(clean_cmd)
cli.add_command(config_cmd)
cli.add_command(install_cmd)
cli.add_command(run_cmd)
cli.add_command(track_cmd)
cli.add_command(stop_cmd)
cli.add_command(logs_cmd)
cli.add_command(build_cmd)
cli.add_command(rebuild_cmd)
cli.add_command(copy_pyproject_deps)
cli.add_command(rust_update_vendor)
cli.add_command(go_update_vendor)
cli.add_command(npm_update_vendor)
cli.add_command(update_submodules)
cli.add_command(merge_tag_cmd)
cli.add_command(rpmdiff_cmd)
cli.add_command(copy_group)


if __name__ == "__main__":
    cli()
