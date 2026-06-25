import subprocess
from typing import List, Optional

import typer
from rich import print as rich_print

app = typer.Typer(
    name="merge-tag",
    help="Merge a given tag into current branch with automatic conflict resolution favoring the tag.",
)


def path_exists_in_revision(revision: str, path: str) -> bool:
    """
    Check if 'path' (file or directory) exists in the specified Git 'revision'.
    Returns True if exists, False otherwise.
    """
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", path],
        capture_output=True,
        text=True,
    )
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return bool(files)


def is_excluded_path(path: str, excluded_paths: List[str]) -> bool:
    """
    Returns True if the given path should be excluded (exact file match or inside excluded directory).
    """
    for excl in excluded_paths:
        excl_norm = excl.rstrip("/")
        if path == excl_norm:
            return True
        if path.startswith(excl_norm + "/"):
            return True
    return False


@app.command()
def merge_tag(
    tag: str = typer.Argument(..., help="Tag to merge into current branch."),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help=(
            "File or directory path to exclude from merge (can be used multiple times). "
            "Always excludes '.gear' directory by default."
        ),
    ),
):
    """
    Merge given TAG into current branch, automatically resolving conflicts
    in favor of the tag, except for excluded files/directories ('.gear' is always excluded).

    Example usage:
        altbuilder merge-tag v2.3.2 -e alt -e .bundles -e arrow.spec
    """
    # Always exclude .gear (even if not explicitly specified)
    excluded_paths = [".gear"]
    if exclude:
        for d in exclude:
            if d not in excluded_paths:
                excluded_paths.append(d)

    # Ensure working directory is clean (no unstaged or staged changes)
    try:
        subprocess.run(["git", "diff", "--quiet"], check=True)
        subprocess.run(["git", "diff", "--cached", "--quiet"], check=True)
    except subprocess.CalledProcessError:
        rich_print(
            "[red]Error: Working directory is not clean. Please commit or stash changes first.[/red]"
        )
        raise typer.Exit(code=1)

    # Start merge with no commit and no fast-forward
    try:
        subprocess.run(["git", "merge", "--no-commit", "--no-ff", tag], check=True)
    except subprocess.CalledProcessError:
        # Merge conflicts are expected, continue handling
        pass

    # Dynamically deinitialize all submodules (if any)
    result = subprocess.run(
        ["git", "submodule", "--quiet", "foreach", "echo $sm_path"],
        capture_output=True,
        text=True,
    )
    submodules = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for sub in submodules:
        subprocess.run(["git", "submodule", "deinit", "-f", sub], check=False)

    # Resolve conflicts by taking "theirs" version from the tag, excluding excluded paths
    try:
        result = subprocess.run(
            ["git", "ls-files", "-u"], capture_output=True, text=True, check=True
        )
        unmerged_files = sorted(
            set(line.split()[-1] for line in result.stdout.splitlines())
        )
    except Exception:
        unmerged_files = []

    for file in unmerged_files:
        if is_excluded_path(file, excluded_paths):
            continue

        exists_in_tag = (
            subprocess.call(
                ["git", "cat-file", "-e", f"{tag}:{file}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            == 0
        )
        if exists_in_tag:
            subprocess.run(["git", "checkout", "--theirs", file], check=True)
            subprocess.run(["git", "add", file], check=True)
        else:
            subprocess.run(["git", "rm", "-f", file], check=True)

    # Handle any leftover conflict markers (diff-filter=U)
    result2 = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True,
        text=True,
    )
    for file in result2.stdout.splitlines():
        try:
            subprocess.run(["git", "checkout", "--theirs", file], check=True)
            subprocess.run(["git", "add", file], check=True)
        except Exception:
            subprocess.run(["git", "rm", "-f", file], check=True)

    # Abort merge if there are still unresolved conflicts
    still_unmerged = subprocess.run(
        ["git", "ls-files", "-u"],
        capture_output=True,
        text=True,
    ).stdout
    if still_unmerged.strip():
        rich_print(
            "[red]Error: Some conflicts could not be resolved automatically. Resolve manually.[/red]"
        )
        subprocess.run(["git", "merge", "--abort"])
        raise typer.Exit(code=1)

    # Overwrite working tree completely from the tag (except excluded paths)
    subprocess.run(["git", "checkout", tag, "--", "."], check=True)

    # Restore excluded paths from pre-merge state HEAD@{1}, if they exist there
    for path in excluded_paths:
        if path_exists_in_revision("HEAD@{1}", path):
            subprocess.run(["git", "checkout", "HEAD@{1}", "--", path], check=True)

    # Remove files that exist in HEAD@{1} but not in the tag (except excluded paths)
    # This handles the case where 'git checkout tag -- .' doesn't delete files
    result_head = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD@{1}"],
        capture_output=True,
        text=True,
    )
    result_tag = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", tag],
        capture_output=True,
        text=True,
    )

    files_in_head = set(line.strip() for line in result_head.stdout.splitlines() if line.strip())
    files_in_tag = set(line.strip() for line in result_tag.stdout.splitlines() if line.strip())
    files_to_delete = files_in_head - files_in_tag

    for file in sorted(files_to_delete):
        if not is_excluded_path(file, excluded_paths):
            try:
                subprocess.run(["git", "rm", "-f", file], check=True, capture_output=True)
                rich_print(f"[yellow]Removed file not in tag: {file}[/yellow]")
            except subprocess.CalledProcessError:
                # File might already be deleted or not exist in working tree
                pass

    # Add everything, just in case
    subprocess.run(["git", "add", "."], check=True)

    # Finalize the merge, disable editor prompt
    exit_code = subprocess.call(["sh", "-c", "EDITOR=true git merge --continue"])
    if exit_code != 0:
        rich_print("[red]Error: Merge continue failed. Check 'git status'.[/red]")
        raise typer.Exit(code=1)

    # Verify if differences outside excluded paths exist
    diff_cmd = ["git", "diff", tag, "--"]
    for path in excluded_paths:
        path_strip = path.rstrip("/")
        diff_cmd.append(f":^{path_strip}/**")  # Exclude this path prefix from diff

    diff_output = subprocess.run(
        diff_cmd,
        capture_output=True,
        text=True,
    ).stdout

    if diff_output.strip():
        rich_print(
            "[yellow]Warning: Diff is not empty! There are unexpected differences outside excluded paths:[/yellow]"
        )
        rich_print(diff_output)
    else:
        rich_print("[green]Success: No differences outside excluded directories.[/green]")


if __name__ == "__main__":
    app()
