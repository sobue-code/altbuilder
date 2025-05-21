import os
import json
import shutil
import subprocess
from datetime import datetime
from ..exceptions import EnvironmentError
from ..utils import logger, get_host_arch, run_logged_command, generate_sources_list
from ..adapters.hasher import HasherAdapter


class Environment:
    def __init__(self, name, config, task_id=None, adapter=None):
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
        """Reads and returns sandbox info from JSON."""
        if not os.path.exists(self.info_file):
            raise EnvironmentError(f"Sandbox info file not found: {self.info_file}")
        with open(self.info_file, "r") as f:
            return json.load(f)

    @classmethod
    def from_info_file(cls, info_file, adapter=None):
        """Creates Environment object from sandbox_info.json file"""
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
        """Generate sources.list based on branch, architecture and task_id."""
        lines = generate_sources_list(self.branch, self.arch, self.task_id, self.config)
        with open(self.sources_list, "w") as f:
            f.write("\n".join(lines))

    def _generate_priorities(self):
        """Generate priorities file based on branch."""
        branch = self.config.get("branch", "Sisyphus").lower()
        release = (
            "altlinux-release-sis"
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
            shutil.rmtree(self.environment_dir)
        os.makedirs(self.hasher_dir, exist_ok=True)
        self._generate_config_files()

        # Save a copy of generated config files to the log directory
        if os.path.exists(self.sources_list):
            shutil.copy2(self.sources_list, os.path.join(log_dir, "sources.list"))
        if os.path.exists(self.apt_conf):
            shutil.copy2(self.apt_conf, os.path.join(log_dir, "apt.conf"))
        if os.path.exists(self.priorities):
            shutil.copy2(self.priorities, os.path.join(log_dir, "priorities"))

        cmd = ["hsh", "--apt-config", self.apt_conf, "--initroot-only"]
        host_arch = get_host_arch()
        if self.config["arch"] != host_arch:
            run_logged_command(
                ["rpm", "-q", "qemu-user-static"],
                check=True,
                log_file=os.path.join(log_dir, "qemu_check.log"),
            )
            cmd += [
                f'--with-qemu={self.config["arch"]}',
                f'--target={self.config["arch"]}',
            ]
        else:
            cmd += [f'--target={self.config["arch"]}']
        cmd.append(self.hasher_dir)
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
        try:
            cmd = ["hsh", "--cleanup-only", self.hasher_dir]
            run_logged_command(cmd, check=True, real_time=True, log_file=clean_log)
            shutil.rmtree(self.environment_dir)
            logger.info(f"Sandbox {self.name} cleaned successfully.")
            logger.info(f"Cleanup logs saved to: {log_dir}")
        except (subprocess.CalledProcessError, OSError) as e:
            logger.error(f"Failed to clean sandbox {self.name}: {e}")
            raise EnvironmentError(f"Failed to clean sandbox {self.name}: {e}")

    def shell(self, root=False, internet=False):
        """Launch a shell inside the sandbox."""
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")
        logger.info(f"Launching shell for sandbox: {self.name}")
        if internet:
            self.enable_internet()
        self.adapter.shell(self.hasher_dir, root, internet)

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
            "--rooter",
            "--mountpoints=/proc",
            self.hasher_dir,
        ]
        logger.info("Writing DNS config inside sandbox")
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

    def install(self, packages):
        """Installs packages into the sandbox."""
        if not self.exists():
            logger.error(f"Sandbox {self.name} does not exist.")
            raise FileNotFoundError(f"Sandbox {self.name} does not exist.")
        cmd = [
            "hsh-install",
            self.hasher_dir,
        ] + list(packages)
        run_logged_command(cmd, check=True)
        logger.info(f"Packages installed in sandbox {self.name}")

    def run(self, command):
        """Executes a command inside the sandbox."""
        if not self.exists():
            logger.error(f"Sandbox {self.name} does not exist.")
            raise FileNotFoundError(f"Sandbox {self.name} does not exist.")

        import shlex

        logger.info(f"Running command '{command}' in sandbox {self.name}")

        command_parts = shlex.split(command)

        cmd = ["hsh-run", "--mountpoints=/proc", self.hasher_dir, "--"] + command_parts

        run_logged_command(cmd, check=True, quiet=True)

        logger.info(f"Command executed in sandbox {self.name}")

    def copy_to(self, src: str, dst: str):
        """Copy files from the host into the sandbox.

        Args:
            src (str): Path to the source file or directory on the host.
            dst (str): Path inside the sandbox where the file or directory will be copied.
        """
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        logger.info(f"Copying {src} to {dst} in sandbox {self.name}")
        try:
            # Use hsh-copy to transfer files into the sandbox
            subprocess.run(
                ["hsh-copy", "--workdir", self.hasher_dir, src, dst],
                check=True,
            )
            logger.info(f"Successfully copied {src} to {dst} in sandbox {self.name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to copy {src} to {dst}: {e}")
            raise EnvironmentError(f"Failed to copy {src} to {dst}: {e}")

    def copy_from(self, src: str, dst: str):
        """Copy files or directories from the sandbox to the host.

        Args:
            src (str): Path inside the sandbox to the file or directory to copy.
            dst (str): Path on the host where the file or directory will be copied.
        """
        if not self.exists():
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")

        exchange_dir = os.path.join(self.environment_dir, "exchange")
        mount_point = "/exchange"
        os.makedirs(exchange_dir, exist_ok=True)

        env = os.environ.copy()
        env["share_mount"] = "yes"

        try:
            # Check if the source is a directory
            is_dir_proc = subprocess.run(
                [
                    "hsh-run",
                    "--mountpoints=/proc",
                    self.hasher_dir,
                    "--",
                    "test",
                    "-d",
                    src,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            is_dir = is_dir_proc.returncode == 0

            if is_dir:
                # Copy directory using tar to preserve structure
                os.makedirs(dst, exist_ok=True)
                proc = subprocess.Popen(
                    [
                        "hsh-run",
                        f"--mount={exchange_dir}:{mount_point}",
                        "--mountpoints=/proc",
                        self.hasher_dir,
                        "--",
                        "tar",
                        "-C",
                        src,
                        "-cf",
                        "-",
                        ".",
                    ],
                    stdout=subprocess.PIPE,
                    env=env,
                )
                extract = subprocess.run(
                    ["tar", "-C", dst, "-xf", "-"], stdin=proc.stdout
                )
                proc.wait()
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, proc.args)
            else:
                # Copy single file
                subprocess.run(
                    [
                        "hsh-run",
                        f"--mount={exchange_dir}:{mount_point}",
                        "--mountpoints=/proc",
                        self.hasher_dir,
                        "--",
                        "cp",
                        "-a",
                        src,
                        f"{mount_point}/",
                    ],
                    check=True,
                    env=env,
                )
                shutil.move(os.path.join(exchange_dir, os.path.basename(src)), dst)

            logger.info(f"Successfully copied {src} from sandbox {self.name} to {dst}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to copy {src} from sandbox to host: {e}")
            raise EnvironmentError(f"Failed to copy {src} from sandbox to host: {e}")
        finally:
            # Clean up the exchange directory
            shutil.rmtree(exchange_dir, ignore_errors=True)
