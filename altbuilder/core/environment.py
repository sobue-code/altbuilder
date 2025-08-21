import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime

from ..adapters.hasher import HasherAdapter
from ..exceptions import EnvironmentError
from ..utils import (generate_sources_list, get_host_arch, logger,
                     run_logged_command)
from ..utils.metrics import Metrics


class Environment:
    def __init__(self, name, config, task_id=None, adapter=None):
        """Initialize Environment with name, config, and optional task ID and adapter."""
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

    def shell(self, root=False, internet=False, log_dir=None):
        """Launch a shell inside the sandbox."""
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "shell", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        shell_log = os.path.join(log_dir, "shell.log")

        cmd = ["hsh-shell", "--wait-lock"]
        cmd.append("--mount=/proc")
        if root:
            cmd.append("--rooter")
        if internet:
            cmd.append("--mount=/dev/pts")
            os.environ["share_network"] = "yes"
            os.environ["share_ipc"] = "yes"
            self.enable_internet()
        cmd.append(self.hasher_dir)

        command_str = " ".join(cmd)
        logger.info(f"Launching shell for sandbox: {self.name}")
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            with open(shell_log, "a") as log_file:
                log_file.write(f"Launching shell: {command_str}\n")
            os.execvp(cmd[0], cmd)

    def enable_internet(self, log_dir=None):
        """Enable internet access in the sandbox by configuring DNS."""
        logger.info(f"Enabling internet in sandbox {self.name}")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "internet", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        internet_log = os.path.join(log_dir, "enable_internet.log")

        try:
            dns = (
                subprocess.check_output(
                    "grep '^nameserver' /etc/resolv.conf | awk '{print $2}' | head -n1",
                    shell=True,
                )
                .decode()
                .strip()
            )
            if not dns:
                logger.error("Failed to find DNS server.")
                raise EnvironmentError("DNS server not found.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to retrieve DNS server: {e}")
            raise EnvironmentError("Could not retrieve DNS server.")

        cmd = [
            "hsh-shell",
            "--wait-lock",
            "--rooter",
            "--mountpoints=/proc",
            self.hasher_dir,
        ]
        command_str = " ".join(cmd)
        logger.info("Writing DNS config inside sandbox")
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            try:
                with open(internet_log, "w") as log_file:
                    log_file.write(f"Setting DNS to {dns}\n")

                process = subprocess.run(
                    cmd,
                    input=f"echo 'nameserver {dns}' > /etc/resolv.conf\nexit\n",
                    check=True,
                    capture_output=True,
                    text=True,
                )

                with open(internet_log, "a") as log_file:
                    if process.stdout:
                        log_file.write(f"Output: {process.stdout}\n")
                    if process.stderr:
                        log_file.write(f"Error: {process.stderr}\n")
                    log_file.write("Internet access enabled successfully\n")

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to configure DNS in sandbox: {e}")
                with open(internet_log, "a") as log_file:
                    log_file.write(f"Error configuring DNS: {e}\n")
                    if e.stdout:
                        log_file.write(f"Output: {e.stdout}\n")
                    if e.stderr:
                        log_file.write(f"Error: {e.stderr}\n")
                raise EnvironmentError(f"Failed to configure DNS: {e}")

        logger.info(f"Internet enabled in sandbox {self.name} with DNS: {dns}")
        logger.info(f"Internet configuration logs saved to: {log_dir}")

    def install(self, packages, log_dir=None):
        """Install packages into the sandbox."""
        if not self.exists():
            logger.error(f"Sandbox {self.name} does not exist.")
            raise FileNotFoundError(f"Sandbox {self.name} does not exist.")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "install", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        install_log = os.path.join(log_dir, "install.log")

        cmd = ["hsh-install", "--wait-lock", self.hasher_dir] + list(packages)
        command_str = " ".join(cmd)
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            run_logged_command(cmd, check=True, log_file=install_log)
        logger.info(f"Packages installed in sandbox {self.name}")

    def run(self, command, log_dir=None):
        """Execute a command inside the sandbox."""
        if not self.exists():
            logger.error(f"Sandbox {self.name} does not exist.")
            raise FileNotFoundError(f"Sandbox {self.name} does not exist.")

        # Create a log directory if not provided
        if not log_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(
                self.config["build_logs_dir"], self.name, "run", timestamp
            )
            os.makedirs(log_dir, exist_ok=True)

        run_log = os.path.join(log_dir, "run.log")

        logger.info(f"Running command '{command}' in sandbox {self.name}")

        command_parts = shlex.split(command)
        cmd = [
            "hsh-run",
            "--wait-lock",
            "--mountpoints=/proc",
            self.hasher_dir,
            "--",
        ] + command_parts
        command_str = " ".join(cmd)
        with self.metrics.track_command(
            command=command_str, log_dir=log_dir, sandbox_name=self.name
        ):
            run_logged_command(cmd, check=True, quiet=True, log_file=run_log)

        logger.info(f"Command executed in sandbox {self.name}")

    def copy_to(self, src: str, dst: str):
        """Copy files from the host into the sandbox."""
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        logger.info(f"Copying {src} to {dst} in sandbox {self.name}")
        cmd = ["hsh-copy", "--wait-lock", "--workdir", self.hasher_dir, src, dst]
        command_str = " ".join(cmd)
        with self.metrics.track_command(command=command_str, sandbox_name=self.name):
            try:
                subprocess.run(cmd, check=True)
                logger.info(
                    f"Successfully copied {src} to {dst} in sandbox {self.name}"
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to copy {src} to {dst}: {e}")
                raise EnvironmentError(f"Failed to copy {src} to {dst}: {e}")

    def copy_from(self, src: str, dst: str):
        """Copy files or directories from the sandbox to the host using tar."""
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        exchange_dir = os.path.join(self.environment_dir, "exchange")
        mount_point = "/exchange"
        os.makedirs(exchange_dir, exist_ok=True)

        env = os.environ.copy()
        env["share_mount"] = "yes"

        try:
            # Ensure destination directory exists
            dst_dir = os.path.dirname(dst) if os.path.basename(dst) else dst
            os.makedirs(dst_dir, exist_ok=True)

            # Use tar to copy both files and directories
            cmd = [
                "hsh-run",
                "--wait-lock",
                f"--mount={exchange_dir}:{mount_point}",
                "--mountpoints=/proc",
                self.hasher_dir,
                "--",
                "tar",
                "-C",
                os.path.dirname(src) or ".",
                "-cf",
                "-",
                os.path.basename(src),
            ]
            command_str = " ".join(cmd)
            with self.metrics.track_command(
                command=command_str, sandbox_name=self.name
            ):
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    env=env,
                )
                extract = subprocess.run(
                    ["tar", "-C", dst, "-xf", "-"],
                    stdin=proc.stdout,
                    check=True,
                )
                proc.wait()
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, proc.args)

            logger.info(f"Successfully copied {src} from sandbox {self.name} to {dst}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to copy {src} from sandbox to host: {e}")
            raise EnvironmentError(f"Failed to copy {src} from sandbox to host: {e}")
        finally:
            # Clean up the exchange directory
            shutil.rmtree(exchange_dir, ignore_errors=True)
