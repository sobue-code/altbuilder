import os
import platform
import subprocess
import shutil
import shlex
from rich import print as rich_print
from .logger import logger, cmd_logger
from altbuilder.exceptions import ToolError


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
            encoding="utf-8",
            errors="replace",  # Replace invalid bytes with �
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
        rich_print("[red]No file manager (mc or ranger) found in PATH.[/red]")
        return

    cmd = [file_manager, path]
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        rich_print(f"[red]Failed to open {path} with {file_manager}: {e}[/red]")


def get_spec_metadata(build_target, is_src_rpm):
    """Extract name, version, and release from a .spec file in the build_target directory or its subdirectories."""
    if is_src_rpm:
        # For src.rpm, use rpm to query metadata
        try:
            result = subprocess.run(
                [
                    "rpm",
                    "-qp",
                    "--queryformat",
                    "%{NAME} %{VERSION} %{RELEASE}",
                    build_target,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            name, version, release = result.stdout.strip().split()
            return name, version, release
        except subprocess.CalledProcessError:
            return None, None, None
    else:
        # For directory, recursively find .spec file
        spec_path = None
        search_dir = os.path.abspath(build_target)
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".spec"):
                    spec_path = os.path.join(root, file)
                    break
            if spec_path:
                break
        if spec_path:
            try:
                result = subprocess.run(
                    [
                        "rpmspec",
                        "-q",
                        "--srpm",
                        "--queryformat",
                        "%{NAME} %{VERSION} %{RELEASE}",
                        spec_path,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                name, version, release = result.stdout.strip().split()
                return name, version, release
            except subprocess.CalledProcessError:
                pass
        return None, None, None


def copy_spec_to_log_dir(build_target, is_src_rpm, build_log_dir, package_name):
    """Copy or extract the spec file to the build log directory."""
    if not is_src_rpm:
        spec_path = None
        search_dir = os.path.abspath(build_target)
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".spec"):
                    spec_path = os.path.join(root, file)
                    break
            if spec_path:
                break
        if spec_path:
            dest = os.path.join(build_log_dir, os.path.basename(spec_path))
            shutil.copy2(spec_path, dest)
            logger.info(f"Copied spec file to {dest}")
        else:
            logger.warning(f"No spec file found in {build_target}")
    else:
        try:
            result = (
                subprocess.check_output(["rpm", "-qpl", build_target])
                .decode()
                .splitlines()
            )
            spec_file = next((f for f in result if f.endswith(".spec")), None)
            if spec_file:
                cwd = os.getcwd()
                os.chdir(build_log_dir)
                abs_build_target = os.path.abspath(build_target)
                cmd = f"rpm2cpio {shlex.quote(abs_build_target)} | cpio -idmv --no-absolute-filenames {shlex.quote(spec_file)}"
                subprocess.run(cmd, shell=True, check=True)
                extracted_spec = os.path.join(build_log_dir, spec_file)
                dest = os.path.join(build_log_dir, f"{package_name}.spec")
                if os.path.basename(extracted_spec) != f"{package_name}.spec":
                    os.rename(extracted_spec, dest)
                os.chdir(cwd)
                logger.info(f"Extracted spec file to {dest}")
            else:
                logger.warning(f"No spec file found in {build_target}")
        except Exception as e:
            logger.warning(f"Failed to extract spec from {build_target}: {e}")


def is_pyproject_deps_sync_error(error: ToolError) -> bool:
    """
    Determine if the error is related to pyproject_deps.json synchronization.

    Returns True if:
    - Exit code is 4 (RPM pyproject_deps sync verification failure)
    - Error message contains telltale signs of deps sync issue

    Args:
        error: ToolError exception to check

    Returns:
        bool: True if this is a pyproject_deps sync error
    """
    # Check exit code 4 (deps sync verification failure)
    if hasattr(error, 'exit_code') and error.exit_code == 4:
        return True

    # Additional check: look for characteristic error messages
    error_msg = str(error).lower()
    deps_indicators = [
        "dependencies of source",
        "changed since last check",
        "pyproject_deps",
        "deps sync"
    ]

    # Check if at least two indicators are present (to avoid false positives)
    matches = sum(1 for indicator in deps_indicators if indicator in error_msg)
    if matches >= 2:
        return True

    return False
