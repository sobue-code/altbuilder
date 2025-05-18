import subprocess
from .base import ToolAdapter
from ..utils.logger import logger


class GearAdapter(ToolAdapter):
    def run_command(self, cmd, **kwargs):
        logger.info(f"Running gear command: {' '.join(cmd)}")
        return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)

    def build(self, workdir, hasher_args):
        cmd = ["gear", "--verbose", "--commit", "--hasher", "--"] + hasher_args
        self.execute(cmd)
