import os
import shutil
import shlex
from datetime import datetime
from ..exceptions import BuildError
from ..utils.logger import logger
from ..utils.metrics import Metrics
from ..adapters.gear import GearAdapter
from ..adapters.hasher import HasherAdapter


class BuildManager:
    def __init__(self, environment, gear_adapter=None, hasher_adapter=None):
        self.environment = environment
        self.gear_adapter = gear_adapter or GearAdapter()
        self.hasher_adapter = hasher_adapter or HasherAdapter()
        self.metrics = Metrics()

    def build(
        self,
        source_dir=None,
        apt_conf=None,
        only_srpm=False,
        build_log_dir=None,
        no_check=False,
        hsh_extra="",
        rpmbuild_extra="",
    ):
        if not self.environment.exists():
            self.environment.init()

        source_dir = source_dir or os.getcwd()
        package_name = os.path.basename(source_dir)
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

        # Save a copy of the sources.list, apt.conf, and priorities files in apt subdirectory
        sources_list_file = os.path.join(build_log_dir, "apt", "sources.list")
        apt_conf_file = os.path.join(build_log_dir, "apt", "apt.conf")
        priorities_file = os.path.join(build_log_dir, "apt", "priorities")

        if os.path.exists(self.environment.sources_list):
            shutil.copy2(self.environment.sources_list, sources_list_file)

        if os.path.exists(apt_conf or self.environment.apt_conf):
            shutil.copy2(apt_conf or self.environment.apt_conf, apt_conf_file)

        if os.path.exists(self.environment.priorities):
            shutil.copy2(self.environment.priorities, priorities_file)

        # Create log files
        hasher_log = os.path.join(build_log_dir, "hasher_build.log")
        # Log file for gear command, named after the package
        gear_log = os.path.join(build_log_dir, f"{package_name}.log")

        with self.metrics.track_build(package_name):
            hasher_args = [
                "hsh",
                "--apt-config",
                apt_conf or self.environment.apt_conf,
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
                workdir=source_dir,
                hasher_args=hasher_args,
                build_log_dir=build_log_dir,
                rpmbuild_args=rpmbuild_args if rpmbuild_args else None,
                log_file=gear_log,
            )

            logger.info(f"Build logs saved to: {build_log_dir}")
            return build_log_dir
