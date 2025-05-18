import subprocess
import os
from .base import ToolAdapter
from ..utils.logger import logger
from ..exceptions import ToolError


class HasherAdapter(ToolAdapter):
    def run_command(self, cmd, **kwargs):
        logger.info(f"Running hasher command: {' '.join(cmd)}")
        return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)

    def init_chroot(self, workdir, arch, apt_config):
        pass

    def build(self, workdir, apt_config, arch, src_path, extra_args=None):
        pass

    def shell(self, workdir, root=False, internet=False):
        cmd = ["hsh-shell"]
        if root:
            cmd.append("--rooter")
        if internet:
            cmd.append("--mount=/dev/pts")
            os.environ["share_network"] = "yes"
            os.environ["share_ipc"] = "yes"
        cmd.append(workdir)
        logger.info(f"Launching interactive shell: {' '.join(cmd)}")
        os.execvp(cmd[0], cmd)
