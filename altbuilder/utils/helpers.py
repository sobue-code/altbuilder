import subprocess
import platform
import os
import time
import sys
from .logger import logger, cmd_logger


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


def run_logged_command(cmd, check=True, real_time=True, log_file=None, **kwargs):
    """
    Run a command, log its execution, and capture output.
    With real_time=True, the output is displayed in real-time.
    """
    cmd_str = " ".join(cmd)
    logger.debug(f"Executing command: {cmd_str}")
    cmd_logger().info(f"Executing: {cmd_str}")

    # If we want real-time output and we're not redirecting stderr/stdout
    if real_time and not kwargs.get("stdout") and not kwargs.get("stderr"):
        # Setup output file if provided
        output_file = None
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            output_file = open(log_file, "w")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
            **{
                k: v for k, v in kwargs.items() if k not in ["stdout", "stderr", "text"]
            },
        )

        output_lines = []
        for line in iter(process.stdout.readline, ""):
            if line:
                line = line.rstrip()
                output_lines.append(line)
                print(line)
                cmd_logger().debug(line)
                if output_file:
                    output_file.write(f"{line}\n")
                    output_file.flush()  # Ensure writing in real-time

        process.stdout.close()
        return_code = process.wait()

        if output_file:
            output_file.close()

        output = "\n".join(output_lines)

        if check and return_code != 0:
            error_msg = f"Command failed with exit code {return_code}: {cmd_str}"
            logger.error(error_msg)
            cmd_logger().error(error_msg)
            raise subprocess.CalledProcessError(return_code, cmd, output=output)

        return subprocess.CompletedProcess(cmd, return_code, stdout=output, stderr="")
    else:
        # Fall back to original behavior for non-real-time or redirected output
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
