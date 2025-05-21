import click
from ..config import load_config
from ..utils.setup_sandbox import setup_sandbox


@click.command("init")
@click.option("--branch", "-b", help="Branch name (e.g., Sisyphus). Overrides config.")
@click.option("--arch", "-a", help="Architecture (e.g., x86_64). Overrides config.")
@click.option("--task", "-t", type=int, help="Attach task repository by ID.")
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize the sandbox before building."
)
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> or config."
)
@click.help_option("--help", "-h")
def init_cmd(branch, arch, task, reinit, sandbox):
    """Initialize a new sandbox environment."""
    config = load_config()
    setup_sandbox(sandbox, branch, arch, reinit, config, task_id=task)
