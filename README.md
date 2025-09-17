# altbuilder

## Table of Contents

* [Features](#features)
* [Requirements](#requirements)
* [Installation](#installation)
* [Quick Start](#quick-start)
* [Configuration](#configuration)
* [Commands](#commands)
* [Examples](#examples)

## Features

* **Sandbox Inventory & Cleanup**: List existing sandboxes and remove one or all.
* **Configuration Management**: View, edit, or (re)initialize altbuilder config.
* **Rebuild from Repo**: Fetch a package’s `src.rpm` and rebuild it inside a sandbox.
* **Task Controls**: Observe the current build task and stop it if needed.
* **Build Logs**: Explore and manage logs by sandbox or package.


### Required System Packages

```bash
# Essential build tools
sudo apt-get install hasher gear rpm-build

# Python and package management
sudo apt-get install python3 python3-pip
```

### Python Dependencies

Installed automatically when you install the package:

* `loguru` — structured logging
* `click`/`typer` ecosystem — CLI framework
* `tomli`, `tomli-w` — TOML parsing/writing
* `colorama`, `rich` — terminal formatting
* `psutil` — system/process utilities

## Installation

### From Source

```bash
git clone <repository-url>
cd altbuilder
pip install .
```

Verification:

```bash
altbuilder --help
```

## Quick Start

1. **Initialize or edit config** (sets defaults like branch, arch, paths):

```bash
altbuilder config --init
# then, if needed:
altbuilder config --edit
```

2. **List existing sandboxes**:

```bash
altbuilder list
```

3. **Rebuild a package** (fetches the corresponding `src.rpm` and rebuilds in a sandbox):

```bash
altbuilder rebuild package-name
# optionally target a specific sandbox:
altbuilder rebuild --task 123456 package-name
# tag the rebuild with an identifier for tracking in logs:
altbuilder rebuild --rebuild-id 2024-07-01a package-name
```

4. **Inspect logs**:

```bash
altbuilder logs --sandbox Sisyphus-x86_64 --package package-name
```

5. **Clean up**:

```bash
# remove one sandbox
altbuilder clean --sandbox Sisyphus-x86_64
# or remove all sandboxes
altbuilder clean --all
```

## Configuration

`altbuilder` uses a single TOML configuration with sane defaults and user overrides.

Typical structure (paths shown as examples):

```toml
branch = "Sisyphus"
arch = "x86_64"
mirror = "http://ftp.altlinux.org/pub/distributions"
mirror_task = "http://git.altlinux.org"
rdb_url = "https://rdb.altlinux.org"
packager = "Your Name <your.email@altlinux.org>"

base_dir = "/tmp/.private/username/altbuilder"
environment_dir = "/tmp/.private/username/altbuilder/environments"
build_logs_dir = "/home/username/.altbuilder/builds"

[logging]
level = "ERROR"
file_level = "DEBUG"
rotation = "10 MB"
format = "{time} | {level} | {message}"

# Optional per-sandbox overrides
[sandboxes.Sisyphus-x86_64]
branch = "Sisyphus"
arch = "x86_64"

[sandboxes.p11-x86_64]
branch = "p11"
arch = "x86_64"
```

## Commands

> Global option available to all commands:
>
> * `--sandbox, -s TEXT` — Sandbox name (e.g., `Sisyphus-x86_64`). Defaults to `<branch>-<arch>` from config.

### `list`

List existing sandboxes with metadata (and optional RPM details).

```bash
altbuilder list
altbuilder list --sandbox Sisyphus-x86_64
```

### `config`

Display, edit, or initialize configuration.

```bash
altbuilder config
altbuilder config --edit
altbuilder config --init
```

### `rebuild`

Fetch a package’s `src.rpm` from repositories and rebuild it inside the sandbox.

```bash
altbuilder rebuild package-name
altbuilder --sandbox Sisyphus-x86_64 rebuild package-name
altbuilder rebuild --rebuild-id nightly-42 package-name
```

Use `--rebuild-id` to attach a unique string to the rebuild. The identifier is stored
alongside build metadata and shown in `altbuilder logs` output.

### `logs`

Display or manage build logs.

```bash
# list recent logs
altbuilder logs
# filter by sandbox or package
altbuilder logs --sandbox Sisyphus-x86_64 --package package-name
# clean logs
altbuilder logs --clean
```

## Examples

**Rebuild a package using the default sandbox from config:**

```bash
altbuilder rebuild python3-module-foo
```

**Rebuild the same package in a specific sandbox:**

```bash
altbuilder --sandbox p11-x86_64 rebuild python3-module-foo
```

**Rebuild with an explicit identifier to track iterations:**

```bash
altbuilder rebuild --rebuild-id test-run-001 python3-module-foo
```

**Watch task status and stop if needed:**

```bash
altbuilder track
altbuilder stop
```

**Inspect logs for a package:**

```bash
altbuilder logs --sandbox Sisyphus-x86_64 --package python3-module-foo
```

**Clean up when done:**

```bash
altbuilder clean --sandbox Sisyphus-x86_64
# or wipe all:
altbuilder clean --all
```
