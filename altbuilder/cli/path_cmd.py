import glob
import os
from typing import List, Optional

import typer
from rich.console import Console

from altbuilder.config import load_config
from altbuilder.utils import logger
from altbuilder.utils.json_utils import is_json_mode, json_response
from altbuilder.utils.completion import complete_sandbox, complete_package

app = typer.Typer(
    name="path",
    help="Get paths to RPM files or directories in sandboxes.",
)


def find_rpm_files(sandbox_path: str, package_name: Optional[str], srpm: bool,
                   no_debuginfo: bool) -> List[str]:
    """Find RPM files matching the criteria."""
    found_files = []

    if srpm:
        # Search in SRPMS
        srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
        if os.path.exists(srpms_dir):
            if package_name:
                pattern = os.path.join(srpms_dir, f"{package_name}-*.src.rpm")
                found_files.extend(sorted(glob.glob(pattern)))
            else:
                pattern = os.path.join(srpms_dir, "*.src.rpm")
                found_files.extend(sorted(glob.glob(pattern)))
    else:
        # Search in arch RPMs
        arch_dirs = sorted(glob.glob(os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")))
        for arch_dir in arch_dirs:
            if package_name:
                # Check if user is looking for debuginfo package explicitly
                if package_name.endswith("-debuginfo"):
                    # User explicitly searches for debuginfo package
                    pattern = os.path.join(arch_dir, f"{package_name}-*.rpm")
                    matched = sorted(glob.glob(pattern))
                    found_files.extend(matched)
                else:
                    # Normal package search
                    pattern = os.path.join(arch_dir, f"{package_name}-*.rpm")
                    matched = sorted(glob.glob(pattern))

                    # Filter to exact package name match (exclude -tests, -devel, -debuginfo, etc.)
                    exact_matches = []
                    for rpm_path in matched:
                        basename = os.path.basename(rpm_path)
                        # Extract package name from RPM filename
                        # Format: name-version-release.arch.rpm

                        # Skip debuginfo packages by default
                        if "-debuginfo-" in basename and no_debuginfo:
                            continue

                        # Always skip debuginfo for regular package search
                        if "-debuginfo-" in basename:
                            continue

                        # Regular package: python3-module-numpy-2.3.4-alt1.x86_64.rpm
                        # Need to check if it's exact match or has suffix like -tests, -devel
                        pkg_base = basename.rsplit("-", 2)[0]  # Remove version-release
                        if pkg_base == package_name:
                            exact_matches.append(rpm_path)

                    found_files.extend(exact_matches)
            else:
                # No package name specified - get all RPMs
                pattern = os.path.join(arch_dir, "*.rpm")
                matched = sorted(glob.glob(pattern))

                # Apply no_debuginfo filter
                if no_debuginfo:
                    matched = [f for f in matched if "-debuginfo-" not in os.path.basename(f)]

                # Without package name, return all files
                found_files.extend(matched)

    return found_files


@app.command()
def path(
    ctx: typer.Context,
    package: Optional[str] = typer.Argument(
        None,
        help="Package name to search for. If not specified, returns all RPMs in the sandbox.",
        autocompletion=complete_package,
    ),
    sandbox: Optional[str] = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name.",
        autocompletion=complete_sandbox,
    ),
    srpm: bool = typer.Option(
        False,
        "--srpm",
        help="Return path to source RPM instead of binary RPM.",
    ),
    dir: bool = typer.Option(
        False,
        "--dir",
        help="Return path to RPM directory instead of specific file.",
    ),
    no_debuginfo: bool = typer.Option(
        False,
        "--no-debuginfo",
        help="Exclude debuginfo packages from results.",
    ),
):
    """Get paths to RPM files or directories in sandboxes.

    Examples:

        # Get path to a specific package RPM
        altbuilder path -s deepcool deepcool-digital-linux

        # Get path to source RPM
        altbuilder path -s deepcool deepcool-digital-linux --srpm

        # Get path to RPM directory (useful for cd command)
        altbuilder path -s deepcool --dir

        # Use in commands
        sudo apt-get install $(altbuilder path -s deepcool deepcool)
        cd $(altbuilder path -s deepcool --dir)
    """
    json_mode = is_json_mode(ctx)
    config = load_config()
    console = Console()
    environment_dir = config["environment_dir"]

    # Get sandbox: prefer local flag, then global flag, then default
    if not sandbox:
        sandbox = ctx.obj.get("sandbox")

    if not sandbox:
        # Try to use default sandbox name
        sandbox = f"{config['branch']}-{config['arch']}"

    sandbox_path = os.path.join(environment_dir, sandbox)

    if not os.path.exists(sandbox_path):
        message = f"Sandbox '{sandbox}' not found."
        logger.error(message)
        if json_mode:
            json_response(ctx, "error", message=message, code=1)
        else:
            console.print(f"[red]{message}[/red]")
            raise typer.Exit(code=1)
        return

    # If --dir is specified, return directory path
    if dir:
        if srpm:
            dir_path = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
        else:
            # Return the first arch directory found
            arch_dirs = sorted(glob.glob(os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher")))
            if arch_dirs:
                dir_path = arch_dirs[0]
            else:
                message = f"No RPM directories found in sandbox '{sandbox}'."
                logger.error(message)
                if json_mode:
                    json_response(ctx, "error", message=message, code=1)
                else:
                    console.print(f"[red]{message}[/red]")
                    raise typer.Exit(code=1)
                return

        if not os.path.exists(dir_path):
            message = f"Directory '{dir_path}' does not exist."
            logger.error(message)
            if json_mode:
                json_response(ctx, "error", message=message, code=1)
            else:
                console.print(f"[red]{message}[/red]")
                raise typer.Exit(code=1)
            return

        if json_mode:
            json_response(ctx, "success", path=dir_path)
        else:
            console.print(dir_path)
        return

    # Find RPM files
    found_files = find_rpm_files(sandbox_path, package, srpm, no_debuginfo)

    if not found_files:
        if package:
            message = f"No RPM files found for package '{package}' in sandbox '{sandbox}'."
        else:
            message = f"No RPM files found in sandbox '{sandbox}'."

        logger.error(message)
        if json_mode:
            json_response(ctx, "error", message=message, code=1)
        else:
            console.print(f"[red]{message}[/red]")
            raise typer.Exit(code=1)
        return

    if json_mode:
        if len(found_files) == 1:
            json_response(ctx, "success", path=found_files[0])
        else:
            json_response(ctx, "success", paths=found_files, count=len(found_files))
    else:
        # Print each path on a separate line
        for file_path in found_files:
            console.print(file_path)


if __name__ == "__main__":
    app()
