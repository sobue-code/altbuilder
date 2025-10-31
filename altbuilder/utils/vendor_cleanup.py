"""
Vendor directory cleanup and optimization utilities.

This module provides functionality for cleaning up and optimizing
vendor directories for Rust, Go, and other language package managers.

Key features:
- Remove binary artifacts (.a, .lib, .dll, .obj)
- Remove platform-specific dependencies (e.g., Windows crates on Linux)
- Update checksums after modifications
- Analyze and report vendor directory statistics
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from rich.console import Console
from rich.table import Table

from altbuilder.utils.logger import logger

console = Console()


@dataclass
class VendorStats:
    """Statistics about vendor directory."""

    total_size_mb: float
    crate_count: int
    file_count: int
    top_crates: List[Tuple[str, float]]  # (name, size_mb)

    def __str__(self):
        return f"{self.crate_count} crates, {self.file_count} files, {self.total_size_mb:.1f} MB"


@dataclass
class CleanupOptions:
    """Options for vendor cleanup operations."""

    remove_binaries: bool = True
    remove_windows: bool = True
    update_checksums: bool = True
    platforms: Optional[List[str]] = None


@dataclass
class CleanupReport:
    """Report of cleanup operations performed."""

    before: VendorStats
    after: VendorStats
    removed_files: int
    removed_crates: List[str]
    space_saved_mb: float
    checksums_updated: int
    gitattributes_removed: int = 0

    def print_summary(self):
        """Print cleanup summary with rich formatting."""
        table = Table(title="Vendor Cleanup Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Before", style="yellow")
        table.add_column("After", style="green")
        table.add_column("Saved", style="magenta")

        table.add_row(
            "Total Size",
            f"{self.before.total_size_mb:.1f} MB",
            f"{self.after.total_size_mb:.1f} MB",
            f"{self.space_saved_mb:.1f} MB",
        )
        table.add_row(
            "Crate Count",
            str(self.before.crate_count),
            str(self.after.crate_count),
            str(self.before.crate_count - self.after.crate_count),
        )
        table.add_row(
            "File Count",
            str(self.before.file_count),
            str(self.after.file_count),
            str(self.removed_files),
        )

        console.print(table)

        if self.gitattributes_removed > 0:
            console.print(
                f"\n[cyan]Removed {self.gitattributes_removed} .gitattributes files[/cyan]"
            )
            console.print(
                "[dim](.gitattributes can cause gear/git archive to exclude files)[/dim]"
            )

        if self.removed_crates:
            console.print(
                f"\n[yellow]Removed crates ({len(self.removed_crates)}):[/yellow]"
            )
            for crate in self.removed_crates[:10]:
                console.print(f"  • {crate}")
            if len(self.removed_crates) > 10:
                console.print(
                    f"  ... and {len(self.removed_crates) - 10} more"
                )


class VendorCleaner:
    """Handle vendor directory cleanup and optimization."""

    def __init__(self, vendor_path: str):
        """
        Initialize cleaner with vendor directory path.

        Args:
            vendor_path: Path to the vendor directory

        Raises:
            FileNotFoundError: If vendor directory doesn't exist
        """
        self.vendor_path = Path(vendor_path)
        if not self.vendor_path.exists():
            raise FileNotFoundError(
                f"Vendor directory not found: {vendor_path}"
            )

    def analyze(self) -> VendorStats:
        """
        Analyze vendor directory and return statistics.

        Note: Uses actual disk usage (du) for accurate size reporting,
        which matches what users see with 'du -sh vendor'.

        Returns:
            VendorStats object with directory statistics
        """
        logger.info(f"Analyzing vendor directory: {self.vendor_path}")

        # Count files and get accurate disk usage
        file_count = 0
        crate_sizes = {}

        # Calculate total size using du (matches user expectation)
        # Use -sk (kilobytes) for actual disk usage, not -sb (apparent size)
        try:
            result = subprocess.run(
                ["du", "-sk", str(self.vendor_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            total_size_kb = int(result.stdout.split()[0])
            total_size = total_size_kb * 1024  # Convert to bytes for consistency
            total_size_mb = total_size_kb / 1024  # KB to MB
            logger.info(f"Using du -sk: {total_size_kb} KB ({total_size_mb:.1f} MB)")
        except Exception as e:
            logger.warning(f"Failed to get du size, falling back to stat: {e}")
            total_size = 0
            # Fallback to stat method
            for root, dirs, files in os.walk(self.vendor_path):
                for file in files:
                    try:
                        total_size += Path(root, file).stat().st_size
                    except OSError:
                        pass
            total_size_mb = total_size / (1024 * 1024)
            logger.info(f"Using stat fallback: {total_size} bytes ({total_size_mb:.1f} MB)")

        # Calculate per-crate sizes and count files
        for crate_dir in self.vendor_path.iterdir():
            if not crate_dir.is_dir():
                continue

            # Count files in this crate (including .cargo and other hidden dirs)
            crate_file_count = 0
            for root, dirs, files in os.walk(crate_dir):
                for file in files:
                    file_count += 1
                    crate_file_count += 1

            # Get crate size using du for consistency
            if crate_file_count > 0:  # Only include crates with files
                try:
                    result = subprocess.run(
                        ["du", "-sk", str(crate_dir)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    crate_size_kb = int(result.stdout.split()[0])
                    crate_size = crate_size_kb * 1024  # Convert to bytes
                    crate_sizes[crate_dir.name] = crate_size
                except Exception:
                    # Fallback to stat
                    crate_size = 0
                    for root, dirs, files in os.walk(crate_dir):
                        for file in files:
                            try:
                                crate_size += Path(root, file).stat().st_size
                            except OSError:
                                pass
                    if crate_size > 0:
                        crate_sizes[crate_dir.name] = crate_size

        # Top 10 crates by size
        top_crates = sorted(
            crate_sizes.items(), key=lambda x: x[1], reverse=True
        )[:10]
        top_crates_mb = [
            (name, size / (1024 * 1024)) for name, size in top_crates
        ]

        stats = VendorStats(
            total_size_mb=total_size / (1024 * 1024),
            crate_count=len(crate_sizes),
            file_count=file_count,
            top_crates=top_crates_mb,
        )

        logger.info(f"Vendor analysis: {stats}")
        return stats

    def remove_binary_artifacts(self) -> int:
        """
        Remove binary artifacts (.a, .lib, .dll, .obj, etc.) from vendor.

        Returns:
            Number of files removed
        """
        logger.info("Removing binary artifacts from vendor directory")

        extensions = [".a", ".lib", ".dll", ".obj", ".dylib", ".so"]
        removed = 0

        for ext in extensions:
            # Use find command for efficiency
            try:
                result = subprocess.run(
                    [
                        "find",
                        str(self.vendor_path),
                        "-name",
                        f"*{ext}",
                        "-delete",
                        "-print",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                files = result.stdout.strip().split("\n")
                count = len([f for f in files if f])
                removed += count
                if count > 0:
                    logger.info(f"Removed {count} {ext} files")
            except Exception as e:
                logger.warning(
                    f"Failed to remove {ext} files: {e}"
                )

        logger.info(f"Total binary artifacts removed: {removed}")
        return removed

    def remove_windows_crates(self) -> List[str]:
        """
        Remove Windows-specific crates from vendor.

        Returns:
            List of removed crate names
        """
        logger.info("Removing Windows-specific crates")

        windows_patterns = [
            "*-pc-windows-*",
            "winapi-*-pc-windows-*",
        ]

        removed_crates = []

        for pattern in windows_patterns:
            matching = list(self.vendor_path.glob(pattern))
            for crate_dir in matching:
                if crate_dir.is_dir():
                    logger.debug(
                        f"Removing Windows crate: {crate_dir.name}"
                    )
                    try:
                        subprocess.run(
                            ["rm", "-rf", str(crate_dir)], check=True
                        )
                        removed_crates.append(crate_dir.name)
                    except subprocess.CalledProcessError as e:
                        logger.warning(
                            f"Failed to remove {crate_dir.name}: {e}"
                        )

        # Also check for Windows-only utility crates
        windows_only_crates = [
            "winapi-util",
            "winapi-build",
            "windows-targets",
        ]

        for crate_name in windows_only_crates:
            # Check all versions of the crate
            matching_dirs = list(
                self.vendor_path.glob(f"{crate_name}*")
            )
            for crate_path in matching_dirs:
                if crate_path.is_dir() and crate_path.name not in removed_crates:
                    # Check if this is truly a Windows-only crate by looking at Cargo.toml
                    cargo_toml = crate_path / "Cargo.toml"
                    if cargo_toml.exists():
                        try:
                            with open(cargo_toml, "r") as f:
                                content = f.read()
                                # Simple heuristic: if mentions windows in target
                                if (
                                    "target.'cfg(windows)" in content
                                    or "target.'cfg(target_os = \"windows\")'" in content
                                ):
                                    logger.debug(
                                        f"Removing Windows-only crate: {crate_path.name}"
                                    )
                                    subprocess.run(
                                        ["rm", "-rf", str(crate_path)],
                                        check=True,
                                    )
                                    removed_crates.append(crate_path.name)
                        except Exception as e:
                            logger.debug(
                                f"Could not analyze {cargo_toml}: {e}"
                            )

        logger.info(
            f"Removed {len(removed_crates)} Windows-specific crates"
        )
        return removed_crates

    def remove_git_directories(self) -> int:
        """
        Remove .git directories from vendor crates.

        Note: cargo-vendor-alt typically doesn't copy .git directories,
        but they may appear in some edge cases (e.g., manually copied submodules).
        This function removes them if found to reduce vendor size.

        Returns:
            Number of .git directories removed
        """
        logger.info("Checking for .git directories in vendor")

        removed = 0
        git_dirs = list(self.vendor_path.rglob(".git"))
        
        if not git_dirs:
            logger.debug("No .git directories found (normal for cargo-vendor-alt)")
            return 0

        for git_dir in git_dirs:
            if git_dir.is_dir():
                try:
                    subprocess.run(
                        ["rm", "-rf", str(git_dir)],
                        check=True
                    )
                    removed += 1
                    logger.debug(f"Removed .git directory: {git_dir}")
                except Exception as e:
                    logger.warning(f"Failed to remove {git_dir}: {e}")

        if removed > 0:
            logger.info(f"Removed {removed} .git directories")

        return removed

    def remove_gitattributes(self) -> int:
        """
        Remove .gitattributes files from vendor crates.

        .gitattributes files can contain export-ignore rules that cause
        files to be excluded from git archive (used by gear), but their
        checksums remain in .cargo-checksum.json, causing build failures.

        Returns:
            Number of .gitattributes files removed
        """
        logger.info("Removing .gitattributes files from vendor")

        removed = 0
        gitattributes_files = list(self.vendor_path.rglob(".gitattributes"))
        
        for gitattr_file in gitattributes_files:
            if gitattr_file.is_file():
                try:
                    gitattr_file.unlink()
                    removed += 1
                    logger.debug(f"Removed .gitattributes: {gitattr_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove {gitattr_file}: {e}")

        if removed > 0:
            logger.info(f"Removed {removed} .gitattributes files")

        return removed

    def update_checksums(self) -> int:
        """
        Update .cargo-checksum.json files after modifications.

        Uses cargo-vendor-checksum if available, otherwise falls back to manual update.

        Returns:
            Number of checksum files updated
        """
        logger.info("Updating cargo checksums")

        # Try to use cargo-vendor-checksum --all (recommended method)
        try:
            # Run from parent directory (where vendor/ is a subdirectory)
            result = subprocess.run(
                ["cargo-vendor-checksum", "--all"],
                cwd=str(self.vendor_path.parent),  # Run from directory containing vendor/
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                # Count how many crates have checksum files
                checksum_files = list(
                    self.vendor_path.glob("*/.cargo-checksum.json")
                )
                logger.info(
                    f"Updated checksums for all {len(checksum_files)} crates using cargo-vendor-checksum"
                )
                return len(checksum_files)
            else:
                logger.warning(
                    f"cargo-vendor-checksum --all failed with exit code {result.returncode}"
                )
                if result.stderr:
                    logger.warning(f"stderr: {result.stderr.strip()}")
                if result.stdout:
                    logger.debug(f"stdout: {result.stdout.strip()}")
                logger.info("Falling back to manual checksum update")
        except FileNotFoundError:
            logger.debug("cargo-vendor-checksum not found, using manual update")
        except Exception as e:
            logger.warning(f"cargo-vendor-checksum error: {e}")
            logger.info("Falling back to manual checksum update")

        # Fallback: manual checksum update (remove entries for deleted files)
        updated = 0
        checksum_files = list(
            self.vendor_path.glob("*/.cargo-checksum.json")
        )

        for checksum_file in checksum_files:
            try:
                with open(checksum_file, "r") as f:
                    data = json.load(f)

                # Remove entries for deleted files
                if "files" in data:
                    crate_dir = checksum_file.parent
                    existing_files = {}

                    for file_path, checksum in data["files"].items():
                        full_path = crate_dir / file_path
                        if full_path.exists():
                            existing_files[file_path] = checksum
                        else:
                            logger.debug(
                                f"Removing checksum for deleted file: {file_path}"
                            )

                    if len(existing_files) != len(data["files"]):
                        data["files"] = existing_files
                        with open(checksum_file, "w") as f:
                            json.dump(data, f, indent=2)
                        updated += 1
                        logger.debug(
                            f"Updated checksum: {checksum_file.parent.name}"
                        )

            except Exception as e:
                logger.warning(
                    f"Failed to update checksum {checksum_file}: {e}"
                )

        logger.info(f"Updated {updated} checksum files (manual method)")
        return updated

    def cleanup(self, options: CleanupOptions) -> CleanupReport:
        """
        Execute full cleanup with given options.

        Args:
            options: CleanupOptions specifying what to clean

        Returns:
            CleanupReport with details of cleanup performed
        """
        logger.info(f"Starting vendor cleanup with options: {options}")

        # Before stats
        before_stats = self.analyze()

        removed_files = 0
        removed_crates = []
        gitattributes_removed = 0

        # Remove .gitattributes files (CRITICAL - they cause gear/git archive issues)
        gitattributes_removed = self.remove_gitattributes()
        if gitattributes_removed > 0:
            removed_files += gitattributes_removed

        # Remove .git directories (if present - reduces size, usually not needed)
        git_removed = self.remove_git_directories()
        if git_removed > 0:
            removed_files += git_removed

        # Remove binary artifacts
        if options.remove_binaries:
            removed_files += self.remove_binary_artifacts()

        # Remove Windows crates
        if options.remove_windows:
            removed_crates = self.remove_windows_crates()

        # Update checksums (must be AFTER all modifications)
        checksums_updated = 0
        if options.update_checksums:
            checksums_updated = self.update_checksums()

        # After stats
        after_stats = self.analyze()

        report = CleanupReport(
            before=before_stats,
            after=after_stats,
            removed_files=removed_files,
            removed_crates=removed_crates,
            space_saved_mb=before_stats.total_size_mb
            - after_stats.total_size_mb,
            checksums_updated=checksums_updated,
            gitattributes_removed=gitattributes_removed,
        )

        logger.info(
            f"Vendor cleanup complete: saved {report.space_saved_mb:.1f} MB"
        )
        return report


def show_vendor_stats(vendor_path: str, title: str = "Vendor Statistics"):
    """
    Show vendor directory statistics in rich table.

    Args:
        vendor_path: Path to vendor directory
        title: Title for the statistics table
    """
    try:
        cleaner = VendorCleaner(vendor_path)
        stats = cleaner.analyze()

        table = Table(title=title)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Total Size", f"{stats.total_size_mb:.1f} MB")
        table.add_row("Crate Count", str(stats.crate_count))
        table.add_row("File Count", str(stats.file_count))

        console.print(table)

        # Show top crates
        if stats.top_crates:
            console.print("\n[cyan]Top 10 Largest Crates:[/cyan]")
            for name, size_mb in stats.top_crates:
                console.print(f"  {name:40s} {size_mb:8.1f} MB")
    except Exception as e:
        logger.error(f"Failed to show vendor stats: {e}")
        console.print(f"[red]Failed to analyze vendor directory: {e}[/red]")
