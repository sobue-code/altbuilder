import os
import subprocess
from pathlib import Path

import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.metrics import Metrics
from altbuilder.utils.vendor_cleanup import (
    CleanupOptions,
    VendorCleaner,
    show_vendor_stats,
)

vendor_app = typer.Typer(
    name="vendor",
    help="Manage vendor dependencies for different languages (Rust, Go, NPM).",
)


def _normalize_vendor_paths(module_dir: str, dest_dir: str) -> tuple[str, str, str]:
    """
    Normalize module_dir and dest_dir paths for vendor commands.

    Args:
        module_dir: Subdirectory containing manifest file (go.mod/Cargo.toml/package.json)
        dest_dir: Destination directory for vendor output

    Returns:
        Tuple of (cd_cmd, normalized_module_dir, normalized_dest_dir):
        - cd_cmd: Shell command to change directory (empty string if not needed)
        - normalized_module_dir: Module directory path (empty string for root)
        - normalized_dest_dir: Destination directory path ("." for root)
    """
    # Normalize module_dir (remove trailing slash, handle ".")
    module_dir = module_dir.rstrip("/")
    if module_dir == ".":
        module_dir = ""

    # Normalize dest_dir
    dest_dir = dest_dir.rstrip("/")
    if dest_dir == ".":
        dest_dir = ""

    # Build cd command for shell execution
    cd_cmd = f"cd {module_dir};" if module_dir else ""

    return cd_cmd, module_dir, dest_dir if dest_dir else "."


def _update_vendor_common(
    language: str,
    packages: list,
    clone_dir: str,
    vendor_cmd: str,
    vendor_source_path: str,
    vendor_dest_path: str,
    gear_rules_hint: str,
    spec_hint: str,
    sandbox: str,
    reinit: bool,
    tag: str,
    force_commit: bool = False,
    vendor_dir_name: str = "vendor",
):
    """Common logic for updating vendor dependencies.

    Args:
        vendor_dir_name: Name of the vendor directory (e.g., "vendor" for Rust/Go, "node_modules" for NPM)
    """
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating {language} vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
    )

    # Save currently staged files to restore later (to avoid committing unrelated changes)
    staged_files = []
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        staged_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        if staged_files:
            logger.info(f"Found {len(staged_files)} staged files, will restore them after vendoring")
            rich_print(
                f"[yellow]Warning: Found {len(staged_files)} staged file(s) that will be temporarily unstaged[/yellow]"
            )
            # Unstage all files
            subprocess.run(["git", "reset", "HEAD"], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to check staged files: {e}")
        # Continue anyway, not critical

    if env.exists() and reinit:
        logger.info(f"Reinitializing sandbox {sandbox_name} due to --reinit flag")
        env.clean()
        env.init()
    elif not env.exists():
        logger.info(f"Initializing new sandbox {sandbox_name}")
        env.init()
    else:
        logger.info(f"Using existing sandbox {sandbox_name}")

    env.enable_internet()
    env.install(packages)

    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "upstream"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        logger.info("Restoring upstream branch...")
        subprocess.run(["gear-remotes-restore"], check=True)

    upstream_url = (
        subprocess.check_output(["git", "config", "--get", "remote.upstream.url"])
        .decode()
        .strip()
    )
    if not upstream_url:
        raise ValueError("Upstream URL is empty.")

    tag_cmd = f"git switch -c alt_vendor_{language.lower()} '{tag}';" if tag else ""
    env_vars = os.environ.copy()
    env_vars["share_ipc"] = "yes"
    env_vars["share_network"] = "yes"

    cmd = [
        "hsh-run",
        "--mountpoints=/proc",
        env.hasher_dir,
        "--",
        "/bin/bash",
        "-ec",
        f"""
        set -e;
        cd /usr/src;
        rm -rf {clone_dir};
        git clone --no-single-branch '{upstream_url}' {clone_dir};
        cd {clone_dir};
        {tag_cmd}
        {vendor_cmd}
        """,
    ]

    metrics = Metrics(base_dir=config["base_dir"])
    with metrics.track_command(command=" ".join(cmd), sandbox_name=sandbox_name):
        subprocess.run(cmd, env=env_vars, check=True)

    try:
        # Remove the existing local vendor directory before copying the freshly
        # generated one from the sandbox. Without this, files that disappeared
        # from the new vendor tree may stay in the package checkout and later
        # get into the source tarball, producing a mixed/stale vendor directory.
        if vendor_dest_path == ".":
            local_vendor_path = Path(vendor_dir_name)
        else:
            local_vendor_path = Path(vendor_dest_path) / vendor_dir_name

        if local_vendor_path in (Path("."), Path("/")):
            raise RuntimeError(f"Refusing to remove unsafe vendor path: {local_vendor_path}")

        if local_vendor_path.exists():
            logger.info(f"Removing existing local vendor directory: {local_vendor_path}")
            subprocess.run(["rm", "-rf", str(local_vendor_path)], check=True)

        env.copy_from(vendor_source_path, vendor_dest_path)

        # Check if vendor directory exists in the previous commit (HEAD)
        # Note: vendor_dest_path might be "." (current dir), so we need to check the actual vendor dir name
        vendor_check_path = vendor_dir_name if vendor_dest_path == "." else vendor_dest_path
        vendor_tracked = False
        try:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", "HEAD", vendor_check_path],
                capture_output=True,
                text=True,
                check=False,  # Don't fail if HEAD doesn't exist or vendor not in HEAD
            )
            # Check if there's any output (files in HEAD)
            vendor_tracked = bool(result.stdout.strip())
        except Exception:
            vendor_tracked = False

        # Stage the vendor directory (force to ignore .gitignore rules)
        # Use -f to ensure ALL vendor files are added, even if matched by .gitignore
        if vendor_dest_path == ".":
            subprocess.run(["git", "add", "-f", vendor_dir_name], check=True)
        else:
            subprocess.run(["git", "add", "-f", vendor_dest_path], check=True)

        # Check if there are staged changes
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )

        if diff_result.returncode == 0:
            rich_print(
                f"[yellow]{language} vendor dependencies are already up to date. Nothing to commit.[/yellow]"
            )
            logger.info(f"{language} vendor dependencies up to date, no commit created.")
        else:
            # Verify that ONLY vendor directory is staged
            staged_after_vendor = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip().split("\n")

            # Determine the full vendor path to check
            vendor_path_to_check = vendor_dir_name if vendor_dest_path == "." else vendor_dest_path
            # Normalize path (handle both "vendor" and "vendor/" formats)
            vendor_prefix = vendor_path_to_check.rstrip("/") + "/"

            # Filter out files that are not in the vendor directory
            non_vendor_files = [
                f for f in staged_after_vendor
                if not f.startswith(vendor_prefix) and f != vendor_path_to_check
            ]

            if non_vendor_files:
                logger.warning(f"Found {len(non_vendor_files)} non-vendor files in staging area")
                rich_print(
                    f"[red]ERROR: Non-vendor files found in staging area:[/red]"
                )
                for f in non_vendor_files[:10]:  # Show first 10
                    rich_print(f"  - {f}")
                if len(non_vendor_files) > 10:
                    rich_print(f"  ... and {len(non_vendor_files) - 10} more")
                raise RuntimeError("Unexpected files in staging area. This should not happen.")

            # Interactive commit confirmation (unless --force-commit is used)
            should_commit = force_commit
            if not force_commit:
                rich_print(f"\n[cyan]Ready to commit {language} vendor dependencies[/cyan]")
                rich_print(f"Files to commit: {len(staged_after_vendor)}")

                # Show diff stats
                diff_stat = subprocess.run(
                    ["git", "diff", "--cached", "--stat"],
                    capture_output=True,
                    text=True,
                ).stdout
                rich_print(f"\n{diff_stat}")

                # Ask for confirmation
                response = typer.prompt(
                    "\nCommit vendor dependencies? [Y/n]",
                    default="y",
                    show_default=False,
                )
                should_commit = response.lower() in ["y", "yes", ""]

            if should_commit:
                # Simple commit message
                commit_message = (
                    f"Update {language} vendor dependencies"
                    if vendor_tracked
                    else f"Add vendored {language} dependencies"
                )
                subprocess.run(["git", "commit", "-m", commit_message], check=True)

                rich_print(
                    f"""[green]{language} vendor dependencies updated and committed successfully.
Don't forget to add the following line to your .gear/rules file:

{gear_rules_hint}

And this to your .spec:

{spec_hint}[/green]"""
                )
                logger.info(
                    f"{language} vendor dependencies updated and committed in sandbox {sandbox_name}"
                )
            else:
                rich_print("[yellow]Commit cancelled by user. Vendor files remain staged.[/yellow]")
                logger.info("User cancelled commit, vendor files remain in staging area")

        # Restore previously staged files
        if staged_files:
            logger.info(f"Restoring {len(staged_files)} previously staged files")
            for file in staged_files:
                try:
                    subprocess.run(["git", "add", file], check=False, capture_output=True)
                except Exception as e:
                    logger.warning(f"Failed to restore staged file {file}: {e}")
            rich_print(f"[cyan]Restored {len(staged_files)} previously staged file(s)[/cyan]")
    except EnvironmentError as e:
        logger.error(f"Failed to update {language} vendor dependencies: {e}")
        rich_print(f"[red]Failed to update {language} vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit {language} vendor dependencies: {e}")
        rich_print(f"[red]Failed to commit {language} vendor dependencies: {e}[/red]")
        raise typer.Exit(code=1)


@vendor_app.command("rust")
def rust(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
    module_dir: str = typer.Option(
        ".",
        "--module-dir",
        "-m",
        help="Subdirectory containing Cargo.toml (for workspace members, relative to repository root).",
    ),
    dest_dir: str = typer.Option(
        ".",
        "--dest-dir",
        "-d",
        help="Destination directory for vendor (relative to repository root).",
    ),
    cleanup: bool = typer.Option(
        False,
        "--cleanup",
        "-c",
        help="Clean up vendor directory (remove binaries, Windows crates, update checksums)",
    ),
    use_filterer: bool = typer.Option(
        True,
        "--filterer/--no-filterer",
        help="Use cargo-vendor-alt for platform filtering (default: True)",
    ),
    keep_windows: bool = typer.Option(
        False,
        "--keep-windows",
        help="Keep Windows-specific crates (by default removed for Linux-only packages)",
    ),
    stats: bool = typer.Option(
        True,
        "--stats/--no-stats",
        help="Show vendor directory statistics (default: True)",
    ),
    verbose_commit: bool = typer.Option(
        False,
        "--verbose-commit",
        help="Include detailed cleanup information in commit message",
    ),
    force_commit: bool = typer.Option(
        False,
        "--force-commit",
        "-f",
        help="Skip interactive commit confirmation and commit automatically",
    ),
):
    """Update Rust vendor dependencies with optional cleanup and optimization."""
    sandbox = ctx.obj.get("sandbox")

    # Normalize paths using helper function
    cd_cmd, module_subdir, normalized_dest = _normalize_vendor_paths(module_dir, dest_dir)

    # Build vendor source path based on module_dir
    if module_subdir:
        vendor_source_path = f"/usr/src/package_rust/{module_subdir}/vendor"
    else:
        vendor_source_path = "/usr/src/package_rust/vendor"

    # Determine vendoring command based on filterer flag
    if use_filterer:
        vendor_cmd = f"{cd_cmd} cargo-vendor-alt || cargo vendor;"
        packages = ["rust-cargo", "cargo-vendor-filterer", "git"]
        rich_print(
            "[cyan]Using cargo-vendor-alt for platform-specific filtering[/cyan]"
        )
    else:
        vendor_cmd = f"{cd_cmd} cargo vendor;"
        packages = ["rust-cargo", "git"]

    # Check if this is first vendor addition (before running vendor command)
    # Check the actual destination path where vendor will be placed
    vendor_check_path = "vendor" if normalized_dest == "." else f"{normalized_dest}/vendor"
    vendor_tracked = False
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", vendor_check_path],
            capture_output=True,
            text=True,
            check=False,
        )
        vendor_tracked = bool(result.stdout.strip())
    except Exception:
        vendor_tracked = False

    _update_vendor_common(
        language="Rust",
        packages=packages,
        clone_dir="package_rust",
        vendor_cmd=vendor_cmd,
        vendor_source_path=vendor_source_path,
        vendor_dest_path=normalized_dest,
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
        force_commit=force_commit,
        vendor_dir_name="vendor",
    )

    # POST-PROCESSING: Statistics and cleanup
    # Build correct vendor path based on dest_dir
    if normalized_dest == ".":
        vendor_path = Path(".") / "vendor"
    else:
        vendor_path = Path(normalized_dest) / "vendor"

    if not vendor_path.exists():
        logger.warning("Vendor directory not found, skipping post-processing")
        return

    # Show statistics before cleanup
    if stats:
        rich_print("\n[cyan]=== Vendor Statistics (Before Cleanup) ===[/cyan]\n")
        show_vendor_stats(str(vendor_path), "Initial Vendor Directory")

    # Perform cleanup if requested
    if cleanup:
        rich_print("\n[cyan]=== Starting Vendor Cleanup ===[/cyan]\n")

        # Check if cargo-vendor-checksum is available
        checksum_available = False
        try:
            subprocess.run(
                ["cargo-vendor-checksum", "--version"],
                capture_output=True,
                check=True,
            )
            checksum_available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            rich_print(
                "[yellow]WARNING: cargo-vendor-checksum not found. "
                "Install it for proper checksum updates:[/yellow]"
            )
            rich_print("[yellow]  su -c 'apt-get install cargo-vendor-checksum'[/yellow]\n")

        try:
            cleaner = VendorCleaner(str(vendor_path))

            # Don't remove Windows crates when using cargo-vendor-alt
            # because it already created optimal stubs
            should_remove_windows = not keep_windows and not use_filterer

            if use_filterer and not keep_windows:
                rich_print(
                    "[yellow]INFO: Skipping Windows crate removal: "
                    "cargo-vendor-alt already created optimal stubs[/yellow]"
                )

            cleanup_opts = CleanupOptions(
                remove_binaries=True,
                remove_windows=should_remove_windows,
                update_checksums=True,
            )

            report = cleaner.cleanup(cleanup_opts)

            rich_print("\n[green]=== Cleanup Complete ===[/green]\n")
            report.print_summary()

            # Update git commit if cleanup made changes
            if report.space_saved_mb > 0 or report.removed_crates or report.gitattributes_removed > 0:
                logger.info("Staging vendor cleanup changes")
                # Stage the correct vendor path
                if normalized_dest == ".":
                    subprocess.run(["git", "add", "-f", "vendor"], check=True)
                else:
                    subprocess.run(["git", "add", "-f", f"{normalized_dest}/vendor"], check=True)

                # Check if there are any changes to commit
                diff_result = subprocess.run(
                    ["git", "diff", "--cached", "--quiet"],
                    capture_output=True,
                )

                if diff_result.returncode != 0:
                    # Create commit message (preserve Add vs Update logic)
                    base_msg = (
                        "Update Rust vendor dependencies"
                        if vendor_tracked
                        else "Add vendored Rust dependencies"
                    )
                    
                    if verbose_commit:
                        # Detailed commit with cleanup info
                        cleanup_details = []
                        cleanup_details.append(f"- Removed {report.removed_files} binary artifact files")
                        if report.gitattributes_removed > 0:
                            cleanup_details.append(f"- Removed {report.gitattributes_removed} .gitattributes files (prevents gear/git archive issues)")
                        cleanup_details.append(f"- Removed {len(report.removed_crates)} Windows-specific crates")
                        cleanup_details.append(f"- Updated {report.checksums_updated} checksum files")
                        cleanup_details.append(f"- Space saved: {report.space_saved_mb:.1f} MB")
                        
                        commit_msg = f"""{base_msg}

Vendoring command: {vendor_cmd.split(';')[0]}
Cleanup performed:
{chr(10).join(cleanup_details)}

Final stats: {report.after}
"""
                    else:
                        # Simple commit message (default)
                        commit_msg = base_msg
                    
                    subprocess.run(
                        ["git", "commit", "--amend", "-m", commit_msg],
                        check=True,
                    )
                    logger.info("Updated commit message")
                    rich_print(
                        "[green]? Commit updated[/green]"
                    )

        except Exception as e:
            logger.error(f"Vendor cleanup failed: {e}")
            rich_print(f"[red]Vendor cleanup failed: {e}[/red]")
            rich_print(
                "[yellow]Continuing without cleanup. Manual cleanup may be needed.[/yellow]"
            )

    # Show final statistics
    if stats:
        rich_print("\n[cyan]=== Final Vendor Statistics ===[/cyan]\n")
        show_vendor_stats(str(vendor_path), "Final Vendor Directory")

    # Final instructions
    if cleanup:
        rich_print(
            "\n[green]OK: Vendor dependencies updated with cleanup![/green]"
        )
    else:
        rich_print(
            "\n[yellow]Tip: Use --cleanup flag to optimize vendor directory size[/yellow]"
        )


@vendor_app.command("go")
def go(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
    module_dir: str = typer.Option(
        ".",
        "--module-dir",
        "-m",
        help="Subdirectory containing go.mod file (relative to repository root).",
    ),
    dest_dir: str = typer.Option(
        ".",
        "--dest-dir",
        "-d",
        help="Destination directory for vendor (relative to repository root).",
    ),
    force_commit: bool = typer.Option(
        False,
        "--force-commit",
        "-f",
        help="Skip interactive commit confirmation and commit automatically",
    ),
):
    """Update Go vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    # Normalize paths using helper function
    cd_cmd, module_subdir, normalized_dest = _normalize_vendor_paths(module_dir, dest_dir)

    # Build vendor source path based on module_dir
    if module_subdir:
        vendor_source_path = f"/usr/src/package_go/{module_subdir}/vendor"
    else:
        vendor_source_path = "/usr/src/package_go/vendor"

    _update_vendor_common(
        language="Go",
        packages=["golang", "git"],
        clone_dir="package_go",
        vendor_cmd=f"""mkdir -p /tmp/gopath;
        export GOROOT=/usr/lib/golang;
        export GOPATH=/tmp/gopath;
        {cd_cmd}
        rm -rf vendor;
        go mod vendor;
        go list -mod=vendor ./...;""",
        vendor_source_path=vendor_source_path,
        vendor_dest_path=normalized_dest,
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
        force_commit=force_commit,
        vendor_dir_name="vendor",
    )


@vendor_app.command("npm")
def npm(
    ctx: typer.Context,
    tag: str = typer.Argument(
        "",
        help="Optional tag to use during update.",
    ),
    reinit: bool = typer.Option(
        False,
        "--reinit",
        "-r",
        help="Reinitialize sandbox if it already exists.",
    ),
    module_dir: str = typer.Option(
        ".",
        "--module-dir",
        "-m",
        help="Subdirectory containing package.json (for monorepo packages, relative to repository root).",
    ),
    dest_dir: str = typer.Option(
        ".",
        "--dest-dir",
        "-d",
        help="Destination directory for node_modules (relative to repository root).",
    ),
    force_commit: bool = typer.Option(
        False,
        "--force-commit",
        "-f",
        help="Skip interactive commit confirmation and commit automatically",
    ),
):
    """Update NPM vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    # Normalize paths using helper function
    cd_cmd, module_subdir, normalized_dest = _normalize_vendor_paths(module_dir, dest_dir)

    # Build vendor source path based on module_dir
    if module_subdir:
        vendor_source_path = f"/usr/src/package_nodejs/{module_subdir}/node_modules"
    else:
        vendor_source_path = "/usr/src/package_nodejs/node_modules"

    _update_vendor_common(
        language="NPM",
        packages=["npm", "nodejs", "git"],
        clone_dir="package_nodejs",
        vendor_cmd=f"""{cd_cmd}
        rm -rf node_modules;
        # Install dependencies using appropriate npm command
        if [ -s package-lock.json ]; then
            npm ci || npm install;
        else
            npm install;
        fi""",
        vendor_source_path=vendor_source_path,
        vendor_dest_path=normalized_dest,
        gear_rules_hint="tar: node_modules name=node_modules",
        spec_hint=" SourceX: node_modules.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
        force_commit=force_commit,
        vendor_dir_name="node_modules",
    )


if __name__ == "__main__":
    vendor_app()
