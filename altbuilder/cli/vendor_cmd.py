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
):
    """Common logic for updating vendor dependencies."""
    config = load_config()
    sandbox_name = sandbox or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)
    env = Environment(sandbox_name, sandbox_config)

    logger.info(
        f"Updating {language} vendor dependencies in sandbox {sandbox_name} with tag: {tag or 'none'}"
    )

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
        env.copy_from(vendor_source_path, vendor_dest_path)

        # Check if vendor directory exists in the previous commit (HEAD)
        # Note: vendor_dest_path might be "." (current dir), so we need to check "vendor" specifically
        vendor_check_path = "vendor" if vendor_dest_path == "." else vendor_dest_path
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
            subprocess.run(["git", "add", "-f", "vendor"], check=True)
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
):
    """Update Rust vendor dependencies with optional cleanup and optimization."""
    sandbox = ctx.obj.get("sandbox")

    # Determine vendoring command based on filterer flag
    if use_filterer:
        vendor_cmd = "cargo-vendor-alt || cargo vendor;"
        packages = ["rust-cargo", "cargo-vendor-filterer", "git"]
        rich_print(
            "[cyan]Using cargo-vendor-alt for platform-specific filtering[/cyan]"
        )
    else:
        vendor_cmd = "cargo vendor;"
        packages = ["rust-cargo", "git"]

    # Check if this is first vendor addition (before running vendor command)
    vendor_tracked = False
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", "vendor"],
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
        vendor_source_path="/usr/src/package_rust/vendor",
        vendor_dest_path=".",  # Extract to current directory (creates ./vendor/)
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
    )

    # POST-PROCESSING: Statistics and cleanup
    vendor_path = Path(".") / "vendor"

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
                subprocess.run(["git", "add", "-f", "vendor"], check=True)

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
):
    """Update Go vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    _update_vendor_common(
        language="Go",
        packages=["golang", "git"],
        clone_dir="package_go",
        vendor_cmd="""mkdir -p /tmp/gopath;
        export GOROOT=/usr/lib/golang;
        export GOPATH=/tmp/gopath;
        mkdir -p vendor;
        go mod vendor;""",
        vendor_source_path="/usr/src/package_go/vendor",
        vendor_dest_path=".",
        gear_rules_hint="tar: vendor name=vendor",
        spec_hint=" SourceX: vendor.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
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
):
    """Update NPM vendor dependencies."""
    sandbox = ctx.obj.get("sandbox")

    _update_vendor_common(
        language="NPM",
        packages=["npm", "nodejs", "git"],
        clone_dir="package_nodejs",
        vendor_cmd="""rm -rf node_modules;
        # Install dependencies using appropriate npm command
        if [ -s package-lock.json ]; then
            npm ci || npm install;
        else
            npm install;
        fi""",
        vendor_source_path="/usr/src/package_nodejs/node_modules",
        vendor_dest_path=".",
        gear_rules_hint="tar: node_modules name=node_modules",
        spec_hint=" SourceX: node_modules.tar\n\n%setup -a X",
        sandbox=sandbox,
        reinit=reinit,
        tag=tag,
    )


if __name__ == "__main__":
    vendor_app()
