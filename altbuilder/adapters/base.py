from abc import ABC, abstractmethod
import subprocess
from ..exceptions import ToolError


class ToolAdapter(ABC):
    @abstractmethod
    def run_command(self, cmd, **kwargs):
        pass

    def execute(self, cmd, **kwargs):
        try:
            return self.run_command(cmd, **kwargs)
        except subprocess.CalledProcessError as e:
            raise ToolError(
                f"Command {cmd} failed with exit code {e.returncode}: {e.output}"
            )
