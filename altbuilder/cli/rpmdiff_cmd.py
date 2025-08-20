import os
import subprocess
import tempfile

import typer

from ..utils.colorize import colorize

app = typer.Typer(
    name="rpmdiff",
    help="Compare two RPM packages and display differences in dependencies, provides, conflicts, and file lists.",
)


@app.command()
def rpmdiff_cmd(
    old_package: str = typer.Argument(
        ...,
        help="Path to the old RPM package.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    new_package: str = typer.Argument(
        ...,
        help="Path to the new RPM package.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    requires: bool = typer.Option(
        True, "--requires", help="Compare package dependencies (requires)."
    ),
    provides: bool = typer.Option(
        True, "--provides", help="Compare provided capabilities (provides)."
    ),
    conflicts: bool = typer.Option(
        True, "--conflicts", help="Compare package conflicts (conflicts)."
    ),
    files: bool = typer.Option(True, "--files", help="Compare file lists (files)."),
):
    """Compares two RPM packages and displays differences in dependencies,
    provided capabilities, conflicts, and file lists.
    """

    # Validate packages
    for pkg in (old_package, new_package):
        if not os.path.exists(pkg):
            typer.echo(colorize(f"Error: {pkg} does not exist.", color="red"))
            raise typer.Exit(code=1)
        try:
            subprocess.run(
                ["rpm", "-qp", pkg],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            typer.echo(
                colorize(f"Error: {pkg} is not a valid RPM package.", color="red")
            )
            raise typer.Exit(code=1)

    # If no flags provided → compare all
    if not any([requires, provides, conflicts, files]):
        requires = provides = conflicts = files = True

    def get_rpm_query(package: str, query: str) -> list[str]:
        """Extracts info from RPM using rpm -qp QUERY."""
        try:
            output = subprocess.check_output(["rpm", "-qp", package, query], text=True)
            return sorted(output.splitlines())
        except subprocess.CalledProcessError:
            return []

    def compare_lists(label: str, old_list: list[str], new_list: list[str]):
        """Diffs two lists via external `diff` and colors output."""
        with (
            tempfile.NamedTemporaryFile("w") as old_file,
            tempfile.NamedTemporaryFile("w") as new_file,
        ):
            old_file.write("\n".join(old_list))
            old_file.flush()
            new_file.write("\n".join(new_list))
            new_file.flush()
            diff_output = subprocess.run(
                [
                    "diff",
                    "--unchanged-line-format=",
                    "--old-line-format=- %L",
                    "--new-line-format=+ %L",
                    old_file.name,
                    new_file.name,
                ],
                text=True,
                capture_output=True,
            ).stdout

            if diff_output.strip():
                typer.echo(colorize(f"@@ {label} @@", color="cyan"))
                for line in diff_output.splitlines():
                    if line.startswith("-"):
                        typer.echo(colorize(line, color="red"))
                    elif line.startswith("+"):
                        typer.echo(colorize(line, color="green"))

    # Display headers
    typer.echo(colorize(f"--- {os.path.basename(old_package)}", color="yellow"))
    typer.echo(colorize(f"+++ {os.path.basename(new_package)}", color="yellow"))

    # Define categories
    categories: list[tuple[str, str]] = []
    if requires:
        categories.append(("REQUIRES", "--requires"))
    if provides:
        categories.append(("PROVIDES", "--provides"))
    if conflicts:
        categories.append(("CONFLICTS", "--conflicts"))
    if files:
        categories.append(("FILE LIST", "--list"))

    # Run comparisons
    for label, query in categories:
        old_data = get_rpm_query(old_package, query)
        new_data = get_rpm_query(new_package, query)
        compare_lists(label, old_data, new_data)


if __name__ == "__main__":
    app()
