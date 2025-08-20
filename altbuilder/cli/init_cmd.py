import typer

from ..config import load_config
from ..utils.setup_sandbox import setup_sandbox

app = typer.Typer(
    name="init",
    help="Initialize a new sandbox environment.",
)

@app.command()
def init_cmd(
    branch: str = typer.Option(
        None, "--branch", "-b", help="Branch name (e.g., Sisyphus). Overrides config."
    ),
    arch: str = typer.Option(
        None, "--arch", "-a", help="Architecture (e.g., x86_64). Overrides config."
    ),
    task: int = typer.Option(
        None, "--task", "-t", help="Attach task repository by ID."
    ),
    reinit: bool = typer.Option(
        False, "--reinit", "-r", help="Reinitialize the sandbox before building."
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> or config.",
    ),
):
    """Initialize a new sandbox environment."""
    config = load_config()
    setup_sandbox(sandbox, branch, arch, reinit, config, task_id=task)


if __name__ == "__main__":
    app()
