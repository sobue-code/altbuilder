import os
import subprocess

import typer

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import colorize, init_logger, logger
from altbuilder.utils.metrics import Metrics

app = typer.Typer(
    name="rust-update-vendor",
    help="Update Rust vendor dependencies, optionally using a specific tag.",
)


@app.command()
def rust_update_vendor(
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
    """Update Rust vendor dependencies, optionally using a specific tag."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating Rust vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
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
    env.install(["rust-cargo", "git"])

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

    tag_cmd = f"git switch -c alt_vendor_rust '{tag}';" if tag else ""
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
        rm -rf package_rust;
        git clone '{upstream_url}' package_rust;
        cd package_rust;
        {tag_cmd}
        cargo vendor;
        """,
    ]
    metrics = Metrics(base_dir=config["base_dir"])
    with metrics.track_command(command=" ".join(cmd), sandbox_name=sandbox_name):
        subprocess.run(cmd, env=env_vars, check=True)

    # Copy vendor from sandbox to host using copy_from
    try:
        env.copy_from("/usr/src/package_rust/vendor", "./vendor")
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

        # Проверяем, есть ли staged изменения
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )

        if diff_result.returncode == 0:
            typer.echo(
                colorize(
                    "Rust vendor dependencies are already up to date. Nothing to commit.",
                    color="yellow",
                )
            )
            logger.info("Rust vendor dependencies up to date, no commit created.")
        else:
            commit_message = (
                "Update Rust dependencies"
                if vendor_tracked
                else "Vendoring Rust dependencies"
            )
            subprocess.run(["git", "commit", "-m", commit_message], check=True)

            typer.echo(
                colorize(
                    f"""Rust vendor dependencies updated and committed successfully.
Don't forget to add the following line to your .gear/rules file:

tar: vendor name=vendor

And this to your .spec:

SourceX: vendor.tar

%setup -a X
""",
                    color="green",
                )
            )
            logger.info(
                f"Rust vendor dependencies updated and committed in sandbox {sandbox_name}"
            )
    except EnvironmentError as e:
        logger.error(f"Failed to update Rust vendor dependencies: {e}")
        typer.echo(
            colorize(f"Failed to update Rust vendor dependencies: {e}", color="red")
        )
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit Rust vendor dependencies: {e}")
        typer.echo(
            colorize(f"Failed to commit Rust vendor dependencies: {e}", color="red")
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
