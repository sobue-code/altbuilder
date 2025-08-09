import os
import subprocess
import sys

import click


@click.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
@click.option(
    "--install",
    is_flag=True,
    help="Install the completion script to the appropriate shell configuration directory.",
)
def completion_cmd(shell, install):
    """Generate and optionally install shell completion script."""
    completion_dir = {
        "bash": os.path.expanduser("~/.local/share/bash-completion/completions"),
        "zsh": os.path.expanduser("~/.zfunc"),
        "fish": os.path.expanduser("~/.config/fish/completions"),
    }
    completion_file = {
        "bash": os.path.join(completion_dir["bash"], "altbuilder"),
        "zsh": os.path.join(completion_dir["zsh"], "_altbuilder"),
        "fish": os.path.join(completion_dir["fish"], "altbuilder.fish"),
    }

    # Generate completion script
    env = os.environ.copy()
    env["_ALTBUILDER_COMPLETE"] = f"{shell}_source"
    result = subprocess.run([sys.argv[0]], env=env, capture_output=True, text=True)

    if not install:
        # Print script to stdout
        click.echo(result.stdout)
        return

    # Install the completion script
    os.makedirs(completion_dir[shell], exist_ok=True)
    with open(completion_file[shell], "w") as f:
        f.write(result.stdout)
    click.echo(f"Completion script written to {completion_file[shell]}")

    # Provide sourcing instructions
    if shell == "bash":
        click.echo(
            "Add to ~/.bashrc:\n"
            f"source {completion_file['bash']}\n"
            "Then run: source ~/.bashrc"
        )
    elif shell == "zsh":
        click.echo(
            "Add to ~/.zshrc:\n"
            "fpath+=(~/.zfunc)\n"
            "autoload -Uz compinit\n"
            "compinit\n"
            f"Then run: source ~/.zshrc"
        )
    elif shell == "fish":
        click.echo(f"Completion loaded automatically in {completion_file['fish']}")
