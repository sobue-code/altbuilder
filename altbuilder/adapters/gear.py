import subprocess
import os
from .base import ToolAdapter
from ..utils.logger import logger
from ..utils.helpers import run_logged_command


class GearAdapter(ToolAdapter):
    def run_command(self, cmd, log_file=None, **kwargs):
        logger.info(f"Running gear command: {' '.join(cmd)}")
        return run_logged_command(
            cmd, check=True, real_time=True, log_file=log_file, quiet=True, **kwargs
        )

    def build(self, workdir, hasher_args, build_log_dir=None, rpmbuild_args=None):
        log_file = None
        if build_log_dir:
            os.makedirs(build_log_dir, exist_ok=True)
            log_file = os.path.join(build_log_dir, "gear_build.log")

        cmd = ["gear", "--verbose", "--commit", "--hasher", "--"]
        cmd.extend(hasher_args)
        if rpmbuild_args:
            cmd.extend(["--rpmbuild-args", " ".join(rpmbuild_args)])

        if build_log_dir:
            log_file = os.path.join(build_log_dir, "gear_build.log")
        return self.execute(cmd, log_file=log_file, cwd=workdir)
