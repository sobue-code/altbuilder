"""Dependency analyzer for RPM spec files."""

import os
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple

from altbuilder.utils.logger import logger


def find_spec_file(spec_path: Optional[str] = None) -> str:
    """
    Find a spec file either by explicit path or auto-discovery.

    Args:
        spec_path: Optional path to .spec file. If None, searches current directory.

    Returns:
        Absolute path to the spec file.

    Raises:
        FileNotFoundError: If spec file not found or no spec files in current directory.
        ValueError: If multiple spec files found (ambiguous) or path is not a .spec file.
    """
    if spec_path:
        # Explicit path provided
        if not os.path.exists(spec_path):
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        if not spec_path.endswith(".spec"):
            raise ValueError(f"Not a spec file: {spec_path}")
        return os.path.abspath(spec_path)

    # Auto-discovery in current directory
    cwd = os.getcwd()
    spec_files = []

    for root, _, files in os.walk(cwd):
        for file in files:
            if file.endswith(".spec"):
                spec_files.append(os.path.join(root, file))

    if len(spec_files) == 0:
        raise FileNotFoundError("No .spec file found in current directory")

    if len(spec_files) > 1:
        file_list = "\n  ".join(spec_files)
        raise ValueError(
            f"Multiple .spec files found. Please specify one:\n  {file_list}"
        )

    return spec_files[0]


def parse_dependencies(spec_path: str) -> Dict[str, any]:
    """
    Parse BuildRequires and per-package Requires from a spec file.

    This function handles multi-package spec files by parsing each %package
    section separately. BuildRequires are global, but Requires are tracked
    per-package to avoid false positives for meta-packages.

    Args:
        spec_path: Path to .spec file.

    Returns:
        Dict with structure:
        {
            "BuildRequires": ["pkg1", "pkg2", ...],
            "packages": {
                "main": {"Requires": ["dep1", "dep2", ...]},
                "subpkg1": {"Requires": ["dep3", ...]},
                ...
            }
        }

    Raises:
        FileNotFoundError: If spec file doesn't exist.
    """
    # Regex patterns
    BR_REGEX = re.compile(r"^BuildRequires(?:\(pre\))?:\s*(.+)", re.IGNORECASE)
    REQ_REGEX = re.compile(r"^Requires(?:\(pre\))?:\s*(.+)", re.IGNORECASE)
    PKG_REGEX = re.compile(r"^%package\s+(?:-n\s+)?(.+)", re.IGNORECASE)

    build_requires = []
    packages = {}
    current_package = "main"  # Default package (no %package directive)
    packages[current_package] = {"Requires": []}

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            for line in f:
                # Track which package section we're in
                pkg_match = PKG_REGEX.match(line)
                if pkg_match:
                    pkg_name = pkg_match.group(1).strip()
                    current_package = pkg_name
                    packages[current_package] = {"Requires": []}
                    continue

                # Parse BuildRequires (global, not package-specific)
                br_match = BR_REGEX.match(line)
                if br_match:
                    build_requires.extend(_parse_dep_line(br_match.group(1)))
                    continue

                # Parse Requires (package-specific)
                req_match = REQ_REGEX.match(line)
                if req_match:
                    packages[current_package]["Requires"].extend(
                        _parse_dep_line(req_match.group(1))
                    )

    except FileNotFoundError:
        logger.error(f"Spec file not found: {spec_path}")
        raise

    # Deduplicate dependencies within each package
    build_requires = list(set(build_requires))
    for pkg_name in packages:
        packages[pkg_name]["Requires"] = list(set(packages[pkg_name]["Requires"]))

    return {
        "BuildRequires": build_requires,
        "packages": packages,
    }


def _parse_dep_line(line: str) -> List[str]:
    """
    Parse a single dependency line and extract package names.

    Args:
        line: Dependency line from spec file (after the colon).

    Returns:
        List of cleaned package names.
    """
    deps = []
    tokens = line.split()

    for token in tokens:
        # 1. Clean up trailing commas
        token = token.strip(",")

        # 2. Skip version constraints
        if any(op in token for op in [">", "<", "="]):
            continue

        # 3. Handle virtual dependencies (e.g., pkgconfig(gtk4))
        # apt-cache can handle these, so keep them
        if token.lower().startswith("pkgconfig("):
            deps.append(token)
            continue

        # 4. Skip RPM macros (like %name, %{?_cross_file})
        if token.startswith("%"):
            continue

        # 5. Add the cleaned package name (minimum 2 characters)
        if len(token) > 1:
            deps.append(token)

    return deps


def get_recursive_dependencies(
    package: str, apt_conf: str, verbose: bool = False
) -> Set[str]:
    """
    Get recursive dependencies of a package using apt-cache.

    Args:
        package: Package name to query.
        apt_conf: Path to apt.conf file to use.
        verbose: If True, log debug information.

    Returns:
        Set of package names that are transitive dependencies.
    """
    deps = set()

    # apt-cache command with --recurse and --important flags
    cmd = [
        "apt-cache",
        "-c",
        apt_conf,
        "depends",
        "--recurse",
        "--important",  # Only hard dependencies (Depends, Pre-Depends)
        package,
    ]

    if verbose:
        logger.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,  # Don't raise on non-zero exit
        )

        if result.returncode != 0:
            if verbose:
                logger.debug(
                    f"apt-cache failed for {package}: {result.stderr.strip()}"
                )
            return deps

        if not result.stdout.strip():
            if verbose:
                logger.debug(f"apt-cache returned empty result for '{package}'")
            return deps

        # Parse apt-cache output
        for line in result.stdout.splitlines():
            line = line.strip()

            # Look for "Depends: <pkg>" or "Pre-Depends: <pkg>" format
            if ": " in line:
                key, value = line.split(": ", 1)
                key = key.strip()
                value = value.strip()

                # Only interested in hard dependencies
                if key in ("Depends", "Pre-Depends"):
                    # Remove version constraints and < markers (virtual packages)
                    pkg_name = value.split(" ", 1)[0].strip("<")

                    # Filter out virtual/obsolete packages (start with <)
                    if pkg_name and not pkg_name.startswith("<"):
                        deps.add(pkg_name)

        if verbose:
            logger.debug(f"Found {len(deps)} transitive dependencies for '{package}'")

    except FileNotFoundError:
        logger.error("apt-cache command not found. Is apt-rpm installed?")
        return deps
    except Exception as e:
        logger.debug(f"Error querying apt-cache for {package}: {e}")
        return deps

    return deps


def analyze_redundancy(
    dependencies: Dict[str, any], apt_conf: str, verbose: bool = False
) -> Dict[str, any]:
    """
    Analyze dependency redundancy by querying apt-cache.

    For each dependency, checks if it's already provided transitively by
    other dependencies. BuildRequires are analyzed globally. Requires are
    analyzed per-package to correctly handle multi-package spec files.

    Args:
        dependencies: Dict with structure:
            {
                "BuildRequires": ["pkg1", "pkg2", ...],
                "packages": {
                    "main": {"Requires": [...]},
                    "subpkg": {"Requires": [...]},
                }
            }
        apt_conf: Path to apt.conf file.
        verbose: Enable verbose logging.

    Returns:
        Dict with structure:
        {
            "BuildRequires": [("redundant_pkg", ["provider1", "provider2"])],
            "packages": {
                "main": {"Requires": [("redundant_pkg", ["provider"])]},
                "subpkg": {"Requires": [...]},
            }
        }
    """
    results = {
        "BuildRequires": [],
        "packages": {}
    }

    # Analyze BuildRequires (global)
    br_list = dependencies.get("BuildRequires", [])
    results["BuildRequires"] = _analyze_dep_list(br_list, apt_conf, verbose, "BuildRequires")

    # Analyze Requires per package
    packages = dependencies.get("packages", {})
    for pkg_name, pkg_data in packages.items():
        req_list = pkg_data.get("Requires", [])
        results["packages"][pkg_name] = {
            "Requires": _analyze_dep_list(req_list, apt_conf, verbose, f"Requires ({pkg_name})")
        }

    return results


def _analyze_dep_list(
    dep_list: List[str], apt_conf: str, verbose: bool = False, dep_type: str = ""
) -> List[Tuple[str, List[str]]]:
    """
    Analyze a single list of dependencies for redundancy.

    Args:
        dep_list: List of package names.
        apt_conf: Path to apt.conf file.
        verbose: Enable verbose logging.
        dep_type: Description for logging (e.g., "BuildRequires", "Requires (main)").

    Returns:
        List of tuples: (redundant_pkg, [providers]).
    """
    if not dep_list:
        return []

    if dep_type:
        logger.info(f"Analyzing {dep_type}: {len(dep_list)} direct dependencies")

    # Build dependency tree map for all packages
    dep_trees = {}
    for pkg in dep_list:
        if verbose:
            logger.debug(f"Querying dependency tree for {pkg}...")
        dep_trees[pkg] = get_recursive_dependencies(pkg, apt_conf, verbose)

    # Find redundancies
    redundant = []
    for pkg_to_check in dep_list:
        providers = []

        # Check if pkg_to_check appears in any other package's tree
        for provider_pkg in dep_list:
            if pkg_to_check == provider_pkg:
                continue

            # Is pkg_to_check in provider_pkg's transitive dependencies?
            if pkg_to_check in dep_trees[provider_pkg]:
                providers.append(provider_pkg)

        if providers:
            redundant.append((pkg_to_check, providers))

    return redundant
