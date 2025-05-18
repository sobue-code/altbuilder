import os
import shutil
import subprocess
from ..exceptions import EnvironmentError
from ..utils.logger import logger
from ..utils.helpers import get_host_arch, run_logged_command
from ..adapters.hasher import HasherAdapter


class Environment:
    def __init__(self, name, config, task_id=None, adapter=None):
        self.name = name
        self.config = config
        self.task_id = task_id
        self.environment_dir = os.path.join(
            config["environment_dir"], ".sandboxes", name
        )
        self.hasher_dir = os.path.join(self.environment_dir, "hasher")
        self.apt_conf = os.path.join(self.environment_dir, "apt.conf")
        self.sources_list = os.path.join(self.environment_dir, "sources.list")
        self.priorities = os.path.join(self.environment_dir, "priorities")
        self.adapter = adapter or HasherAdapter()

    def _generate_sources_list(self):
        """Generate sources.list based on branch, architecture and task_id."""
        lines = []
        mirror = self.config.get("mirror", "http://ftp.altlinux.org/pub/distributions")
        branch = self.config.get("branch", "Sisyphus")
        arch = self.config.get("arch", "x86_64")
        if mirror.startswith("file://"):
            lines.append(f"rpm {mirror}/{branch.lower()}/last {arch} classic")
            lines.append(f"rpm {mirror}/{branch.lower()}/last noarch classic")
            if arch == "x86_64":
                lines.append(f"rpm {mirror}/{branch.lower()}/last {arch}-i586 classic")
        else:
            lines.append(f"rpm [alt] {mirror} ALTLinux/{branch}/{arch} classic")
            lines.append(f"rpm [alt] {mirror} ALTLinux/{branch}/noarch classic")
            if arch == "x86_64":
                lines.append(
                    f"rpm [alt] {mirror} ALTLinux/{branch}/{arch}-i586 classic"
                )
        if self.task_id:
            mirror_task = self.config.get("mirror_task", "http://git.altlinux.org")
            lines.append(f"rpm {mirror_task} repo/{self.task_id}/{arch} task")
            logger.info(f"Added task repository for task_id={self.task_id}")
        else:
            logger.debug("No task_id provided, skipping task repository")
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
        conf = f"""
Dir::Etc::main "/dev/null";
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

    def init(self):
        """Initialize the sandbox with preliminary generation of configuration files."""
        logger.info(f"Initializing sandbox: {self.name}")
        if os.path.exists(self.environment_dir):
            logger.debug(f"Removing existing sandbox directory {self.environment_dir}")
            shutil.rmtree(self.environment_dir)
        os.makedirs(self.hasher_dir, exist_ok=True)
        self._generate_config_files()
        cmd = ["hsh", "--apt-config", self.apt_conf, "--initroot-only"]
        host_arch = get_host_arch()
        if self.config["arch"] != host_arch:
            run_logged_command(["rpm", "-q", "qemu-user-static"], check=True)
            cmd += [
                f'--with-qemu={self.config["arch"]}',
                f'--target={self.config["arch"]}',
            ]
        else:
            cmd += [f'--target={self.config["arch"]}']
        cmd.append(self.hasher_dir)
        run_logged_command(cmd, check=True)

    def exists(self):
        """Check if the sandbox exists."""
        return os.path.exists(os.path.join(self.hasher_dir, "chroot"))

    def clean(self):
        """Remove the sandbox directory and its contents."""
        logger.info(f"Cleaning sandbox: {self.name}")
        if not os.path.exists(self.environment_dir):
            raise EnvironmentError(f"Sandbox {self.name} does not exist.")
        try:
            cmd = ["hsh", "--cleanup-only", self.hasher_dir]
            run_logged_command(cmd, check=True)
            shutil.rmtree(self.environment_dir)
            logger.info(f"Sandbox {self.name} cleaned successfully.")
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

    def enable_internet(self):
        """Enable internet access in the sandbox by configuring DNS."""
        logger.info(f"Enabling internet in sandbox {self.name}")
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
            subprocess.run(
                cmd,
                input=f"echo 'nameserver {dns}' > /etc/resolv.conf\nexit\n".encode(),
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to configure DNS in sandbox: {e}")
            raise EnvironmentError(f"Failed to configure DNS: {e}")
        logger.info(f"Internet enabled in sandbox {self.name} with DNS: {dns}")
