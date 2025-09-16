import json
import os
import shutil
import subprocess
from datetime import datetime

from altbuilder.exceptions import EnvironmentError
from altbuilder.utils import (generate_sources_list, get_host_arch, logger,
                              run_logged_command)
from altbuilder.utils.metrics import Metrics


class Environment:
    def __init__(self, name, config, task_id=None, adapter=None):
        """Initialize Environment with name, config, and optional task ID and adapter."""
        from altbuilder.adapters.hasher import HasherAdapter

        self.name = name
        self.config = config
        self.branch = config["branch"]
        self.arch = config["arch"]
        self.task_id = task_id
        self.environment_dir = os.path.join(config["environment_dir"], name)
        self.hasher_dir = os.path.join(self.environment_dir, "hasher")
        self.apt_conf = os.path.join(self.environment_dir, "apt.conf")
        self.sources_list = os.path.join(self.environment_dir, "sources.list")
        self.priorities = os.path.join(self.environment_dir, "priorities")
        self.adapter = adapter or HasherAdapter()
        self.info_file = os.path.join(
            self.environment_dir, "hasher", "sandbox_info.json"
        )
        self.metrics = Metrics(base_dir=config["base_dir"])

    def serialize(self):
        """Save sandbox info to JSON next to hasher."""
        info = {
            "name": self.name,
            "branch": self.branch,
            "arch": self.arch,
            "task_id": self.task_id,
            "config": self.config,
        }
        os.makedirs(os.path.dirname(self.info_file), exist_ok=True)
        with open(self.info_file, "w") as f:
            json.dump(info, f, indent=2)
        logger.info(f"Sandbox info saved to {self.info_file}")

    def get_info(self):
        """Read and return sandbox info from JSON."""
        if not os.path.exists(self.info_file):
            raise EnvironmentError(f"Sandbox info file not found: {self.info_file}")
        with open(self.info_file, "r") as f:
            return json.load(f)

    @classmethod
    def from_info_file(cls, info_file, adapter=None):
        """Create Environment object from sandbox_info.json file."""
        with open(info_file, "r") as f:
            info = json.load(f)
        return cls(
            name=info["name"],
            config=info["config"],
            task_id=info.get("task_id"),
            adapter=adapter,
        )

    def is_partially_initialized(self):
        """Check if the sandbox directory exists but is not fully initialized."""
        return os.path.isdir(self.environment_dir) and not self.exists()

    def exists(self):
        """Check if the sandbox is fully initialized."""
        return os.path.exists(os.path.join(self.hasher_dir, "sandbox_info.json"))

    def _generate_sources_list(self):
        """Generate sources.list based on branch, architecture, and task_id."""
        lines = generate_sources_list(self.branch, self.arch, self.task_id, self.config)
        with open(self.sources_list, "w") as f:
            f.write("\n".join(lines))

    def _generate_priorities(self):
        """Generate priorities file based on branch."""
        branch = self.config.get("branch", "Sisyphus").lower()
        release = (
            "altlinux-release-Sisyphus"
            if branch == "sisyphus"
            else f"altlinux-release-{branch}"
        )
        content = f"""Important:
basesystem
{release}
Required:
apt
"""
        with open(self.priorities, "w") as f:
            f.write(content)

    def _generate_apt_conf(self):
        """Generate apt.conf file with links to sources.list and priorities."""
        conf = f"""Dir::Etc::main "/dev/null";
Dir::Etc::parts "/var/empty";
Dir::Etc::sourcelist "{self.sources_list}";
Dir::Etc::pkgpriorities "{self.priorities}";
APT::Cache-Limit "201326592";
APT::Architecture "{self.config['arch']}";
Debug::pkgMarkInstall "true";
Debug::pkgProblemResolver "true";
"""
        with open(self.apt_conf, "w") as f:
            f.write(conf)

    def _generate_config_files(self):
        """Generate all necessary config files."""
        logger.debug(f"Generating config files for sandbox {self.name}")
        self._generate_sources_list()
        self._generate_priorities()
        self._generate_apt_conf()

    def init(self, log_dir=None):
        """Initialize the sandbox with preliminary generation of configuration files."""
        logger.info(f"Initializing sandbox: {self.name}")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "init", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        init_log = os.path.join(log_dir, "init.log")

        if os.path.exists(self.environment_dir):
            self.clean(log_dir=log_dir)
            logger.debug(f"Removing existing sandbox directory {self.environment_dir}")
            try:
                shutil.rmtree(self.environment_dir)
            except FileNotFoundError:
                logger.warning(f"Directory {self.environment_dir} already removed.")

        os.makedirs(self.hasher_dir, exist_ok=True)
        self._generate_config_files()

        # Save a copy of generated config files to the log directory
        if os.path.exists(self.sources_list):
            shutil.copy2(self.sources_list, os.path.join(log_dir, "sources.list"))
        if os.path.exists(self.apt_conf):
            shutil.copy2(self.apt_conf, os.path.join(log_dir, "apt.conf"))
        if os.path.exists(self.priorities):
            shutil.copy2(self.priorities, os.path.join(log_dir, "priorities"))

        cmd = ["hsh", "--wait-lock", "--apt-config", self.apt_conf, "--initroot-only"]
        host_arch = get_host_arch()
        if self.config["arch"] != host_arch and self.config["arch"] != "i586":
            run_logged_command(
                ["rpm", "-q", "qemu-user-static"],
                check=True,
                log_file=os.path.join(log_dir, "qemu_check.log"),
                quiet=True,
            )
            cmd += [
                f"--with-qemu={self.config['arch']}",
                f"--target={self.config['arch']}",
            ]
        else:
            cmd += [f"--target={self.config['arch']}"]
        cmd.append(self.hasher_dir)

        command_str = " ".join(cmd)
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            run_logged_command(cmd, check=True, real_time=True, log_file=init_log)
        self.serialize()
        logger.info(f"Sandbox initialization logs saved to: {log_dir}")

    def clean(self, log_dir=None):
        """Remove the sandbox directory and its contents."""
        logger.info(f"Cleaning sandbox: {self.name}")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "clean", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        clean_log = os.path.join(log_dir, "clean.log")

        if not os.path.exists(self.environment_dir):
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        cmd = ["hsh", "--wait-lock", "--cleanup-only", self.hasher_dir]
        command_str = " ".join(cmd)
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            try:
                run_logged_command(cmd, check=True, real_time=True, log_file=clean_log)
                shutil.rmtree(self.environment_dir)
                logger.info(f"Sandbox {self.name} cleaned successfully.")
                logger.info(f"Cleanup logs saved to: {log_dir}")
            except (subprocess.CalledProcessError, OSError) as e:
                logger.error(f"Failed to clean sandbox {self.name}: {e}")
                raise EnvironmentError(f"Failed to clean sandbox {self.name}: {e}")
