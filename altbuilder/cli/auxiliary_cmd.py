import os
import click
import subprocess
import shutil
from ..config import load_config, get_sandbox_config
from ..core.environment import Environment
from ..utils import init_logger, logger, colorize
from ..utils.metrics import Metrics


@click.command("copy-pyproject-deps")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.help_option("--help", "-h")
def copy_pyproject_deps(sandbox):
    """Copy pyproject_deps.json from sandbox to .gear/ directory."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    if not env.exists():
        logger.warning(f"Sandbox {sandbox_name} does not exist, initializing...")
        env.init()

    logger.info(f"Copying pyproject_deps.json from sandbox {sandbox_name} to .gear/")
    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        'cat "$(rpm --eval %pyproject_deps_config)"',
    ]
    try:
        os.makedirs(".gear", exist_ok=True)
        with open(".gear/pyproject_deps.json", "w") as f:
            subprocess.run(cmd, stdout=f, check=True)
        click.echo(colorize(f"pyproject_deps.json copied to .gear/", color="green"))
        logger.info(f"pyproject_deps.json copied to .gear/ in sandbox {sandbox_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy pyproject_deps.json: {e}")
        click.echo(colorize(f"Failed to copy pyproject_deps.json: {e}", color="red"))
        raise


@click.command("rust-update-vendor")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize sandbox if it already exists."
)
@click.argument("tag", required=False, default="")
@click.help_option("--help", "-h")
def rust_update_vendor(sandbox, reinit, tag):
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
        click.echo(
            colorize(f"Rust vendor dependencies updated successfully.", color="green")
        )
        logger.info(f"Rust vendor dependencies updated in sandbox {sandbox_name}")
    except EnvironmentError as e:
        logger.error(f"Failed to update Rust vendor dependencies: {e}")
        click.echo(
            colorize(f"Failed to update Rust vendor dependencies: {e}", color="red")
        )
        raise


@click.command("go-update-vendor")
@click.option(
    "--sandbox", "-s", help="Sandbox name. Defaults to <branch>-<arch> from config."
)
@click.option(
    "--reinit", "-r", is_flag=True, help="Reinitialize sandbox if it already exists."
)
@click.argument("tag", required=False, default="")
@click.help_option("--help", "-h")
def go_update_vendor(sandbox, reinit, tag):
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
        click.echo(
            colorize(f"Go vendor dependencies updated successfully.", color="green")
        )
        logger.info(f"Go vendor dependencies updated in sandbox {sandbox_name}")
    except EnvironmentError as e:
        logger.error(f"Failed to update Go vendor dependencies: {e}")
        click.echo(
            colorize(f"Failed to update Go vendor dependencies: {e}", color="red")
        )
        raise
