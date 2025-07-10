import os
import shutil
import shlex
from datetime import datetime
from ..exceptions import BuildError
from ..utils.logger import logger
from ..utils.metrics import Metrics
from ..utils.helpers import get_spec_metadata, copy_spec_to_log_dir
from ..adapters.gear import GearAdapter
from ..adapters.hasher import HasherAdapter


class BuildManager:
    def __init__(self, environment, gear_adapter=None, hasher_adapter=None):
        """Initialize BuildManager with environment and optional adapters."""
        self.environment = environment
        self.gear_adapter = gear_adapter or GearAdapter()
        self.hasher_adapter = hasher_adapter or HasherAdapter()
        self.metrics = Metrics(base_dir=self.environment.config["base_dir"])

    def build(
        self,
        build_target=None,
        is_src_rpm=False,
        apt_conf=None,
        only_srpm=False,
        build_log_dir=None,
        no_check=False,
        hsh_extra="",
        rpmbuild_extra="",
        command="build",
    ):
        """Build a package with the specified parameters."""
        if not self.environment.exists():
            self.environment.init()

        build_target = build_target or os.getcwd()
        # Get package metadata
        package_name, version, release = get_spec_metadata(build_target, is_src_rpm)
        if not package_name:
            package_name = (
                os.path.basename(build_target).replace(".src.rpm", "")
                if is_src_rpm
                else os.path.basename(build_target)
            )
            version = "unknown"
            release = "unknown"
        logger.info(f"Building {package_name} in {self.environment.name}")

        # If no build log directory specified, create one
        if not build_log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            build_log_dir = os.path.join(
                self.environment.config["build_logs_dir"],
                self.environment.name,
                package_name,
                timestamp,
            )
            os.makedirs(build_log_dir, exist_ok=True)

        apt_dir = os.path.join(build_log_dir, "apt")
        os.makedirs(apt_dir, exist_ok=True)

        # Save copies of sources.list, apt.conf, and priorities files in apt subdirectory
        sources_list_file = os.path.join(build_log_dir, "apt", "sources.list")
        apt_conf_file = os.path.join(build_log_dir, "apt", "apt.conf")
        priorities_file = os.path.join(build_log_dir, "apt", "priorities")

        if os.path.exists(self.environment.sources_list):
            shutil.copy2(self.environment.sources_list, sources_list_file)

        if os.path.exists(apt_conf or self.environment.apt_conf):
            shutil.copy2(apt_conf or self.environment.apt_conf, apt_conf_file)

        if os.path.exists(self.environment.priorities):
            shutil.copy2(self.environment.priorities, priorities_file)

        # Copy the spec file to the build log directory
        copy_spec_to_log_dir(build_target, is_src_rpm, build_log_dir, package_name)

        # Log file for gear or hasher command, named after the package
        log_file = os.path.join(build_log_dir, f"{package_name}.build.log")

        with self.metrics.track_build(
            package_name=package_name,
            build_log_dir=build_log_dir,
            sandbox_name=self.environment.name,
            command=command,
            version=version,
            release=release,
        ):
            if is_src_rpm:
                extra_args = shlex.split(hsh_extra) if hsh_extra else []
                # Prepare rpmbuild args for src.rpm builds
                rpmbuild_args = []
                if rpmbuild_extra:
                    rpmbuild_args.extend(shlex.split(rpmbuild_extra))
                if no_check:
                    rpmbuild_args.append("--without=check")
                if rpmbuild_args:
                    extra_args.append("--rpmbuild-args")
                    extra_args.append(" ".join(rpmbuild_args))
                self.hasher_adapter.build_from_srpm(
                    src_rpm=build_target,
                    workdir=self.environment.hasher_dir,
                    apt_config=apt_conf or self.environment.apt_conf,
                    arch=self.environment.config["arch"],
                    log_file=log_file,
                    extra_args=extra_args,
                    sandbox_name=self.environment.name,
                    package_name=package_name,
                )
            else:
                hasher_args = [
                    "hsh",
                    "--apt-config",
                    apt_conf or self.environment.apt_conf,
                    "--mount=/proc,/dev/pts,/dev/console",
                    "--verbose",
                    "--no-sisyphus-check=packager,gpg",
                    "--target",
                    self.environment.config["arch"],
                    self.environment.hasher_dir,
                    "--lazy-cleanup",
                ]
                if only_srpm:
                    hasher_args.append("--build-srpm-only")

                # Inject extra hsh arguments
                if hsh_extra:
                    hasher_args[1:1] = shlex.split(hsh_extra)

                # Prepare extra rpmbuild args
                rpmbuild_args = []
                if rpmbuild_extra:
                    rpmbuild_args.extend(shlex.split(rpmbuild_extra))
                if no_check:
                    rpmbuild_args.append("--without=check")

                self.gear_adapter.build(
                    workdir=build_target,
                    hasher_args=hasher_args,
                    build_log_dir=build_log_dir,
                    rpmbuild_args=rpmbuild_args if rpmbuild_args else None,
                    log_file=log_file,
                )

            logger.info(f"Build logs saved to: {build_log_dir}")
            return build_log_dir
