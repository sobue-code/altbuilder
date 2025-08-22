%define _unpackaged_files_terminate_build 1
%define oname altbuilder
%define module_name altbuilder

%def_with check

Name: python3-module-%oname
Version: 0.1.0
Release: alt1
Summary: Command-line tool for managing ALT Linux sandboxes and building packages
License: unlicense
Group: Development/Python3
Url: https://github.com/sobue-code/altbuilder
Vcs: https://github.com/sobue-code/altbuilder.git
BuildArch: noarch

Source0: %name-%version.tar
Source1: %pyproject_deps_config_name

%pyproject_runtimedeps_metadata
BuildRequires(pre): rpm-build-pyproject
%pyproject_builddeps_build

Requires: gear
Requires: hasher
Requires: git-core
Requires: rpm-build

%description
altbuilder is a command-line tool for managing ALT Linux sandboxes, building
packages, and handling cross-compilation workflows. It simplifies the process
of creating isolated build environments, managing dependencies, and building
packages for different architectures.

%prep
%setup
%pyproject_deps_resync_build
%pyproject_deps_resync_metadata

%build
%pyproject_build

%install
%pyproject_install

%check
# There are no tests

%files
%doc README.md
%_bindir/%module_name
%python3_sitelibdir/%module_name
%python3_sitelibdir/%{pyproject_distinfo %oname}

%changelog
* Mon Sep 15 2025 Aleksandr A. Voyt <sobue@altlinux.org> 0.1.0-alt1
- Initial build.
