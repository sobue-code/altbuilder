import os
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

    def build(self, source_dir=None, apt_conf=None, only_srpm=False):
        if not self.environment.exists():
            self.environment.init()

        source_dir = source_dir or os.getcwd()
        package_name = os.path.basename(source_dir)
        logger.info(f"Building {package_name} in {self.environment.name}")

        with self.metrics.track_build(package_name):
            hasher_args = [
                "hsh",
                "--apt-config",
                apt_conf,
                "--verbose",
                "--no-sisyphus-check=packager,gpg",
                "--target",
                self.environment.config["arch"],
                self.environment.hasher_dir,
                "--lazy-cleanup",
            ]
            if only_srpm:
                hasher_args.append("--build-srpm-only")
            self.gear_adapter.build(workdir=source_dir, hasher_args=hasher_args)
