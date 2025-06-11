import subprocess
import os
from .base import ToolAdapter
from ..utils.logger import logger
from ..utils.helpers import run_logged_command
from ..exceptions import ToolError


class HasherAdapter(ToolAdapter):
    def run_command(self, cmd, log_file=None, **kwargs):
        logger.info(f"Running hasher command: {' '.join(cmd)}")
        return run_logged_command(
            cmd, check=True, real_time=True, log_file=log_file, **kwargs
        )

    def init_chroot(self, workdir, arch, apt_config, log_file=None):
        cmd = [
            "hsh",
            "--wait-lock",
            "--apt-config",
            apt_config,
            "--initroot-only",
            f"--target={arch}",
            workdir,
        ]
        return self.execute(cmd, log_file=log_file)

    def build(
        self, workdir, apt_config, arch, src_path, log_file=None, extra_args=None
    ):
        cmd = [
            "hsh",
            "--wait-lock",
            "--mount=/proc,/dev/pts",
            "--apt-config",
            apt_config,
            "--verbose",
            f"--target={arch}",
            workdir,
        ]
        if extra_args:
            cmd.extend(extra_args)
        return self.execute(cmd, log_file=log_file, cwd=src_path)

    def build_from_srpm(
        self, src_rpm, workdir, apt_config, arch, log_file=None, extra_args=None
    ):
        cmd = [
            "hsh",
            "--wait-lock",
            "--mount=/proc,/dev/pts",
            "--apt-config",
            apt_config,
            "--verbose",
            f"--target={arch}",
            f"--workdir={workdir}",
            src_rpm,
        ]
        if extra_args:
            cmd.extend(extra_args)
        return self.execute(cmd, log_file=log_file)

    def shell(self, workdir, root=False, internet=False):
        cmd = ["hsh-shell", "--wait-lock"]
        cmd.append("--mount=/proc")
        if root:
            cmd.append("--rooter")
        if internet:
            cmd.append("--mount=/dev/pts")
            os.environ["share_network"] = "yes"
            os.environ["share_ipc"] = "yes"
        cmd.append(workdir)
        logger.info(f"Launching interactive shell: {' '.join(cmd)}")
        os.execvp(cmd[0], cmd)

    def install(self, workdir, *packages):
        """Installs packages in the sandbox."""
        cmd = ["hsh-install", "--wait-lock", workdir] + list(packages)
        run_logged_command(cmd, check=True)
        logger.info(f"Packages installed in sandbox {self.name}")
