import click
import tomli_w
from ..config import load_config


@click.command("config")
def config_cmd():
    """Print the current config."""
    config = load_config()
    # Convert config to TOML string and print
    click.echo(tomli_w.dumps(config))
