import os
import subprocess
import tempfile
import click
from ..utils.colorize import colorize

@click.command("rpmdiff")
@click.argument("old_package", type=click.Path(exists=True))
@click.argument("new_package", type=click.Path(exists=True))
@click.option("--requires", is_flag=True, help="Compare package dependencies (requires).")
@click.option("--provides", is_flag=True, help="Compare provided capabilities (provides).")
@click.option("--conflicts", is_flag=True, help="Compare package conflicts (conflicts).")
@click.option("--files", is_flag=True, help="Compare file lists (files).")
@click.help_option("--help", "-h")
def rpmdiff_cmd(old_package, new_package, requires=True, provides=True, conflicts=True, files=True):
    """Compares two RPM packages and displays differences in dependencies, provided capabilities, conflicts, and file lists."""
    # Validate packages
    for pkg in (old_package, new_package):
        if not os.path.exists(pkg):
            click.echo(colorize(f"Error: {pkg} does not exist.", color="red"))
            return
        try:
            subprocess.run(["rpm", "-qp", pkg], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            click.echo(colorize(f"Error: {pkg} is not a valid RPM package.", color="red"))
            return

    # Check if any comparison flags are set; if none, compare all
    if not any([requires, provides, conflicts, files]):
        requires = provides = conflicts = files = True

    def get_rpm_query(package, query):
        """Extracts data from an RPM package using rpm -qp."""
        try:
            output = subprocess.check_output(
                ["rpm", "-qp", package, query], text=True
            ).splitlines()
            return sorted(output)
        except subprocess.CalledProcessError:
            return []

    def compare_lists(label, old_list, new_list):
        """Compares two lists and displays differences with colors."""
        with tempfile.NamedTemporaryFile("w") as old_file, tempfile.NamedTemporaryFile("w") as new_file:
            old_file.write("\n".join(old_list))
            old_file.flush()
            new_file.write("\n".join(new_list))
            new_file.flush()
            diff_output = subprocess.run(
                ["diff", "--unchanged-line-format=", "--old-line-format=- %L", "--new-line-format=+ %L", old_file.name, new_file.name],
                text=True,
                capture_output=True,
            ).stdout
            if diff_output.strip():
                click.echo(colorize(f"@@ {label} @@", color="cyan"))
                for line in diff_output.splitlines():
                    if line.startswith("-"):
                        click.echo(colorize(line, color="red"))
                    elif line.startswith("+"):
                        click.echo(colorize(line, color="green"))

    # Display package names
    click.echo(colorize(f"--- {os.path.basename(old_package)}", color="yellow"))
    click.echo(colorize(f"+++ {os.path.basename(new_package)}", color="yellow"))

    # Define comparison categories based on flags
    categories = []
    if requires:
        categories.append(("REQUIRES", "--requires"))
    if provides:
        categories.append(("PROVIDES", "--provides"))
    if conflicts:
        categories.append(("CONFLICTS", "--conflicts"))
    if files:
        categories.append(("FILE LIST", "--list"))

    # Compare selected categories
    for label, query in categories:
        old_data = get_rpm_query(old_package, query)
        new_data = get_rpm_query(new_package, query)
        compare_lists(label, old_data, new_data)
