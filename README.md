# altbuilder

A command-line tool for managing ALT Linux sandboxes, building packages, and handling cross-compilation workflows. altbuilder simplifies the process of creating isolated build environments, managing dependencies, and building packages for different architectures.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Commands](#commands)
- [Cross-compilation](#cross-compilation)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Features

- **Sandbox Management**: Create, manage, and clean isolated build environments
- **Package Building**: Build packages from source directories or source RPMs
- **Cross-compilation**: Build packages for different architectures using QEMU emulation
- **Task Monitoring**: Track build progress and manage running tasks
- **Comprehensive Logging**: Detailed logging with build history and comparison
- **Flexible Configuration**: Hierarchical configuration system with user customization
- **Repository Integration**: Support for ALT Linux repositories and task-specific builds
- **Development Tools**: Utilities for Rust, Go, and Python dependency management

## Requirements

### System Requirements

- **Operating System**: ALT Linux (Sisyphus or stable branches)
- **Python**: 3.11 or higher
- **Architecture**: x86_64 (primary), with cross-compilation support for others

### Required System Packages

#### Core Dependencies

```bash
# Essential build tools
sudo apt-get install hasher gear rpm-build

# Python and package management
sudo apt-get install python3 python3-pip

# For cross-compilation (if needed)
sudo apt-get install qemu-user-static qemu-user-static-binfmt
```

#### Architecture-specific Packages

For cross-compilation to specific architectures:

```bash
# For ARM64/aarch64
sudo apt-get install qemu-user-static-aarch64 qemu-user-static-binfmt-aarch64

# For other architectures, install corresponding qemu-user-static-<arch> packages
```

#### Optional Dependencies

```bash
# File managers (for -f flag functionality)
sudo apt-get install mc  # or ranger

# Development tools
sudo apt-get install git golang rust-cargo  # for vendor update commands
```

### Python Dependencies

The following Python packages are automatically installed:

- `loguru` (>=0.7.3): Advanced logging
- `click` (>=8.2.0): Command-line interface framework
- `tomli` (>=2.2.1): TOML configuration parsing
- `tomli-w` (>=1.2.0): TOML configuration writing
- `colorama` (>=0.4.6): Cross-platform colored terminal text
- `rich` (>=14.0.0): Rich text and formatting for terminal
- `psutil` (>=7.0.0): System and process utilities

## Installation

### From Source

1. Clone the repository:

```bash
git clone <repository-url>
cd altbuilder
```

2. Install using Poetry (recommended):

```bash
pip install poetry
poetry install
```

3. Or install using pip:

```bash
pip install .
```

### Verify Installation

```bash
altbuilder --help
```

### Shell Completion (Optional but Recommended)

Enable tab completion for altbuilder commands, sandbox names, and package names.

#### For Bash:

```bash
# Install completion
altbuilder --install-completion bash

# Add to your ~/.bashrc (if not added automatically)
eval "$(_ALTBUILDER_COMPLETE=bash_source altbuilder)"

# Reload shell
source ~/.bashrc
```

#### For Zsh:

```bash
# Install completion
altbuilder --install-completion zsh

# Add to your ~/.zshrc (if not added automatically)
eval "$(_ALTBUILDER_COMPLETE=zsh_source altbuilder)"

# Reload shell
source ~/.zshrc
```

#### For Fish:

```bash
# Install completion
altbuilder --install-completion fish

# Reload shell
source ~/.config/fish/config.fish
```

**Note:** After enabling completion, you can use Tab to autocomplete:
- Sandbox names: `altbuilder -s <TAB>`
- Package names: `altbuilder path -s sandbox <TAB>`
- Command names and options

## Quick Start

### 1. Initialize Configuration

Generate a user-specific configuration:

```bash
altbuilder config --init
```

### 2. Create Your First Sandbox

Initialize a sandbox for the default branch and architecture:

```bash
altbuilder init
```

Or specify custom parameters:

```bash
altbuilder init --branch Sisyphus --arch x86_64
```

### 3. Build a Package

Build from a source directory:

```bash
cd /path/to/package/source
altbuilder build
```

Build from a source RPM:

```bash
altbuilder build package.src.rpm
```

Rebuild a package from repository:

```bash
altbuilder rebuild package-name
```

### 4. Manage Sandboxes

List all sandboxes:

```bash
altbuilder list
```

Enter a sandbox shell:

```bash
altbuilder shell
```

Clean up sandboxes:

```bash
altbuilder clean --all
```

## Configuration

### Configuration Hierarchy

altbuilder uses a hierarchical configuration system:

1. **Default configuration** (built-in defaults)
2. **User configuration** (`~/.altbuilder/config.toml`)
3. **Command-line overrides**

### Configuration File Structure

The configuration file (`~/.altbuilder/config.toml`) supports the following sections:

#### Global Settings

```toml
branch = "Sisyphus"                    # Default branch
arch = "x86_64"                        # Default architecture
mirror = "http://ftp.altlinux.org/pub/distributions"
mirror_task = "http://git.altlinux.org"
rdb_url = "https://rdb.altlinux.org"
packager = "Your Name <your.email@altlinux.org>"
base_dir = "/tmp/.private/username/altbuilder"
environment_dir = "/tmp/.private/username/altbuilder/environments"
build_logs_dir = "/home/username/.altbuilder/builds"
```

#### Sandbox-specific Settings

```toml
[sandboxes.Sisyphus-x86_64]
mirror = "http://ftp.altlinux.org/pub/distributions"
branch = "Sisyphus"
arch = "x86_64"

[sandboxes.p11-aarch64]
mirror = "http://ftp.altlinux.org/pub/distributions"
branch = "p11"
arch = "aarch64"
```

#### Logging Configuration

```toml
[logging]
level = "ERROR"              # Console log level
file_level = "DEBUG"         # File log level
rotation = "10 MB"           # Log rotation size
format = "{time} | {level} | {message}"
```

### Configuration Management

View current configuration:

```bash
altbuilder config
```

Edit configuration:

```bash
altbuilder config --edit
```

Reinitialize configuration:

```bash
altbuilder config --init --force
```

## Commands

### Sandbox Management

#### `altbuilder init`

Initialize a new sandbox environment.

Options:

- `--branch, -b`: Branch name (e.g., Sisyphus, p11)
- `--arch, -a`: Architecture (e.g., x86_64, aarch64)
- `--task, -t`: Attach task repository by ID
- `--reinit, -r`: Reinitialize existing sandbox
- `--sandbox, -s`: Custom sandbox name

#### `altbuilder list`

List all existing sandboxes with metadata.

Options:

- `--sandbox, -s`: Show details for specific sandbox
- `-f`: Open sandbox directory in file manager
- `--file-manager`: Specify file manager (mc, ranger)

#### `altbuilder path`

Get paths to RPM files or directories in sandboxes. Useful for quick access to built packages.

**Basic usage:**

```bash
# Get path to a specific package RPM
altbuilder path -s deepcool deepcool-digital-linux
# → /home/user/.altbuilder/environments/deepcool/hasher/repo/x86_64/RPMS.hasher/deepcool-digital-linux-0.9.0-alt1.x86_64.rpm

# Get path to source RPM
altbuilder path -s deepcool deepcool-digital-linux --srpm
# → /home/user/.altbuilder/environments/deepcool/hasher/repo/SRPMS.hasher/deepcool-digital-linux-0.9.0-alt1.src.rpm

# Get path to RPM directory (useful for cd command)
altbuilder path -s deepcool --dir
# → /home/user/.altbuilder/environments/deepcool/hasher/repo/x86_64/RPMS.hasher
```

**Practical examples:**

```bash
# Install locally built package
sudo apt-get install $(altbuilder path -s deepcool deepcool-digital-linux)

# Copy RPM to another location
cp $(altbuilder path -s deepcool deepcool) /tmp/

# Change to RPM directory
cd $(altbuilder path -s deepcool --dir)

# Use with tab completion (see Shell Completion section below)
altbuilder path -s <TAB>  # completes sandbox names
altbuilder path -s deepcool <TAB>  # completes package names in sandbox
```

Options:

- `--sandbox, -s`: Sandbox name (supports tab completion)
- `--srpm`: Return path to source RPM instead of binary RPM
- `--dir`: Return path to RPM directory instead of specific file
- `--no-debuginfo`: Exclude debuginfo packages from results

**Note:** You can also use the global `--sandbox/-s` flag: `altbuilder -s deepcool path`

**Behavior:**
- Without package name: returns all RPMs in the sandbox
- With package name: returns exact package match only (e.g., `python3-module-numpy` returns only the main package, not `-tests`, `-devel`, or `-debuginfo`)
- To get debuginfo package explicitly: use `python3-module-numpy-debuginfo` as package name

#### `altbuilder shell`

Enter an interactive shell in the sandbox.

Options:

- `--sandbox, -s`: Sandbox name
- `--root`: Run shell as root
- `--internet`: Enable internet access

#### `altbuilder clean`

Clean sandbox environments.

Options:

- `--sandbox, -s`: Specific sandbox to clean
- `--all`: Clean all sandboxes

#### `altbuilder install`

Install packages into sandbox.

```bash
altbuilder install package1 package2 ...
```

#### `altbuilder run`

Execute commands in sandbox.

```bash
altbuilder run -- command arg1 arg2
```

### Package Building

#### `altbuilder build`

Build a package from source directory or source RPM.

Options:

- `--arch, -a`: Target architecture
- `--branch, -b`: Branch name
- `--task, -t`: Task ID
- `--reinit, -r`: Reinitialize sandbox
- `--sandbox, -s`: Sandbox name
- `--no-check`: Skip package tests
- `--hsh-extra`: Extra flags for hsh
- `--rpmbuild-extra`: Extra flags for rpmbuild

#### `altbuilder rebuild`

Rebuild a package from repository.

```bash
altbuilder rebuild package-name
```

Options:

- `--sandbox, -s`: Sandbox name
- `--no-check`: Skip package tests
- `--rpmbuild-extra`: Extra rpmbuild flags

### Task Management

#### `altbuilder track`

Monitor current tasks.

Options:

- `--watch`: Continuously monitor (real-time updates)

#### `altbuilder stop`

Stop running tasks.

Options:

- `--force`: Force stop without confirmation

#### `altbuilder logs`

View build logs and history.

Options:

- `--sandbox, -s`: Filter by sandbox
- `--package, -p`: Filter by package
- `--json-output, -j`: Output in JSON format
- `--limit`: Limit number of results
- `-f`: Open logs in file manager
- `--clean`: Remove logs
- `--expand-history, -e`: Show detailed build history
- `--diff-spec, -d`: Compare spec files between builds

### Utility Commands

#### `altbuilder copy`

Copy files between host and sandbox.

```bash
# Copy to sandbox
altbuilder copy to-sandbox /host/path /sandbox/path

# Copy from sandbox
altbuilder copy from-sandbox /sandbox/path /host/path
```

#### `altbuilder rpmdiff`

Compare a locally built RPM with the latest package from ALT Linux repositories (or compare two given RPM files).  
The command can take a **package name** (it will fetch the remote RPM and find the local one in the sandbox) or two explicit RPM paths.

- Compare local sandbox build with remote package (by name):
  ```
  altbuilder rpmdiff -s Sisyphus-x86_64 python3-module-foo
  ```

- Compare **requires and provides only**:
  ```
  altbuilder rpmdiff -s Sisyphus-x86_64 --requires --provides python3-module-foo
  ```

- Compare two specific RPM files:
  ```
  altbuilder rpmdiff /path/to/old.rpm /path/to/new.rpm
  ```

#### Development Utilities

```bash
# Update Rust vendor dependencies
altbuilder rust-update-vendor [tag]

# Update Go vendor dependencies
altbuilder go-update-vendor [tag]

# Copy Python project dependencies
altbuilder copy-pyproject-deps

# Update git submodules
altbuilder update-submodules tag
```

## Cross-compilation

altbuilder supports cross-compilation using QEMU user-mode emulation.

### Setup for Cross-compilation

1. Install QEMU static binaries:

```bash
sudo apt-get install qemu-user-static qemu-user-static-binfmt
```

2. For specific architectures:

```bash
# ARM64/aarch64
sudo apt-get install qemu-user-static-aarch64 qemu-user-static-binfmt-aarch64

# Other architectures
sudo apt-get install qemu-user-static-<arch> qemu-user-static-binfmt-<arch>
```

3. Restart binfmt service:

```bash
sudo systemctl restart systemd-binfmt
```

### Verify Cross-compilation Setup

Check if QEMU is registered:

```bash
cat /proc/sys/fs/binfmt_misc/qemu-aarch64
```

Should show "enabled" status.

### Cross-compilation Examples

Build for ARM64:

```bash
altbuilder build --arch aarch64
```

Create ARM64 sandbox:

```bash
altbuilder init --arch aarch64 --branch Sisyphus
```

Rebuild package for different architecture:

```bash
altbuilder rebuild --sandbox Sisyphus-aarch64 package-name
```

## Examples

### Basic Workflow

1. **Setup environment:**

```bash
altbuilder config --init
altbuilder init
```

2. **Build a package:**

```bash
cd my-package/
altbuilder build
```

3. **Check build logs:**

```bash
altbuilder logs --package my-package
```

### Cross-compilation Workflow

1. **Setup cross-compilation:**

```bash
sudo apt-get install qemu-user-static qemu-user-static-aarch64 qemu-user-static-binfmt
sudo systemctl restart systemd-binfmt
```

2. **Create ARM64 sandbox:**

```bash
altbuilder init --arch aarch64 --sandbox my-aarch64-build
```

3. **Build for ARM64:**

```bash
altbuilder build --sandbox my-aarch64-build
```

### Development Workflow

1. **Update dependencies:**

```bash
altbuilder rust-update-vendor v1.0.0
altbuilder go-update-vendor v2.0.0
```

2. **Test in sandbox:**

```bash
altbuilder shell --internet
altbuilder run -- make test
```

3. **Compare package versions:**

```bash
altbuilder rpmdiff old-package.rpm new-package.rpm --files
```

## Troubleshooting

### Common Issues

#### Cross-compilation Fails with "Exec format error"

**Cause**: QEMU user-mode emulation not properly configured.

**Solution**:

```bash
sudo apt-get install qemu-user-static qemu-user-static-binfmt qemu-user-static-aarch64
sudo systemctl restart systemd-binfmt
```

Verify setup:

```bash
cat /proc/sys/fs/binfmt_misc/qemu-aarch64
```

### Debug Mode

Enable verbose logging:

```bash
altbuilder config --edit
# Set logging.level = "DEBUG"
```

View detailed logs:

```bash
tail -f ~/.altbuilder/altbuilder.log
```

### Getting Help

View command help:

```bash
altbuilder --help
altbuilder build --help
```

Check configuration:

```bash
altbuilder config
```
