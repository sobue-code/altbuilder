from typing import Optional


def generate_sources_list(
    branch: str, arch: str, task_id: Optional[int], config: dict
) -> list[str]:
    mirror = config.get("mirror", "http://ftp.altlinux.org/pub/distributions")
    mirror_task = config.get("mirror_task", "http://git.altlinux.org")

    lines = []
    if mirror.startswith("file://"):
        lines.append(f"rpm {mirror}/{branch.lower()}/last {arch} classic")
        lines.append(f"rpm {mirror}/{branch.lower()}/last noarch classic")
        if arch == "x86_64":
            lines.append(f"rpm {mirror}/{branch.lower()}/last {arch}-i586 classic")
    elif branch.lower() == "sisyphus":
        lines.append(f"rpm [alt] {mirror} ALTLinux/{branch}/{arch} classic")
        lines.append(f"rpm [alt] {mirror} ALTLinux/{branch}/noarch classic")
        if arch == "x86_64":
            lines.append(f"rpm [alt] {mirror} ALTLinux/{branch}/{arch}-i586 classic")
    elif branch.startswith("p") and branch[1:].isdigit():
        lines.append(f"rpm {mirror}/ALTLinux {branch}/branch/{arch} classic")
        lines.append(f"rpm {mirror}/ALTLinux {branch}/branch/noarch classic")
        if arch == "x86_64":
            lines.append(f"rpm {mirror}/ALTLinux {branch}/branch/{arch}-i586 classic")
    else:
        raise ValueError(f"Unsupported branch name: {branch}")

    if task_id and mirror_task.startswith("file://"):
        pass
    elif task_id:
        lines.append(f"rpm {mirror_task} repo/{task_id}/{arch} task")

    return lines
