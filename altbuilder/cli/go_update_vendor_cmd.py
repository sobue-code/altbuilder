import os
import subprocess

import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.metrics import Metrics

app = typer.Typer(
    name="go-update-vendor",
    help="Update Go vendor dependencies, optionally using a specific tag.",
)


@app.command()
def go_update_vendor(
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
):
    """Update Go vendor dependencies, optionally using a specific tag."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating Go vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
    )
    if env.exists() and reinit:
        logger.info(f"Reinitializing sandbox {sandbox_name} due to --reinit flag")
        env.clean()
        env.init()
    elif not env.exists():
        logger.info(f"Initializing new sandbox {sandbox_name}")
        env.init()
    else:
        logger.info(f"Using existing sandbox {sandbox_name}")

    env.enable_internet()
    env.install(["golang", "git"])

    try:
        subprocess.run(["git", "rev-parse", "--verify", "upstream"], check=True)
    except subprocess.CalledProcessError:
        logger.info("Restoring upstream branch...")
        subprocess.run(["gear-remotes-restore"], check=True)

    upstream_url = (
        subprocess.check_output(["git", "config", "--get", "remote.upstream.url"])
        .decode()
        .strip()
    )
    if not upstream_url:
        raise ValueError("Upstream URL is empty.")

    tag_cmd = f"git switch -c alt_vendor_go '{tag}';" if tag else ""

    env_vars = os.environ.copy()
    env_vars["share_ipc"] = "yes"
    env_vars["share_network"] = "yes"

    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        f"""
        set -e;
        cd /usr/src;
        rm -rf package_go;
        git clone '{upstream_url}' package_go;
        cd package_go;
        {tag_cmd}
        mkdir -p /tmp/gopath;
        export GOROOT=/usr/lib/golang;
        export GOPATH=/tmp/gopath;
        mkdir -p vendor;
        go mod vendor;
        """,
    ]

    metrics = Metrics(base_dir=config["base_dir"])
    with metrics.track_command(command=" ".join(cmd), sandbox_name=sandbox_name):
        subprocess.run(cmd, env=env_vars, check=True)

    try:
        env.copy_from("/usr/src/package_go/vendor", "./vendor")
        # Check if vendor directory is already tracked in git
        vendor_tracked = False
        try:
            subprocess.run(
                ["git", "ls-files", "vendor"],
                capture_output=True,
                check=True,
                text=True,
            )
            vendor_tracked = True
        except subprocess.CalledProcessError:
            vendor_tracked = False

        # Stage the vendor directory
        subprocess.run(["git", "add", "vendor"], check=True)

        # Проверяем, есть ли изменения в индексе
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )

        if diff_result.returncode == 0:
            rich_print(
                "[yellow]Go vendor dependencies are already up to date. Nothing to commit.[/yellow]"
            )
            logger.info("Vendor dependencies up to date, no commit created.")
        else:
            commit_message = (
                "Update Go dependencies"
                if vendor_tracked
                else "Vendoring Go dependencies"
            )
            subprocess.run(["git", "commit", "-m", commit_message], check=True)

            rich_print(
                f"""[green]Go vendor dependencies updated and committed successfully.
Don't forget to add the following line to your .gear/rules:

tar: vendor name=vendor

And this to your .spec:

SourceX: vendor.tar

%setup -a X[/green]"""
            )
            logger.info(
                f"Go vendor dependencies updated and committed in sandbox {sandbox_name}"
            )
    except EnvironmentError as e:
        logger.error(f"Failed to update Go vendor dependencies: {e}")
        rich_print(f"[red]Failed to update Go vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit Go vendor dependencies: {e}")
        rich_print(f"[red]Failed to commit Go vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
