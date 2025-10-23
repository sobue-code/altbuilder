import os
import subprocess

import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.metrics import Metrics

vendor_app = typer.Typer(
    name="vendor",
    help="Manage vendor dependencies for different languages (Rust, Go, NPM).",
)


def _update_vendor_common(
    language: str,
    packages: list,
    clone_dir: str,
    vendor_cmd: str,
    vendor_source_path: str,
    vendor_dest_path: str,
    gear_rules_hint: str,
    spec_hint: str,
    sandbox: str,
    reinit: bool,
    tag: str,
):
    """Common logic for updating vendor dependencies."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating {language} vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
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
    env.install(packages)

    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "upstream"],
            check=True,
            capture_output=True,
        )
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

    tag_cmd = f"git switch -c alt_vendor_{language.lower()} '{tag}';" if tag else ""
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
        rm -rf {clone_dir};
        git clone --no-single-branch '{upstream_url}' {clone_dir};
        cd {clone_dir};
        {tag_cmd}
        {vendor_cmd}
        """,
    ]

    metrics = Metrics(base_dir=config["base_dir"])
    with metrics.track_command(command=" ".join(cmd), sandbox_name=sandbox_name):
        subprocess.run(cmd, env=env_vars, check=True)

    try:
        env.copy_from(vendor_source_path, vendor_dest_path)

        # Check if vendor directory is already tracked in git
        vendor_tracked = False
        try:
            subprocess.run(
                ["git", "ls-files", vendor_dest_path],
                capture_output=True,
                check=True,
                text=True,
            )
            vendor_tracked = True
        except subprocess.CalledProcessError:
            vendor_tracked = False

        # Stage the vendor directory
        subprocess.run(["git", "add", vendor_dest_path], check=True)

        # Check if there are staged changes
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )

        if diff_result.returncode == 0:
            rich_print(
                f"[yellow]{language} vendor dependencies are already up to date. Nothing to commit.[/yellow]"
            )
            logger.info(f"{language} vendor dependencies up to date, no commit created.")
        else:
            commit_message = (
                f"Update {language} dependencies"
                if vendor_tracked
                else f"Vendoring {language} dependencies"
            )
            subprocess.run(["git", "commit", "-m", commit_message], check=True)

            rich_print(
                f"""[green]{language} vendor dependencies updated and committed successfully.
Don't forget to add the following line to your .gear/rules file:

{gear_rules_hint}

And this to your .spec:

{spec_hint}[/green]"""
            )
            logger.info(
                f"{language} vendor dependencies updated and committed in sandbox {sandbox_name}"
            )
    except EnvironmentError as e:
        logger.error(f"Failed to update {language} vendor dependencies: {e}")
        rich_print(f"[red]Failed to update {language} vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit {language} vendor dependencies: {e}")
        rich_print(f"[red]Failed to commit {language} vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)


@vendor_app.command("rust")
def rust(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
):
    """Update Rust vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    _update_vendor_common(
        language="Rust",
        packages=["rust-cargo", "git"],
        clone_dir="package_rust",
        vendor_cmd="cargo vendor;",
        vendor_source_path="/usr/src/package_rust/vendor",
        vendor_dest_path="./vendor",
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
    )


@vendor_app.command("go")
def go(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
):
    """Update Go vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    _update_vendor_common(
        language="Go",
        packages=["golang", "git"],
        clone_dir="package_go",
        vendor_cmd="""mkdir -p /tmp/gopath;
        export GOROOT=/usr/lib/golang;
        export GOPATH=/tmp/gopath;
        mkdir -p vendor;
        go mod vendor;""",
        vendor_source_path="/usr/src/package_go/vendor",
        vendor_dest_path="./vendor",
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
    )


@vendor_app.command("npm")
def npm(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
):
    """Update NPM vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    _update_vendor_common(
        language="NPM",
        packages=["npm", "nodejs", "git"],
        clone_dir="package_nodejs",
        vendor_cmd="""rm -rf node_modules;
        # Install dependencies using appropriate npm command
        if [ -s package-lock.json ]; then
            npm ci || npm install;
        else
            npm install;
        fi""",
        vendor_source_path="/usr/src/package_nodejs/node_modules",
        vendor_dest_path="./node_modules",
        gear_rules_hint="tar: node_modules name=node_modules",
        spec_hint=" SourceX: node_modules.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
    )


if __name__ == "__main__":
    vendor_app()
