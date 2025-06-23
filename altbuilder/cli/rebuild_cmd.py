import os
import re
import requests
from bs4 import BeautifulSoup
import tempfile
import click
from altbuilder.config import load_config, get_sandbox_config
from altbuilder.core.environment import Environment
from altbuilder.adapters.hasher import HasherAdapter
from altbuilder.utils import init_logger, colorize, logger


def get_local_repo_dir(mirror, branch):
    """
    Constructs the local repository directory path based on the mirror and branch.

    Args:
        mirror (str): The mirror URL (e.g., 'file:/mnt/repo').
        branch (str): The branch name (e.g., 'Sisyphus').

    Returns:
        str: The path to the SRPMS directory.

    Raises:
        ValueError: If the mirror URL is not a valid local file path.
    """
    if not mirror.startswith("file:"):
        raise ValueError("Invalid local mirror URL: must start with 'file:'")
    local_path = mirror[5:]  # Remove 'file:' prefix
    if branch.lower() == "sisyphus":
        return os.path.join(local_path, branch.lower(), "last", "files", "SRPMS")
    else:
        return None


def find_src_rpm_local(repo_dir, package_name):
    """
    Searches the local repository directory for the latest matching src.rpm file with exact name.

    Args:
        repo_dir (str): The local SRPMS directory path.
        package_name (str): The exact package name to search for (e.g., 'python3-module-hypothesis').

    Returns:
        str or None: The full path to the latest matching src.rpm file, or None if not found.

    Raises:
        ValueError: If the repository directory is inaccessible.
    """
    try:
        files = os.listdir(repo_dir)
    except FileNotFoundError:
        raise ValueError(f"Repository directory not found or inaccessible: {repo_dir}")
    except PermissionError:
        raise ValueError(
            f"Permission denied accessing repository directory: {repo_dir}"
        )

    # Pattern for exact match: package_name-<version>-<release>.src.rpm
    pattern = re.compile(
        rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]+-[0-9a-zA-Z._%+-]+\.src\.rpm$"
    )
    matching_files = [f for f in files if pattern.match(f)]

    if not matching_files:
        return None

    matching_files.sort()  # Sort to get the highest version last
    latest_file = matching_files[-1]
    return os.path.join(repo_dir, latest_file)


def get_remote_repo_url(mirror, branch):
    """
    Constructs the remote repository URL based on the mirror and branch.

    Args:
        mirror (str): The mirror URL (e.g., 'http://ftp.altlinux.org/pub/distributions').
        branch (str): The branch name (e.g., 'Sisyphus').

    Returns:
        str: The URL to the SRPMS directory.

    Raises:
        ValueError: If the mirror URL is not a valid HTTP URL.
    """
    if not mirror.startswith("http"):
        raise ValueError("Invalid remote mirror URL: must start with 'http'")
    if branch.lower() == "sisyphus":
        return f"{mirror}/ALTLinux/{branch}/files/SRPMS/"
    else:
        return f"{mirror}/ALTLinux/{branch}/branch/SRPMS/"


def find_src_rpm_remote(repo_url, package_name):
    """
    Searches the remote repository for the latest matching src.rpm file with exact name.

    Args:
        repo_url (str): The URL to the SRPMS directory.
        package_name (str): The exact package name to search for (e.g., 'python3-module-hypothesis').

    Returns:
        tuple: (src_rpm_url, src_rpm_filename) or (None, None) if not found.

    Raises:
        ValueError: If the repository cannot be accessed.
    """
    try:
        response = requests.get(repo_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Failed to access remote repository {repo_url}: {e}")

    soup = BeautifulSoup(response.text, "html.parser")
    links = soup.find_all("a", href=True)

    # Pattern for exact match: package_name-<version>-<release>.src.rpm
    pattern = re.compile(
        rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]+-[0-9a-zA-Z._%+-]+\.src\.rpm$"
    )
    matching_files = [link["href"] for link in links if pattern.match(link["href"])]

    if not matching_files:
        return None, None

    matching_files.sort()  # Sort to get the highest version last
    latest_file = matching_files[-1]
    src_rpm_url = repo_url + latest_file
    return src_rpm_url, latest_file


def download_src_rpm(src_rpm_url, src_rpm_filename):
    """
    Downloads the src.rpm file from the remote repository to a temporary location.

    Args:
        src_rpm_url (str): The full URL to the src.rpm file.
        src_rpm_filename (str): The name of the src.rpm file.

    Returns:
        str: The local path to the downloaded file.

    Raises:
        ValueError: If the download fails.
    """
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
    except requests.RequestException as e:
        raise ValueError(f"Failed to download {src_rpm_url}: {e}")
    except IOError as e:
        raise ValueError(f"Failed to write downloaded file {local_path}: {e}")


@click.command("rebuild")
@click.option(
    "--sandbox",
    "-s",
    help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
)
@click.argument("package_name")
@click.help_option("--help", "-h")
def rebuild_cmd(sandbox, package_name):
    """
    Rebuild a package in the specified sandbox by providing an exact package name.
    Fetches the corresponding src.rpm from the repository specified by the mirror,
    which can be local (file:/mnt/repo) or remote (http://ftp.altlinux.org/...).

    Args:
        sandbox (str): Optional sandbox name; defaults to branch-arch if not provided.
        package_name (str): Exact name of the package to rebuild (e.g., 'python3-module-hypothesis').
    """
    # Load the global configuration
    try:
        config = load_config()
    except Exception as e:
        click.echo(colorize(f"Failed to load configuration: {e}", color="red"))
        return

    # Determine the sandbox name, defaulting to <branch>-<arch> if not specified
    sandbox_name = (
        sandbox or f"{config.get('branch', 'Sisyphus')}-{config.get('arch', 'x86_64')}"
    )

    # Get sandbox-specific configuration
    try:
        sandbox_config = get_sandbox_config(sandbox_name, config)
    except Exception as e:
        click.echo(
            colorize(
                f"Failed to get sandbox configuration for {sandbox_name}: {e}",
                color="red",
            )
        )
        return

    # Initialize the logger for the sandbox
    try:
        init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    except Exception as e:
        click.echo(colorize(f"Failed to initialize logger: {e}", color="red"))
        return

    # Create Environment object and verify sandbox existence
    env = Environment(sandbox_name, sandbox_config)
    if not env.exists():
        click.echo(
            colorize(
                f"Sandbox {sandbox_name} does not exist. Please initialize it first.",
                color="red",
            )
        )
        return

    # Extract mirror and branch from sandbox configuration
    mirror = sandbox_config.get("mirror")
    branch = sandbox_config.get("branch")
    if not mirror or not branch:
        click.echo(
            colorize("Mirror or branch not specified in configuration.", color="red")
        )
        return

    # Variable to track temporary file for cleanup
    temp_file = None
    src_rpm_path = None
    full_package_name = None

    try:
        if mirror.startswith("file:"):
            # Handle local mirror
            repo_dir = get_local_repo_dir(mirror, branch)
            src_rpm_path = find_src_rpm_local(repo_dir, package_name)
            if src_rpm_path is None:
                click.echo(
                    colorize(
                        f"No matching src.rpm found for {package_name} in {repo_dir}",
                        color="red",
                    )
                )
                return
            full_package_name = os.path.basename(src_rpm_path)

        elif mirror.startswith("http"):
            # Handle remote mirror
            repo_url = get_remote_repo_url(mirror, branch)
            src_rpm_url, src_rpm_filename = find_src_rpm_remote(repo_url, package_name)
            if src_rpm_url is None or src_rpm_filename is None:
                click.echo(
                    colorize(
                        f"No matching src.rpm found for {package_name} at {repo_url}",
                        color="red",
                    )
                )
                return
            temp_file = download_src_rpm(src_rpm_url, src_rpm_filename)
            src_rpm_path = temp_file
            full_package_name = src_rpm_filename

        else:
            click.echo(
                colorize(
                    f"Unsupported mirror type: {mirror}. Must be 'file:' or 'http'.",
                    color="red",
                )
            )
            return

        logger.info(
            f"Rebuilding package: {full_package_name} in sandbox: {sandbox_name}"
        )
        click.echo(
            colorize(
                f"Rebuilding package: {full_package_name} in sandbox: {sandbox_name}",
                color="cyan",
            )
        )

        # Set up build log directory and file
        log_dir = os.path.join(
            sandbox_config["build_logs_dir"], sandbox_name, package_name
        )
        build_number = 1
        while os.path.exists(os.path.join(log_dir, f"build_{build_number}")):
            build_number += 1
        build_log_dir = os.path.join(log_dir, f"build_{build_number}")
        os.makedirs(build_log_dir, exist_ok=True)
        build_log = os.path.join(build_log_dir, "build.log")

        # Initialize HasherAdapter for building
        hasher = HasherAdapter(base_dir=config.get("base_dir"))

        # Perform the rebuild
        hasher.build_from_srpm(
            src_rpm=src_rpm_path,
            workdir=env.hasher_dir,
            apt_config=env.apt_conf,
            arch=env.config["arch"],
            log_file=build_log,
        )
        click.echo(
            colorize(
                f"Successfully rebuilt {full_package_name} (sandbox: {sandbox_name}).",
                color="green",
            )
        )

    except ValueError as e:
        click.echo(colorize(str(e), color="red"))
    except Exception as e:
        click.echo(
            colorize(
                f"Failed to rebuild {full_package_name} (sandbox: {sandbox_name}).",
                color="red",
            )
        )
    finally:
        # Clean up temporary file if it was created
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                click.echo(
                    colorize(
                        f"Warning: Failed to remove temporary file {temp_file}: {e}",
                        color="yellow",
                    )
                )
