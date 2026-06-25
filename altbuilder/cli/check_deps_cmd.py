"""Check BuildRequires and Requires for redundant dependencies."""

import os
from typing import Dict, List, Tuple

import typer
from rich import print as rich_print

from altbuilder.config import get_sandbox_config, load_config
from altbuilder.core.dependency_analyzer import (
    analyze_redundancy,
    find_spec_file,
    parse_dependencies,
)
from altbuilder.core.environment import Environment
from altbuilder.utils import init_logger, logger
from altbuilder.utils.json_utils import is_json_mode, json_response

app = typer.Typer(
    name="check-deps",
    help="Check BuildRequires and Requires for redundant dependencies.",
)


@app.command()
def check_deps_cmd(
    ctx: typer.Context,
    spec_path: str = typer.Argument(
        None,
        help="Path to .spec file. If not provided, searches current directory.",
    ),
    sandbox: str = typer.Option(
        None,
        "--sandbox",
        "-s",
        help="Sandbox name. Defaults to <branch>-<arch> from config.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output with detailed dependency information.",
    ),
):
    """
    Analyze BuildRequires and Requires for redundant dependencies.

    This command checks if any dependencies in your spec file are already
    transitively provided by other direct dependencies, using the sandbox's
    APT repository configuration.

    Examples:
        altbuilder -s Sisyphus-x86_64 check-deps
        altbuilder -s Sisyphus-x86_64 check-deps mypackage.spec
        altbuilder -s Sisyphus-x86_64 check-deps --verbose
        altbuilder -s Sisyphus-x86_64 check-deps --json mypackage.spec
    """
    json_mode = is_json_mode(ctx)
    config = load_config()

    # Resolve sandbox name
    sandbox_name = sandbox or ctx.obj.get("sandbox") or f"{config['branch']}-{config['arch']}"
    sandbox_config = get_sandbox_config(sandbox_name, config)

    # Initialize logger
    init_logger(sandbox_name, sandbox_config["build_logs_dir"], config)

    # Validate sandbox exists
    env = Environment(sandbox_name, sandbox_config)

    if not env.exists():
        error_msg = f"Sandbox {sandbox_name} does not exist. Run 'altbuilder init' first."
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, code=1)
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)

    # Check if aptbox exists (created after first build)
    aptbox_apt_conf = os.path.join(env.hasher_dir, "aptbox", "etc", "apt", "apt.conf")

    if not os.path.exists(aptbox_apt_conf):
        error_msg = f"Sandbox {sandbox_name} aptbox not initialized."
        logger.error(error_msg)
        if json_mode:
            json_response(ctx, "error", message=error_msg, sandbox=sandbox_name, code=1)
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            rich_print(
                "[yellow]Hint: Run a build first to initialize the aptbox.[/yellow]"
            )
            raise typer.Exit(code=1)

    # Find spec file
    try:
        spec_file = find_spec_file(spec_path)
    except (FileNotFoundError, ValueError) as e:
        error_msg = str(e)
        logger.error(error_msg)
        if json_mode:
            json_response(
                ctx, "error", message=error_msg, sandbox=sandbox_name, code=1
            )
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)

    # Parse dependencies from spec file
    if not json_mode:
        rich_print(f"[bold]Analyzing spec file:[/bold] {spec_file}")

    try:
        dependencies = parse_dependencies(spec_file)
    except Exception as e:
        error_msg = f"Failed to parse spec file: {e}"
        logger.error(error_msg)
        if json_mode:
            json_response(
                ctx, "error", message=error_msg, spec_file=spec_file, code=1
            )
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)

    # Show dependency counts
    br_count = len(dependencies.get("BuildRequires", []))
    packages = dependencies.get("packages", {})

    # Count total Requires across all packages
    req_count = sum(len(pkg_data.get("Requires", [])) for pkg_data in packages.values())

    if not json_mode:
        pkg_count = len(packages)
        rich_print(f"Found {br_count} BuildRequires and {req_count} Requires across {pkg_count} package(s)")

        if verbose:
            if br_count > 0:
                br_list = ", ".join(dependencies["BuildRequires"])
                rich_print(f"[dim]BuildRequires: {br_list}[/dim]")

            # Show Requires per package
            for pkg_name, pkg_data in packages.items():
                req_list = pkg_data.get("Requires", [])
                if req_list:
                    req_str = ", ".join(req_list)
                    rich_print(f"[dim]Requires ({pkg_name}): {req_str}[/dim]")

    # Analyze redundancy
    if not json_mode and verbose:
        rich_print("\n[cyan]Querying dependency trees...[/cyan]")

    try:
        results = analyze_redundancy(dependencies, aptbox_apt_conf, verbose)
    except Exception as e:
        error_msg = f"Failed to analyze dependencies: {e}"
        logger.error(error_msg)
        if json_mode:
            json_response(
                ctx, "error", message=error_msg, spec_file=spec_file, code=1
            )
        else:
            rich_print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(code=1)

    # Output results
    if json_mode:
        _output_json(ctx, spec_file, sandbox_name, dependencies, results)
    else:
        _output_text(spec_file, dependencies, results, verbose)


def _output_text(
    spec_file: str,
    dependencies: Dict[str, any],
    results: Dict[str, any],
    verbose: bool,
):
    """
    Output analysis results in human-readable text format.

    Args:
        spec_file: Path to the spec file that was analyzed.
        dependencies: Dict with 'BuildRequires' and per-package 'Requires'.
        results: Dict with redundancy analysis results.
        verbose: Whether verbose output is enabled.
    """
    rich_print("\n")

    # Analyze BuildRequires (global)
    br_list = dependencies.get("BuildRequires", [])
    br_redundant = results.get("BuildRequires", [])

    rich_print(f"[bold cyan]Analyzing BuildRequires...[/bold cyan]")

    if br_redundant:
        # Print header
        rich_print("=" * 64)
        rich_print(f"[bold yellow]REDUNDANT DEPENDENCIES FOUND IN BuildRequires[/bold yellow]")
        rich_print("=" * 64)

        for pkg, providers in br_redundant:
            rich_print(f"\n[bold red][!] REDUNDANT:[/bold red] {pkg}")
            provider_str = ", ".join(providers)
            rich_print(f"    Reason: Already provided by {provider_str}")

            # Special advice for -devel packages
            if pkg.endswith("-devel") and any(p.endswith("-devel") for p in providers):
                rich_print(
                    f"    [dim]Advice: Development packages often depend on each other. Consider removing.[/dim]"
                )
    else:
        rich_print(f"[green]No redundant dependencies found in BuildRequires.[/green]")

    rich_print("\n")

    # Analyze Requires per package
    packages_deps = dependencies.get("packages", {})
    packages_results = results.get("packages", {})

    for pkg_name, pkg_data in packages_deps.items():
        req_list = pkg_data.get("Requires", [])
        req_redundant = packages_results.get(pkg_name, {}).get("Requires", [])

        # Skip packages with no Requires
        if not req_list:
            continue

        rich_print(f"[bold cyan]Analyzing Requires ({pkg_name})...[/bold cyan]")

        if req_redundant:
            # Print header
            rich_print("=" * 64)
            rich_print(f"[bold yellow]REDUNDANT DEPENDENCIES FOUND IN Requires ({pkg_name})[/bold yellow]")
            rich_print("=" * 64)

            for pkg, providers in req_redundant:
                rich_print(f"\n[bold red][!] REDUNDANT:[/bold red] {pkg}")
                provider_str = ", ".join(providers)
                rich_print(f"    Reason: Already provided by {provider_str}")

                # Special advice for -devel packages
                if pkg.endswith("-devel") and any(p.endswith("-devel") for p in providers):
                    rich_print(
                        f"    [dim]Advice: Development packages often depend on each other. Consider removing.[/dim]"
                    )
        else:
            rich_print(f"[green]No redundant dependencies found in Requires ({pkg_name}).[/green]")

        rich_print("\n")

    # Summary
    br_total = len(br_list)
    br_redundant_count = len(br_redundant)

    # Count total Requires and redundant across all packages
    req_total = sum(len(pkg_data.get("Requires", [])) for pkg_data in packages_deps.values())
    req_redundant_count = sum(
        len(packages_results.get(pkg_name, {}).get("Requires", []))
        for pkg_name in packages_deps.keys()
    )

    rich_print("[bold]Summary:[/bold]")
    rich_print(f"  - BuildRequires: {br_redundant_count} redundant out of {br_total}")
    rich_print(f"  - Requires: {req_redundant_count} redundant out of {req_total} (across all packages)")


def _output_json(
    ctx: typer.Context,
    spec_file: str,
    sandbox_name: str,
    dependencies: Dict[str, any],
    results: Dict[str, any],
):
    """
    Output analysis results in JSON format.

    Args:
        ctx: Typer context.
        spec_file: Path to the spec file that was analyzed.
        sandbox_name: Name of the sandbox used.
        dependencies: Dict with 'BuildRequires' and per-package 'Requires'.
        results: Dict with redundancy analysis results.
    """
    # Build analysis structure
    analysis = {}

    # BuildRequires (global)
    br_list = dependencies.get("BuildRequires", [])
    br_redundant = results.get("BuildRequires", [])
    redundant_items = []

    for pkg, providers in br_redundant:
        advice = None
        if pkg.endswith("-devel") and any(p.endswith("-devel") for p in providers):
            advice = "Development packages often depend on each other. Consider removing."

        redundant_items.append(
            {
                "package": pkg,
                "provided_by": providers,
                "advice": advice,
            }
        )

    analysis["BuildRequires"] = {
        "total": len(br_list),
        "redundant_count": len(br_redundant),
        "redundant": redundant_items,
    }

    # Requires per package
    packages_deps = dependencies.get("packages", {})
    packages_results = results.get("packages", {})
    packages_analysis = {}

    for pkg_name, pkg_data in packages_deps.items():
        req_list = pkg_data.get("Requires", [])
        req_redundant = packages_results.get(pkg_name, {}).get("Requires", [])
        redundant_items = []

        for pkg, providers in req_redundant:
            advice = None
            if pkg.endswith("-devel") and any(p.endswith("-devel") for p in providers):
                advice = "Development packages often depend on each other. Consider removing."

            redundant_items.append(
                {
                    "package": pkg,
                    "provided_by": providers,
                    "advice": advice,
                }
            )

        packages_analysis[pkg_name] = {
            "total": len(req_list),
            "redundant_count": len(req_redundant),
            "redundant": redundant_items,
        }

    analysis["packages"] = packages_analysis

    # Output JSON response
    json_response(
        ctx,
        "success",
        spec_file=spec_file,
        sandbox=sandbox_name,
        analysis=analysis,
    )


if __name__ == "__main__":
    app()
