import os
import platform
import subprocess
import shutil
from .logger import logger, cmd_logger


def get_host_arch():
    return platform.machine()


def run_logged_command(
    cmd, check=True, real_time=True, log_file=None, quiet=False, **kwargs
):
    """
    Run a command, log its execution, and capture output.
    With real_time=True, the output is displayed in real-time.
    With quiet=True, suppresses logging of individual output lines to DEBUG.
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
                print(line)  # Always print to console

                # Only log to DEBUG if not in quiet mode
                if not quiet:
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
            if result.stdout and not quiet:
                logger.debug(f"Command output: {result.stdout.strip()}")
            if result.stderr and not quiet:
                logger.debug(f"Command stderr: {result.stderr.strip()}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}: {e.stderr}")
            raise


def open_with_file_manager(path, file_manager=None):
    # Use MC, ranger, or default to MC if not specified and available
    cmd = []
    if not file_manager:
        file_manager = os.environ.get("ALTBUILDER_FILE_MANAGER")
        if not file_manager or not shutil.which(file_manager):
            file_manager = shutil.which("mc")
    if not file_manager:
        # Try to auto-detect
        if shutil.which("mc"):
            file_manager = "mc"
        else:
            file_manager = None

    if not file_manager:
        click.echo(
            colorize("No file manager (mc or ranger) found in PATH.", color="red")
        )
        return

    cmd = [file_manager, path]
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        click.echo(
            colorize(f"Failed to open {path} with {file_manager}: {e}", color="red")
        )
