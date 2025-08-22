import os
import re
import tempfile

import requests
import typer
from bs4 import BeautifulSoup

from altbuilder.adapters.hasher import HasherAdapter
from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.build_manager import BuildManager
from altbuilder.core.environment import Environment
from altbuilder.utils import colorize, get_spec_metadata, init_logger, logger


def get_local_repo_dir(mirror, branch: str) -> str:
    """Return local repo directory path for given mirror and branch."""
    if not mirror.startswith("file:"):
        raise ValueError("Invalid local mirror URL: must start with 'file:'")
    local_path = mirror[5:]
    if branch.lower() == "sisyphus":
        return os.path.join(local_path, branch.lower(), "last", "files", "SRPMS")
    return None


def find_src_rpm_local(repo_dir: str, package_name: str) -> str | None:
    """Search local SRPMS dir for latest matching src.rpm file by exact name."""
    try:
        files = os.listdir(repo_dir)
    except (FileNotFoundError, PermissionError) as e:
        raise ValueError(f"Repository directory inaccessible: {e}")

    pattern = re.compile(
        rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]+-[0-9a-zA-Z._%+-]+\.src\.rpm$"
    )
    matching_files = sorted([f for f in files if pattern.match(f)])
    if not matching_files:
        return None
    return os.path.join(repo_dir, matching_files[-1])


def get_remote_repo_url(mirror: str, branch: str) -> str:
    """Build remote repo SRPMS URL."""
    if not mirror.startswith("http"):
        raise ValueError("Invalid remote mirror URL: must start with 'http'")
    if branch.lower() == "sisyphus":
        return f"{mirror}/ALTLinux/{branch}/files/SRPMS/"
    return f"{mirror}/ALTLinux/{branch}/branch/SRPMS/"


def find_src_rpm_remote(
    repo_url: str, package_name: str
) -> tuple[str | None, str | None]:
    """Search remote SRPMS dir for latest matching src.rpm file by exact name."""
    try:
        response = requests.get(repo_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Failed to access remote repository {repo_url}: {e}")

    soup = BeautifulSoup(response.text, "html.parser")
    links = [link["href"] for link in soup.find_all("a", href=True)]

    pattern = re.compile(
        rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]+-[0-9a-zA-Z._%+-]+\.src\.rpm$"
    )
    matching_files = sorted([f for f in links if pattern.match(f)])
    if not matching_files:
        return None, None
    return repo_url + matching_files[-1], matching_files[-1]


def download_src_rpm(src_rpm_url: str, src_rpm_filename: str) -> str:
    """Download src.rpm to temp location, return local path."""
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, src_rpm_filename)
    try:
        with requests.get(src_rpm_url, stream=True, timeout=10) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return local_path
    except (requests.RequestException, IOError) as e:
        raise ValueError(f"Failed to download {src_rpm_url}: {e}")


app = typer.Typer(
    name="rebuild",
    help="Rebuild a package in the specified sandbox by fetching its src.rpm from a repository.",
)


@app.command()
def rebuild_cmd(
    package_name: str = typer.Argument(
        ...,
        help="Exact package name to rebuild (e.g., python3-module-hypothesis).",
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
    ),
    no_check: bool = typer.Option(
        False,
        "--no-check",
        help="Do not run package tests (rpmbuild --without=check).",
    ),
    rpmbuild_extra: str = typer.Option(
        "",
        "--rpmbuild-extra",
        help="Extra flags to pass to rpmbuild (via --rpmbuild-args).",
    ),
):
    """Rebuild a package by fetching its corresponding src.rpm and building it in sandbox."""
    # Load config
    try:
        config = load_config()
    except Exception as e:
        typer.echo(colorize(f"Failed to load configuration: {e}", color="red"))
        raise typer.Exit(code=1)

    sandbox_name = (
        sandbox or f"{config.get('branch', 'Sisyphus')}-{config.get('arch', 'x86_64')}"
    )
    try:
        sandbox_config = get_sandbox_config(sandbox_name, config)
    except Exception as e:
        typer.echo(
            colorize(
                f"Failed to get sandbox configuration for {sandbox_name}: {e}",
                color="red",
            )
        )
        raise typer.Exit(code=1)

    # Logging
    try:
        init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    except Exception as e:
        typer.echo(colorize(f"Failed to initialize logger: {e}", color="red"))
        raise typer.Exit(code=1)

    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        typer.echo(
            colorize(
                f"Sandbox {sandbox_name} does not exist. Please initialize it first.",
                color="red",
            )
        )
        raise typer.Exit(code=1)

    mirror, branch = sandbox_config.get("mirror"), sandbox_config.get("branch")
    if not mirror or not branch:
        typer.echo(
            colorize("Mirror or branch not specified in configuration.", color="red")
        )
        raise typer.Exit(code=1)

    temp_file, src_rpm_path = None, None
    try:
        if mirror.startswith("file:"):
            repo_dir = get_local_repo_dir(mirror, branch)
            src_rpm_path = find_src_rpm_local(repo_dir, package_name)
            if src_rpm_path is None:
                typer.echo(
                    colorize(
                        f"No matching src.rpm found for {package_name} in {repo_dir}",
                        color="red",
                    )
                )
                raise typer.Exit(code=1)

        elif mirror.startswith("http"):
            repo_url = get_remote_repo_url(mirror, branch)
            src_rpm_url, src_rpm_filename = find_src_rpm_remote(repo_url, package_name)
            if not src_rpm_url or not src_rpm_filename:
                typer.echo(
                    colorize(
                        f"No matching src.rpm found for {package_name} at {repo_url}",
                        color="red",
                    )
                )
                raise typer.Exit(code=1)
            temp_file = download_src_rpm(src_rpm_url, src_rpm_filename)
            src_rpm_path = temp_file
        else:
            typer.echo(colorize(f"Unsupported mirror type: {mirror}", color="red"))
            raise typer.Exit(code=1)

        # Metadata
        meta_name, version, release = get_spec_metadata(src_rpm_path, is_src_rpm=True)
        if not meta_name:
            meta_name = os.path.basename(src_rpm_path).replace(".src.rpm", "")
            version, release = "unknown", "unknown"

        logger.info(
            f"Rebuilding package: {meta_name} (Version: {version}, Release: {release}) in sandbox: {sandbox_name}"
        )
        typer.echo(
            colorize(
                f"Rebuilding package: {meta_name} (Version: {version}, Release: {release}) in sandbox: {sandbox_name}",
                bold=True,
            )
        )

        # Build log dir
        log_dir = os.path.join(
            sandbox_config["build_logs_dir"], sandbox_name, meta_name
        )
        build_number = 1
        while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
            build_number += 1
        build_log_dir = os.path.join(log_dir, f"build_{build_number}")
        os.makedirs(build_log_dir, exist_ok=True)

        hasher = HasherAdapter(base_dir=config.get("base_dir"))
        builder = BuildManager(env, hasher_adapter=hasher)
        builder.build(
            build_target=src_rpm_path,
            is_src_rpm=True,
            apt_conf=None,
            only_srpm=False,
            build_log_dir=build_log_dir,
            no_check=no_check,
            hsh_extra="",
            rpmbuild_extra=rpmbuild_extra,
            command="rebuild",
        )

        typer.echo(
            colorize(
                f"Successfully rebuilt {meta_name} (Version: {version}, Release: {release}) (sandbox: {sandbox_name}).",
                color="green",
            )
        )

    except Exception as e:
        typer.echo(colorize(f"Failed to rebuild {package_name}: {e}", color="red"))
        raise typer.Exit(code=1)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                typer.echo(
                    colorize(
                        f"Warning: Failed to remove temporary file {temp_file}: {e}",
                        color="yellow",
                    )
                )


if __name__ == "__main__":
    app()
