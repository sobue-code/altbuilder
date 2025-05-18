import subprocess
from .base import ToolAdapter
from ..utils.logger import logger
from ..utils.helpers import run_logged_command


class AptRepoAdapter(ToolAdapter):
    def run_command(self, cmd, log_file=None, **kwargs):
        logger.info(f"Running apt-repo command: {' '.join(cmd)}")
        return run_logged_command(
            cmd, check=True, real_time=True, log_file=log_file, **kwargs
        )

    def add(self, source, log_file=None):
        self.execute(["apt-repo", "add", source], log_file=log_file)

    def list(self, log_file=None):
        return self.execute(["apt-repo", "list"], log_file=log_file).stdout
