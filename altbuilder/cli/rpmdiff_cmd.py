import os
import re
import subprocess
import tempfile

import requests
import typer
from bs4 import BeautifulSoup

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.utils import colorize, init_logger, logger

app = typer.Typer(
    name="rpmdiff",
    help="Compare two RPM packages and display differences in dependencies, provides, conflicts, and file lists.",
)


def get_remote_repo_urls(mirror: str, branch: str, arch: str) -> tuple[str, str]:
    """
    Build correct remote repo RPMs URLs for the given architecture and noarch.
    Handles mirrors both with and without '/pub/distributions' suffix.
    Uses RPMS.classic for actual RPMs.
    """
    if not mirror.startswith("http"):
        raise ValueError("Invalid remote mirror URL: must start with 'http'")

    mirror = mirror.rstrip("/")

    # Normalize base path to include exactly one '/pub/distributions'
    if mirror.endswith("/pub/distributions"):
        base_root = mirror
    else:
        base_root = mirror + "/pub/distributions"

    # Sisyphus layout: .../ALTLinux/Sisyphus/<arch>/RPMS.classic/
    if branch.lower() == "sisyphus":
        base_url = f"{base_root}/ALTLinux/{branch}/"
        return (
            f"{base_url}{arch}/RPMS.classic/",
            f"{base_url}noarch/RPMS.classic/",
        )

    # Stable branches layout: .../ALTLinux/<branch>/branch/<arch>/RPMS.classic/
    base_url = f"{base_root}/ALTLinux/{branch}/branch/"
    return (
        f"{base_url}{arch}/RPMS.classic/",
        f"{base_url}noarch/RPMS.classic/",
    )


def find_rpm_remote(
    repo_urls: tuple[str, str], package_name: str
) -> tuple[str | None, str | None]:
    """
    Search remote RPM directories (arch-specific and noarch) for the latest matching .rpm by exact base name.
    Returns (full_url, filename) or (None, None) if not found.
    """
    arch_url, noarch_url = repo_urls
    for url in (arch_url, noarch_url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to access repository {url}: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        links = [link.get("href", "") for link in soup.find_all("a", href=True)]

        # Match e.g.: python3-module-glpi-api-0.7.2-alt1.noarch.rpm
        # or with release variants and disttags: name-version-release.arch.rpm
        pattern = re.compile(
            rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]*-[0-9a-zA-Z._%+-]*\..*\.rpm$"
        )
        matching_files = sorted([f for f in links if pattern.match(f)])
        if matching_files:
            return url + matching_files[-1], matching_files[-1]
    return None, None


def download_rpm(src_rpm_url: str, src_rpm_filename: str) -> str:
    """Download RPM to a temporary location and return the local path."""
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, src_rpm_filename)
    try:
        with requests.get(src_rpm_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return local_path
    except (requests.RequestException, IOError) as e:
        raise ValueError(f"Failed to download {src_rpm_url}: {e}")


def find_local_rpm(sandbox_path: str, package_name: str, arch: str) -> str | None:
    """
    Search sandbox for the latest matching RPM file by exact base name.
    Prefers binary packages from hasher repo, falls back to SRPMs.
    """
    # Binary RPMs
    rpms_dir = os.path.join(sandbox_path, "hasher", "repo", arch, "RPMS.hasher")
    if os.path.exists(rpms_dir):
        files = os.listdir(rpms_dir)
        pattern = re.compile(
            rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]*-[0-9a-zA-Z._%+-]*\..*\.rpm$"
        )
        matching_files = sorted([f for f in files if pattern.match(f)])
        if matching_files:
            return os.path.join(rpms_dir, matching_files[-1])

    # SRPM fallback
    srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
    if os.path.exists(srpms_dir):
        files = os.listdir(srpms_dir)
        pattern = re.compile(
            rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]*-[0-9a-zA-Z._%+-]*\.src\.rpm$"
        )
        matching_files = sorted([f for f in files if pattern.match(f)])
        if matching_files:
            return os.path.join(srpms_dir, matching_files[-1])

    return None


@app.command()
def rpmdiff_cmd(
    package: str = typer.Argument(
        ...,
        help="Package name to compare (e.g., python3-module-glpi-api) or path to the old RPM package.",
    ),
    new_package: str | None = typer.Argument(
        None,
        help="Path to the new RPM package (optional, used only if the first argument is a path).",
    ),
    sandbox: str | None = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name (e.g., Sisyphus-x86_64). Defaults to <branch>-<arch> from config.",
    ),
    branch: str | None = typer.Option(
        None,
        "--branch",
        "-b",
        help="Repository branch (e.g., Sisyphus, p11). Defaults to sandbox branch.",
    ),
    arch: str | None = typer.Option(
        None,
        "--arch",
        "-a",
        help="Repository architecture (e.g., x86_64, i586). Defaults to sandbox arch.",
    ),
    requires: bool = typer.Option(
        False,
        "--requires",
        help="Compare package dependencies (requires).",
    ),
    provides: bool = typer.Option(
        False,
        "--provides",
        help="Compare provided capabilities (provides).",
    ),
    conflicts: bool = typer.Option(
        False,
        "--conflicts",
        help="Compare package conflicts (conflicts).",
    ),
    files: bool = typer.Option(
        False,
        "--files",
        help="Compare file lists (files).",
    ),
):
    """
    Compare a locally built RPM package from a sandbox with the latest version from the remote repository,
    or compare two RPM packages if both paths are provided.

    Flag behavior:
    - If no comparison flags are given, all categories are compared by default.
    - If one or more flags are specified, only those selected categories are compared.
    """

    # Load config
    try:
        config = load_config()
    except Exception as e:
        typer.echo(colorize(f"Failed to load configuration: {e}", color="red"))
        raise typer.Exit(code=1)

    # Determine categories to compare
    if not any([requires, provides, conflicts, files]):
        requires = provides = conflicts = files = True

    def get_rpm_query(pkg_path: str, query: str) -> list[str]:
        """
        Extract lines from an RPM using rpm -qp QUERY.
        Validates output to ensure no malformed lines.
        """
        try:
            output = subprocess.check_output(["rpm", "-qp", pkg_path, query], text=True)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            # Log warning if any line contains unexpected characters
            for line in lines:
                if not re.match(r"^[a-zA-Z0-9/._%+-]+$", line):
                    logger.warning(
                        f"Suspicious line in RPM query output for {pkg_path}: {line}"
                    )
            return sorted(set(lines))
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to query RPM {pkg_path} with {query}: {e}")
            return []

    def compare_lists(label: str, old_list: list[str], new_list: list[str]):
        """
        Diff two lists via 'diff' and colorize output.
        Ensures consistent line endings, removes duplicates, and strips whitespace.
        Logs input for debugging if differences are detected.
        """
        # Normalize input: remove duplicates, empty lines, and strip whitespace
        old_list = sorted(set(line.strip() for line in old_list if line.strip()))
        new_list = sorted(set(line.strip() for line in new_list if line.strip()))

        # Log input lists for debugging if they differ
        if old_list != new_list:
            logger.debug(f"Diff input for {label}: old={old_list}, new={new_list}")

        with (
            tempfile.NamedTemporaryFile("w", newline="\n") as old_file,
            tempfile.NamedTemporaryFile("w", newline="\n") as new_file,
        ):
            # Write lists to temporary files with explicit newline handling
            old_file.write("\n".join(old_list) + "\n")
            new_file.write("\n".join(new_list) + "\n")
            old_file.flush()
            new_file.flush()

            # Run diff command
            result = subprocess.run(
                [
                    "diff",
                    "--unchanged-line-format=",
                    "--old-line-format=- %L",
                    "--new-line-format=+ %L",
                    old_file.name,
                    new_file.name,
                ],
                text=True,
                capture_output=True,
            )
            diff_output = result.stdout

            # Output results
            if diff_output.strip():
                typer.echo(colorize(f"@@ {label} @@", color="cyan"))
                for line in diff_output.splitlines():
                    if line.startswith("-"):
                        typer.echo(colorize(line, color="red"))
                    elif line.startswith("+"):
                        typer.echo(colorize(line, color="green"))
            else:
                typer.echo(colorize(f"@@ {label} (no changes) @@", color="cyan"))

    # Determine comparison inputs
    old_package = None
    temp_file = None

    if new_package and os.path.exists(package):
        # Two direct RPM file paths provided
        old_package = package
        local_package = new_package
    else:
        # Compare local sandbox RPM with remote repo
        package_name = package
        sandbox_name = (
            sandbox
            or f"{config.get('branch', 'Sisyphus')}-{config.get('arch', 'x86_64')}"
        )
        try:
            sandbox_config = get_sandbox_config(sandbox_name, config)
        except Exception as e:
            typer.echo(
                colorize(
                    f"Failed to get sandbox configuration {sandbox_name}: {e}", "red"
                )
            )
            raise typer.Exit(code=1)

        # Init logger
        try:
            init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
        except Exception as e:
            typer.echo(colorize(f"Failed to initialize logger: {e}", "red"))
            raise typer.Exit(code=1)

        # Find local RPM in sandbox
        sandbox_path = os.path.join(config["environment_dir"], sandbox_name)
        if not os.path.exists(sandbox_path):
            typer.echo(colorize(f"Sandbox {sandbox_name} does not exist.", "red"))
            raise typer.Exit(code=1)

        local_package = find_local_rpm(
            sandbox_path, package_name, sandbox_config["arch"]
        )
        if not local_package:
            typer.echo(
                colorize(
                    f"No matching RPM found for {package_name} in sandbox {sandbox_name}",
                    "red",
                )
            )
            raise typer.Exit(code=1)

        # Resolve remote RPM
        mirror = sandbox_config.get("mirror")
        repo_branch = branch or sandbox_config.get("branch")
        repo_arch = arch or sandbox_config.get("arch")
        if not mirror or not repo_branch:
            typer.echo(
                colorize("Mirror or branch is not specified in configuration.", "red")
            )
            raise typer.Exit(code=1)
        if mirror.startswith("file:"):
            typer.echo(
                colorize(
                    "Local mirrors are not supported for remote RPM comparison.", "red"
                )
            )
            raise typer.Exit(code=1)

        try:
            repo_urls = get_remote_repo_urls(mirror, repo_branch, repo_arch)
            rpm_url, rpm_filename = find_rpm_remote(repo_urls, package_name)
            if not rpm_url or not rpm_filename:
                typer.echo(
                    colorize(
                        f"No matching RPM found for {package_name} in {repo_urls[0]} or {repo_urls}",
                        "red",
                    )
                )
                raise typer.Exit(code=1)
            old_package = download_rpm(rpm_url, rpm_filename)
            temp_file = old_package
        except Exception as e:
            typer.echo(
                colorize(
                    f"Failed to retrieve remote RPM for {package_name}: {e}", "red"
                )
            )
            raise typer.Exit(code=1)

    # Validate both RPMs
    for pkg in (old_package, local_package):
        if not os.path.exists(pkg):
            typer.echo(colorize(f"Error: {pkg} does not exist.", "red"))
            raise typer.Exit(code=1)
        try:
            subprocess.run(
                ["rpm", "-qp", pkg],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            typer.echo(colorize(f"Error: {pkg} is not a valid RPM package.", "red"))
            raise typer.Exit(code=1)

    # Headers
    typer.echo(colorize(f"--- {os.path.basename(old_package)}", "yellow"))
    typer.echo(colorize(f"+++ {os.path.basename(local_package)}", "yellow"))

    # Build selected categories
    categories: list[tuple[str, str]] = []
    if requires:
        categories.append(("REQUIRES", "--requires"))
    if provides:
        categories.append(("PROVIDES", "--provides"))
    if conflicts:
        categories.append(("CONFLICTS", "--conflicts"))
    if files:
        categories.append(("FILE LIST", "--list"))

    # Run comparisons
    for label, query in categories:
        old_data = get_rpm_query(old_package, query)
        new_data = get_rpm_query(local_package, query)
        compare_lists(label, old_data, new_data)

    # Cleanup temporary file if needed
    if temp_file and os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except OSError as e:
            typer.echo(
                colorize(
                    f"Warning: failed to remove temporary file {temp_file}: {e}",
                    "yellow",
                )
            )


if __name__ == "__main__":
    app()
