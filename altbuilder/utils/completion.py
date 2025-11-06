"""Autocompletion functions for CLI commands."""
import glob
import os
from typing import List

import typer

from altbuilder.config import load_config


def complete_sandbox(incomplete: str) -> List[str]:
    """Autocomplete function for sandbox names."""
    try:
        config = load_config()
        environment_dir = config["environment_dir"]

        if not os.path.exists(environment_dir):
            return []

        sandboxes = [
            d for d in os.listdir(environment_dir)
            if os.path.isdir(os.path.join(environment_dir, d))
            and d.startswith(incomplete)
        ]
        return sandboxes
    except Exception:
        return []


def complete_package(ctx: typer.Context, incomplete: str) -> List[str]:
    """Autocomplete function for package names in the selected sandbox."""
    try:
        # Try multiple ways to get sandbox name
        sandbox = None

        # 1. Try from params (local --sandbox flag)
        if hasattr(ctx, 'params') and 'sandbox' in ctx.params:
            sandbox = ctx.params.get('sandbox')

        # 2. Try from parent context (global --sandbox flag)
        if not sandbox and ctx.parent and hasattr(ctx.parent, 'params') and 'sandbox' in ctx.parent.params:
            sandbox = ctx.parent.params.get('sandbox')

        # 3. Try from obj (set by global flag callback)
        if not sandbox and ctx.obj:
            sandbox = ctx.obj.get('sandbox')

        # 4. Use default from config
        if not sandbox:
            try:
                config = load_config()
                sandbox = f"{config['branch']}-{config['arch']}"
            except Exception:
                return []

        config = load_config()
        environment_dir = config["environment_dir"]
        sandbox_path = os.path.join(environment_dir, sandbox)

        if not os.path.exists(sandbox_path):
            return []

        packages = set()

        # Search in SRPMS
        srpms_dir = os.path.join(sandbox_path, "hasher", "repo", "SRPMS.hasher")
        if os.path.exists(srpms_dir):
            for rpm_file in glob.glob(os.path.join(srpms_dir, "*.rpm")):
                basename = os.path.basename(rpm_file)
                # Extract package name (remove version and .src.rpm)
                pkg_name = basename.rsplit("-", 2)[0]
                if pkg_name.startswith(incomplete):
                    packages.add(pkg_name)

        # Search in arch RPMs
        arch_dirs = glob.glob(os.path.join(sandbox_path, "hasher", "repo", "*", "RPMS.hasher"))
        for arch_dir in arch_dirs:
            for rpm_file in glob.glob(os.path.join(arch_dir, "*.rpm")):
                basename = os.path.basename(rpm_file)
                # Extract package name (remove version, arch, and .rpm)
                # Handle debuginfo packages specially - skip them in autocomplete
                if "-debuginfo-" in basename:
                    continue

                pkg_name = basename.rsplit("-", 2)[0]
                if pkg_name.startswith(incomplete):
                    packages.add(pkg_name)

        return sorted(list(packages))
    except Exception:
        return []
