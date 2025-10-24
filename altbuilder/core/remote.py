import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup
from loguru import logger

from altbuilder.config import load_config
from altbuilder.exceptions import RemoteError


def parse_package_version_release(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse version and release from package filename.

    Args:
        filename (str): Package filename (e.g., 'python3-module-glpi-api-1.0.0-alt1.src.rpm').

    Returns:
        Tuple[Optional[str], Optional[str]]: Tuple of (version, release).
    """
    # Pattern to match package name, version, and release
    # This pattern captures everything after the first dash as version, and everything before .src.rpm as release
    pattern = r'^[^-]+-(.+)-([^.]+)\.src\.rpm$'
    match = re.match(pattern, filename)
    if match:
        version = match.group(1)
        release = match.group(2)

        # For packages like 'python3-module-glpi-api-0.7.0-alt1.src.rpm'
        # We need to extract just the version part (0.7.0) from the captured group
        # The captured group might contain the full package name, so we need to extract the last part
        version_parts = version.split('-')
        if len(version_parts) > 1:
            # If there are multiple dashes, take the last part as version
            version = version_parts[-1]

        return version, release
    return None, None


class RemoteRepository:
    """Handles operations with git.altlinux.org gears, srpms repositories, and ALT Linux package repositories."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize RemoteRepository with configuration.

        Args:
            config (Optional[dict]): Configuration dictionary. If None, loads default config.
        """
        self.config = config or load_config()
        # Hardcode base URLs for gears and srpms repositories
        self.gears_base_url = "https://git.altlinux.org/gears"
        self.srpms_base_url = "https://git.altlinux.org/srpms"

    def search_git_repository(self, package_name: str) -> Optional[str]:
        """Search for a package's git repository on git.altlinux.org in gears or srpms.

        Args:
            package_name (str): Name of the package (e.g., 'python3-moudle-glpi-api').

        Returns:
            Optional[str]: URL of the git repository if found, None otherwise.

        Raises:
            RemoteError: If the search fails or the git repository is unreachable.
        """
        logger.info(f"Searching for git repository: {package_name}")
        git_name = package_name
        if not git_name.startswith(("rpm/", "gears/", "srpms/")):
            git_name = f"{package_name[0]}/{package_name}"

        # Try gears first
        gears_url = f"{self.gears_base_url}/{git_name}.git"
        logger.info(f"Checking gears repository: {gears_url}")
        try:
            subprocess.run(
                ["git", "ls-remote", gears_url],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.info(f"Found git repository in gears: {gears_url}")
            return gears_url
        except subprocess.CalledProcessError:
            logger.info(f"No git repository found in gears for {package_name}")

        # Fall back to srpms
        srpms_url = f"{self.srpms_base_url}/{git_name}.git"
        logger.info(f"Checking srpms repository: {srpms_url}")
        try:
            subprocess.run(
                ["git", "ls-remote", srpms_url],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.info(f"Found git repository in srpms: {srpms_url}")
            return srpms_url
        except subprocess.CalledProcessError:
            logger.warning(
                f"No git repository found for {package_name} in gears or srpms"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to search for git repository: {e}")
            raise RemoteError(f"Failed to search for git repository: {e}")

    def check_gitalt_repository_exists(
        self, package_name: str, gitalt_dir: str = "packages"
    ) -> bool:
        """Check if a repository exists on git.alt under {gitalt_dir}/{package_name}.git.

        Args:
            package_name (str): Name of the package (e.g., 'python3-module-glpi-api').
            gitalt_dir (str): Directory on git.alt to check (e.g., 'packages' or 'private'). Defaults to 'packages'.

        Returns:
            bool: True if the repository exists, False otherwise.

        Raises:
            RemoteError: If the check fails due to SSH issues or other errors.
        """
        logger.info(
            f"Checking if repository exists on git.alt: {gitalt_dir}/{package_name}.git"
        )
        try:
            result = subprocess.run(
                ["ssh", "git.alt", "ls", gitalt_dir],
                capture_output=True,
                check=True,
                text=True,
            )
            return f"{package_name}.git" in result.stdout.split()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to check git.alt repository in {gitalt_dir}: {e}")
            raise RemoteError(
                f"Failed to check git.alt repository in {gitalt_dir}: {e}"
            )

    def clone_git_repository(
        self,
        package_name: str,
        clone: bool = False,
        gitalt_clone: bool = False,
        custom_url: Optional[str] = None,
        gitalt_dir: str = "packages",
        dest_dir: str = "./",
    ) -> Path:
        """Clone a package's git repository from git.altlinux.org or a custom URL to the destination directory or git.alt.

        Args:
            package_name (str): Name of the package (e.g., 'python3-moudle-glpi-api').
            clone (bool): If True, clone the repository locally. Defaults to False.
            gitalt_clone (bool): If True, clone the repository to git.alt. Defaults to False.
            custom_url (Optional[str]): Custom repository URL to clone from (e.g., GitHub URL). Defaults to None.
            gitalt_dir (str): Directory on git.alt to clone into (e.g., 'packages' or 'private'). Defaults to 'packages'.
            dest_dir (str): Destination directory for local cloning. Defaults to current directory.

        Returns:
            Path: Path to the cloned repository directory if cloned locally, else the package name as a Path.

        Raises:
            RemoteError: If cloning fails or the destination is not writable.
        """
        logger.info(
            f"Cloning git repository for {package_name} to {dest_dir if clone else 'git.alt'}"
        )
        git_url = custom_url if custom_url else self.search_git_repository(package_name)
        if not git_url:
            raise RemoteError(f"No repository found for {package_name}")

        # Handle git.alt cloning
        if gitalt_clone:
            try:
                # Check if the repository already exists on git.alt
                if self.check_gitalt_repository_exists(package_name, gitalt_dir):
                    logger.warning(
                        f"Repository already exists on git.alt: {gitalt_dir}/{package_name}.git, skipping clone"
                    )
                else:
                    result = subprocess.run(
                        [
                            "ssh",
                            "git.alt",
                            "clone",
                            git_url,
                            f"{gitalt_dir}/{package_name}",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    logger.info(
                        f"Repository cloned to git.alt:{gitalt_dir}/{package_name}"
                    )
            except subprocess.CalledProcessError as e:
                error_message = e.stderr or str(e)
                if "Disk quota exceeded" in error_message:
                    logger.error(
                        f"Failed to clone to git.alt: Disk quota exceeded for user"
                    )
                    raise RemoteError(
                        "Failed to clone to git.alt: Disk quota exceeded for user. Please free up space or contact the administrator."
                    )
                if (
                    f"gitery-clone: {package_name}.git: destination already exists"
                    in error_message
                ):
                    logger.warning(
                        f"Repository already exists on git.alt: {gitalt_dir}/{package_name}.git, skipping clone"
                    )
                else:
                    logger.error(f"Failed to clone to git.alt: {error_message}")
                    raise RemoteError(f"Failed to clone to git.alt: {error_message}")

        # Handle local cloning
        if clone:
            dest_path = Path(dest_dir)
            dest_path.mkdir(parents=True, exist_ok=True)
            if not os.access(dest_path, os.W_OK):
                logger.error(f"Destination directory {dest_path} is not writable")
                raise RemoteError(f"Destination directory {dest_path} is not writable")

            repo_dir = dest_path / package_name
            if repo_dir.exists():
                logger.info(
                    f"Repository directory {repo_dir} already exists, skipping local clone"
                )
            else:
                try:
                    subprocess.run(
                        ["git", "clone", git_url, str(repo_dir)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    logger.info(f"Repository cloned to {repo_dir}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to clone repository locally: {e}")
                    raise RemoteError(f"Failed to clone repository locally: {e}")

            # If gitalt_clone is set, add git.alt as a remote alongside origin
            if gitalt_clone:
                try:
                    git_alt_remote = f"git.alt:{gitalt_dir}/{package_name}"
                    # Check if the remote already exists
                    result = subprocess.run(
                        ["git", "-C", str(repo_dir), "remote"],
                        capture_output=True,
                        text=True,
                    )
                    if "git.alt" in result.stdout.split():
                        logger.info(
                            f"Remote git.alt already exists in {repo_dir}, skipping remote addition"
                        )
                    else:
                        subprocess.run(
                            [
                                "git",
                                "-C",
                                str(repo_dir),
                                "remote",
                                "add",
                                "git.alt",
                                git_alt_remote,
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        logger.info(f"Added git.alt remote: {git_alt_remote}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to add git.alt remote: {e}")
                    raise RemoteError(f"Failed to add git.alt remote: {e}")

            return repo_dir

        # If only gitalt_clone is set, return package_name as Path for consistency
        return Path(package_name)

    def get_package_repo_url(self, mirror: str, branch: str) -> str:
        """Build repository URL for SRPMS packages based on mirror and branch.

        Args:
            mirror (str): Repository mirror URL (e.g., 'http://mirror.altlinux.org' or 'file:/path/to/repo').
            branch (str): Branch name (e.g., 'Sisyphus').

        Returns:
            str: URL or local path to the SRPMS repository.

        Raises:
            RemoteError: If the mirror URL is invalid or unsupported.
        """
        logger.info(f"Building repository URL for branch {branch} with mirror {mirror}")
        branch_lower = branch.lower()

        if mirror.startswith("file:"):
            local_path = mirror[5:]
            return os.path.join(local_path, branch_lower, "last", "files", "SRPMS")
        elif mirror.startswith("http"):
            if branch_lower == "sisyphus":
                return f"{mirror}/ALTLinux/{branch}/files/SRPMS/"
            return f"{mirror}/ALTLinux/{branch}/branch/files/SRPMS/"
        else:
            raise RemoteError(f"Invalid mirror type: {mirror}")

    def find_src_rpm(
        self, package_name: str, mirror: str, branch: str, version: Optional[str] = None, release: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Search for a src.rpm file for a package in the specified repository.

        Args:
            package_name (str): Name of the package (e.g., 'python3-module-glpi-api').
            mirror (str): Repository mirror URL (e.g., 'http://mirror.altlinux.org' or 'file:/path/to/repo').
            branch (str): Branch name (e.g., 'Sisyphus').
            version (Optional[str]): Specific version to search for. If None, finds the latest.
            release (Optional[str]): Specific release to search for. If None, finds the latest.

        Returns:
            Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]: Tuple of
            (src_rpm_url_or_path, src_rpm_filename, found_version, found_release).
            Returns (None, None, None, None) if no matching src.rpm is found.

        Raises:
            RemoteError: If the repository is inaccessible or the search fails.
        """
        search_msg = f"Searching for src.rpm for {package_name} in {mirror} (branch: {branch})"
        if version or release:
            search_msg += f" (version: {version or 'any'}, release: {release or 'any'})"
        logger.info(search_msg)

        repo_url = self.get_package_repo_url(mirror, branch)

        pattern = re.compile(
            rf"^{re.escape(package_name)}-[0-9][0-9a-zA-Z._%+-]*-[0-9a-zA-Z._%+-]+\.src\.rpm$"
        )

        if mirror.startswith("file:"):
            local_repo_path = repo_url
            try:
                files = os.listdir(local_repo_path)
                matching_files = sorted([f for f in files if pattern.match(f)])
                if not matching_files:
                    logger.warning(
                        f"No src.rpm found for {package_name} in {local_repo_path}"
                    )
                    return None, None, None, None

                # Filter by version and release if specified
                filtered_files = []
                for filename in matching_files:
                    file_version, file_release = parse_package_version_release(filename)
                    if file_version and file_release:
                        version_match = version is None or file_version == version
                        release_match = release is None or file_release == release
                        if version_match and release_match:
                            filtered_files.append((filename, file_version, file_release))

                if not filtered_files:
                    # Return the latest file with its version/release for error reporting
                    latest_file = matching_files[-1]
                    latest_version, latest_release = parse_package_version_release(latest_file)
                    return (
                        os.path.join(local_repo_path, latest_file),
                        latest_file,
                        latest_version,
                        latest_release,
                    )

                # Return the latest matching file
                latest_match = filtered_files[-1]
                return (
                    os.path.join(local_repo_path, latest_match[0]),
                    latest_match[0],
                    latest_match[1],
                    latest_match[2],
                )
            except (FileNotFoundError, PermissionError) as e:
                logger.error(f"Failed to access local repository {local_repo_path}: {e}")
                raise RemoteError(f"Failed to access local repository {local_repo_path}: {e}")

        try:
            response = requests.get(repo_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = [link["href"] for link in soup.find_all("a", href=True)]
            matching_files = sorted([f for f in links if pattern.match(f)])
            if not matching_files:
                logger.warning(f"No src.rpm found for {package_name} at {repo_url}")
                return None, None, None, None

            # Filter by version and release if specified
            filtered_files = []
            for filename in matching_files:
                file_version, file_release = parse_package_version_release(filename)
                if file_version and file_release:
                    version_match = version is None or file_version == version
                    release_match = release is None or file_release == release
                    if version_match and release_match:
                        filtered_files.append((filename, file_version, file_release))

            if not filtered_files:
                # Return the latest file with its version/release for error reporting
                latest_file = matching_files[-1]
                latest_version, latest_release = parse_package_version_release(latest_file)
                return (
                    repo_url + latest_file,
                    latest_file,
                    latest_version,
                    latest_release,
                )

            # Return the latest matching file
            latest_match = filtered_files[-1]
            return (
                repo_url + latest_match[0],
                latest_match[0],
                latest_match[1],
                latest_match[2],
            )
        except requests.RequestException as e:
            logger.error(f"Failed to access remote repository {repo_url}: {e}")
            raise RemoteError(f"Failed to access remote repository {repo_url}: {e}")

    def download_src_rpm(self, src_rpm_url: str, src_rpm_filename: str) -> str:
        """Download src.rpm to a temporary location and return its local path.

        Args:
            src_rpm_url (str): URL of the src.rpm file to download.
            src_rpm_filename (str): Filename of the src.rpm.

        Returns:
            str: Local path to the downloaded src.rpm file.

        Raises:
            RemoteError: If the download fails.
        """
        logger.info(f"Downloading src.rpm from {src_rpm_url}")
        temp_dir = tempfile.mkdtemp()
        local_path = os.path.join(temp_dir, src_rpm_filename)
        try:
            with requests.get(src_rpm_url, stream=True, timeout=10) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            logger.info(f"Downloaded src.rpm to {local_path}")
            return local_path
        except (requests.RequestException, IOError) as e:
            logger.error(f"Failed to download {src_rpm_url}: {e}")
            raise RemoteError(f"Failed to download {src_rpm_url}: {e}")
