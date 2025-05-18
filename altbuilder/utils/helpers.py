import subprocess
import platform
from .logger import logger


def get_host_arch():
    machine = platform.machine()
    if machine in ["x86_64", "amd64"]:
        return "x86_64"
    elif machine in ["i386", "i686"]:
        return "i586"
    elif machine == "arm":
        return "armh"
    elif machine == "aarch64":
        return "aarch64"
    else:
        return machine


def colorize(text, color=None, bold=False):
    colors = {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
    }
    reset = "\033[0m"
    bold_code = "\033[1m" if bold else ""
    color_code = colors.get(color, "")
    return f"{color_code}{bold_code}{text}{reset}"


def run_logged_command(cmd, check=True, **kwargs):
    """Run a command, log its execution, and capture output."""
    logger.debug(f"Executing command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, check=check, text=True, capture_output=True, **kwargs
        )
        if result.stdout:
            logger.debug(f"Command output: {result.stdout.strip()}")
        if result.stderr:
            logger.debug(f"Command stderr: {result.stderr.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with exit code {e.returncode}: {e.stderr}")
        raise
