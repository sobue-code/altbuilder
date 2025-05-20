import click
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils.logger import init_logger, logger
from ..utils.helpers import colorize


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
    default_sandbox = f"{branch or config['branch']}-{arch or config['arch']}"
    sandbox_name = sandbox or default_sandbox
    if task:
        sandbox_name += f"-{task}"
    sandbox_config = get_sandbox_config(sandbox_name, config, branch, arch)
    init_logger(sandbox_name, config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config, task_id=task)
    if env.exists():
        click.echo(colorize(f"Sandbox {sandbox_name} already exists.", color="yellow"))
        if reinit:
            click.echo(colorize(f"Reinitializing sandbox: {sandbox_name}", bold=True))
            env.clean()
            env.init()
            click.echo(
                colorize(
                    f"Sandbox {sandbox_name} reinitialized successfully.", color="green"
                )
            )
        return
    click.echo(colorize(f"Initializing sandbox: {sandbox_name}", bold=True))
    env.init()
    click.echo(
        colorize(f"Sandbox {sandbox_name} initialized successfully.", color="green")
    )
