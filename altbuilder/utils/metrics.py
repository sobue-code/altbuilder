import os
import json
import time
from datetime import datetime
from contextlib import contextmanager
import psutil
from ..utils.logger import logger
from ..exceptions import ToolError


class Metrics:
    def __init__(self, base_dir):
        """Initialize Metrics with a base directory for global tracking."""
        self.base_dir = base_dir

    def is_process_running(self, pid):
        """Check if a process with the given PID is running."""
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except psutil.NoSuchProcess:
            return False

    @contextmanager
    def track_build(self, package_name, build_log_dir=None, sandbox_name=None, command="build", version=None, release=None):
        """Track a package build process, saving temporary and result JSON files."""
        if not self.base_dir:
            raise ValueError("base_dir is required for tracking builds")

        temp_json_path = os.path.join(self.base_dir, "current_task.json")
        temp_result_path = (
            os.path.join(self.base_dir, "temp_build_result.json")
            if build_log_dir
            else None
        )
        own_pid = os.getpid()

        # Check if a task is already running
        if os.path.exists(temp_json_path):
            with open(temp_json_path, "r") as f:
                task = json.load(f)
            pid = task.get("pid")
            if pid and pid != own_pid and self.is_process_running(pid):
                logger.info(
                    f"A task is already running: {task['command']} (PID: {pid}, Sandbox: {task['sandbox_name']}). "
                    "Waiting for it to finish before starting build."
                )
                while self.is_process_running(pid):
                    time.sleep(1)
                if os.path.exists(temp_json_path):
                    os.remove(temp_json_path)
            else:
                logger.warning(f"Stale task file found for PID {pid}. Removing it.")
                if os.path.exists(temp_json_path):
                    os.remove(temp_json_path)

        start_time = datetime.now().isoformat()
        task_info = {
            "command": command,
            "package": package_name,
            "start_time": start_time,
            "pid": os.getpid(),
            "sandbox_name": sandbox_name or "unknown",
        }

        with open(temp_json_path, "w") as f:
            json.dump(task_info, f, indent=2)

        # Initialize temporary result file
        if build_log_dir:
            temp_result = {
                "package": package_name,
                "command": command,
                "start_time": start_time,
                "duration": 0.0,
                "success": False,
                "end_time": None,
                "sandbox_name": sandbox_name or "unknown",
                "version": version or "unknown",
                "release": release or "unknown",
            }
            with open(temp_result_path, "w") as f:
                json.dump(temp_result, f, indent=2)

        start_time_seconds = time.time()
        success = False
        try:
            yield
            success = True
        finally:
            duration = time.time() - start_time_seconds
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)
            if temp_result_path and os.path.exists(temp_result_path):
                os.remove(temp_result_path)

            if build_log_dir:
                result = {
                    "package": package_name,
                    "command": command,
                    "start_time": start_time,
                    "duration": duration,
                    "success": success,
                    "end_time": datetime.now().isoformat(),
                    "sandbox_name": sandbox_name or "unknown",
                    "version": version or "unknown",
                    "release": release or "unknown",
                }
                os.makedirs(build_log_dir, exist_ok=True)
                result_json_path = os.path.join(build_log_dir, "build_result.json")
                with open(result_json_path, "w") as f:
                    json.dump(result, f, indent=2)

            logger.info(
                f"Build of {package_name} {'succeeded' if success else 'failed'} in {duration:.2f}s"
            )

    @contextmanager
    def track_command(
        self, command, package_name=None, log_dir=None, sandbox_name=None
    ):
        """Track execution of any command, saving temporary and result JSON files."""
        if not self.base_dir:
            raise ValueError("base_dir is required for tracking commands")

        temp_json_path = os.path.join(self.base_dir, "current_task.json")
        temp_result_path = (
            os.path.join(self.base_dir, "temp_command_result.json") if log_dir else None
        )

        own_pid = os.getpid()
        
        # Check if a task is already running
        if os.path.exists(temp_json_path):
            with open(temp_json_path, "r") as f:
                task = json.load(f)
            pid = task.get("pid")
            if pid and pid != own_pid and self.is_process_running(pid):
                logger.info(
                    f"A task is already running: {task['command']} (PID: {pid}, Sandbox: {task['sandbox_name']}). "
                    "Waiting for it to finish before starting command."
                )
                while self.is_process_running(pid):
                    time.sleep(1)
                if os.path.exists(temp_json_path):
                    os.remove(temp_json_path)
            else:
                logger.warning(f"Stale task file found for PID {pid}. Removing it.")
                if os.path.exists(temp_json_path):
                    os.remove(temp_json_path)

        start_time = datetime.now().isoformat()
        task_info = {
            "command": command,
            "package": package_name or "unknown",
            "start_time": start_time,
            "pid": os.getpid(),
            "sandbox_name": sandbox_name or "unknown",
        }

        with open(temp_json_path, "w") as f:
            json.dump(task_info, f, indent=2)

        # Initialize temporary result file
        if log_dir:
            temp_result = {
                "command": command,
                "package": package_name or "unknown",
                "start_time": start_time,
                "duration": 0.0,
                "success": False,
                "end_time": None,
                "sandbox_name": sandbox_name or "unknown",
            }
            with open(temp_result_path, "w") as f:
                json.dump(temp_result, f, indent=2)

        start_time_seconds = time.time()
        success = False
        try:
            yield
            success = True
        finally:
            duration = time.time() - start_time_seconds
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)
            if temp_result_path and os.path.exists(temp_result_path):
                os.remove(temp_result_path)

            if log_dir:
                result = {
                    "command": command,
                    "package": package_name or "unknown",
                    "start_time": start_time,
                    "duration": duration,
                    "success": success,
                    "end_time": datetime.now().isoformat(),
                    "sandbox_name": sandbox_name or "unknown",
                }
                os.makedirs(log_dir, exist_ok=True)
                result_json_path = os.path.join(log_dir, "command_result.json")
                with open(result_json_path, "w") as f:
                    json.dump(result, f, indent=2)

            logger.info(
                f"Command '{command}' {'succeeded' if success else 'failed'} in {duration:.2f}s"
            )

    def get_current_task(self):
        """Retrieve information about the current task from the global tracking file."""
        if not self.base_dir:
            raise ValueError("base_dir is required")
        temp_json_path = os.path.join(self.base_dir, "current_task.json")
        if os.path.exists(temp_json_path):
            with open(temp_json_path, "r") as f:
                task = json.load(f)
            pid = task.get("pid")
            if pid and not self.is_process_running(pid):
                logger.warning(f"Stale task file found for PID {pid}. Removing it.")
                os.remove(temp_json_path)
                return None
            return task
        return None
