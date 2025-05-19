import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger, logger
from ..utils.helpers import colorize


@click.command("init")
@click.option("--branch", help="Branch name (e.g., Sisyphus). Overrides config.")
@click.option("--arch", help="Architecture (e.g., x86_64). Overrides config.")
@click.option("--task", type=int, help="Attach task repository by ID.")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> or config."
)
@click.help_option("--help", "-h")
def init_cmd(branch, arch, task, sandbox):
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
