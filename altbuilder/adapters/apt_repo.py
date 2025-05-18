import subprocess
from .base import ToolAdapter
from ..utils.logger import logger

class AptRepoAdapter(ToolAdapter):
    def run_command(self, cmd, **kwargs):
        logger.info(f"Running apt-repo command: {' '.join(cmd)}")
        return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)

    def add(self, source):
        self.execute(['apt-repo', 'add', source])

    def list(self):
        return self.execute(['apt-repo', 'list']).stdout
