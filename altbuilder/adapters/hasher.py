import os
from .base import ToolAdapter
from ..utils.logger import logger
from ..utils.metrics import Metrics
from ..utils.helpers import run_logged_command


class HasherAdapter(ToolAdapter):
    def __init__(self, base_dir=None):
        """Initialize HasherAdapter with Metrics instance."""
        super().__init__()
        self.metrics = Metrics(base_dir=base_dir)
        self.base_dir = base_dir

    def run_command(self, cmd, log_file=None, sandbox_dir=None, sandbox_name=None, package_name=None):
        """Run a hasher command with metrics tracking."""
        if not self.base_dir:
            raise ValueError("base_dir is required for command tracking")

        self.metrics.base_dir = self.base_dir
        command_str = " ".join(cmd)
        with self.metrics.track_command(
            command=command_str,
            log_dir=os.path.dirname(log_file) if log_file else None,
            sandbox_name=sandbox_name,
            package_name=package_name,
        ):
            logger.info(f"Executing: {command_str}")
            return run_logged_command(
                cmd,
                check=True,
                real_time=True,
                log_file=log_file,
            )

    def init_chroot(self, workdir, arch, apt_config, log_file=None, sandbox_name=None):
        """Initialize chroot environment with metrics tracking."""
        cmd = [
            "hsh",
            "--wait-lock",
            "--apt-config",
            apt_config,
            "--initroot-only",
            f"--target={arch}",
            workdir,
        ]
        return self.run_command(
            cmd,
            log_file=log_file,
            sandbox_dir=os.path.dirname(workdir),
            sandbox_name=sandbox_name,
        )

    def build(
        self,
        workdir,
        apt_config,
        arch,
        src_path,
        log_file=None,
        extra_args=None,
        sandbox_name=None,
    ):
        """Build a package from source with metrics tracking."""
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
        return self.run_command(
            cmd,
            log_file=log_file,
            sandbox_dir=os.path.dirname(workdir),
            sandbox_name=sandbox_name,
        )

    def build_from_srpm(
        self,
        src_rpm,
        workdir,
        apt_config,
        arch,
        log_file=None,
        extra_args=None,
        sandbox_name=None,
        package_name=None,
    ):
        """Build a package from an SRPM with metrics tracking."""
        cmd = [
            "hsh",
            "--wait-lock",
            "--mount=/proc,/dev/pts",
            "--apt-config",
            apt_config,
            "--verbose",
            f"--target={arch}",
            f"--workdir={workdir}",
            "--lazy-cleanup",
            src_rpm,
        ]
        if extra_args:
            cmd.extend(extra_args)
        return self.run_command(
            cmd,
            log_file=log_file,
            sandbox_dir=os.path.dirname(workdir),
            sandbox_name=sandbox_name,
            package_name=package_name,
        )

    def shell(self, workdir, root=False, internet=False):
        """Launch an interactive shell in the sandbox."""
        cmd = ["hsh-shell", "--wait-lock"]
        cmd.append("--mount=/proc")
        if root:
            cmd.append("--rooter")
        if internet:
            cmd.append("--mount=/dev/pts")
            os.environ["share_network"] = "yes"
            os.environ["share_ipc"] = "yes"
        cmd.append(workdir)
        command_str = " ".join(cmd)
        logger.info(f"Launching interactive shell: {command_str}")
        os.execvp(cmd[0], cmd)
