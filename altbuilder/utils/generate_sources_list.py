from typing import Optional
import os
from altbuilder.config.const import SUPPORTED_BRANCHES


def generate_sources_list(
    branch: str, arch: str, task_id: Optional[int], config: dict
) -> list[str]:
    """
    Generate sources.list entries for the given branch, architecture, and configuration.

    Args:
        branch (str): Repository branch (e.g., Sisyphus, p11).
        arch (str): Architecture (e.g., x86_64).
        task_id (Optional[int]): Task ID for task-specific repositories, if any.
        config (dict): Configuration dictionary with mirror settings.

    Returns:
        list[str]: List of repository entries for sources.list.
    """
    mirror = config.get("mirror", "http://ftp.altlinux.org/pub/distributions")
    mirror_task = config.get("mirror_task", "http://git.altlinux.org")
    lines = []

    if mirror.startswith("file:/"):
        local_mirror = mirror.replace("file:", "")
        altlinux_path = os.path.join(local_mirror, "pub", "distributions", "ALTLinux")

        # Check if we have the standard ALTLinux structure
        if os.path.exists(altlinux_path):
            # Standard structure: /pub/distributions/ALTLinux/
            if branch.lower() == "sisyphus":
                repo_path = f"{mirror}/pub/distributions/ALTLinux/{branch}"
                lines.append(f"rpm {repo_path} {arch} classic")
                lines.append(f"rpm {repo_path} noarch classic")
                if arch == "x86_64":
                    lines.append(f"rpm {repo_path} {arch}-i586 classic")
            elif branch.lower() in SUPPORTED_BRANCHES:
                # For p* branches: /pub/distributions/ALTLinux/p11/branch/
                base_path = f"{mirror}/pub/distributions/ALTLinux"
                lines.append(
                    f"rpm [{branch}] {base_path} {branch}/branch/{arch} classic gostcrypto"
                )
                if arch == "x86_64":
                    lines.append(
                        f"rpm [{branch}] {base_path} {branch}/branch/{arch}-i586 classic"
                    )
                lines.append(f"rpm [{branch}] {base_path} {branch}/branch/noarch classic")
            else:
                raise ValueError(f"Unsupported branch name: {branch}")
        else:
            # Alternative structure with symlinks (e.g., /sisyphus/last -> date-based dir)
            last_path = os.path.join(local_mirror, branch.lower(), "last")
            try:
                real_path = os.readlink(last_path)
                resolved_path = os.path.normpath(
                    os.path.join(local_mirror, branch.lower(), real_path)
                )
                repo_path = "file:" + resolved_path
            except (OSError, FileNotFoundError):
                repo_path = f"{mirror}/{branch.lower()}"

            # Add repository entries for arch and noarch
            lines.append(f"rpm {repo_path} {arch} classic")
            lines.append(f"rpm {repo_path} noarch classic")
    elif branch.lower() == "sisyphus":
        lines.append(f"rpm {mirror}/ALTLinux/{branch} {arch} classic")
        lines.append(f"rpm {mirror}/ALTLinux/{branch} noarch classic")
        if arch == "x86_64":
            lines.append(f"rpm {mirror}/ALTLinux/{branch} {arch}-i586 classic")
    elif branch.lower() in SUPPORTED_BRANCHES:
        lines.append(
            f"rpm [{branch}] {mirror}/ALTLinux {branch}/branch/{arch} classic gostcrypto"
        )
        if arch == "x86_64":
            lines.append(
                f"rpm [{branch}] {mirror}/ALTLinux {branch}/branch/{arch}-i586 classic"
            )
        lines.append(f"rpm [{branch}] {mirror}/ALTLinux {branch}/branch/noarch classic")
    else:
        raise ValueError(f"Unsupported branch name: {branch}")

    # Handle task-specific repository if task_id is provided
    if task_id and not mirror_task.startswith("file:/"):
        lines.append(f"# Task {task_id}")
        lines.append(f"rpm {mirror_task} repo/{task_id}/{arch} task")

    return lines
