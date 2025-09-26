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
    def track_build(
        self,
        package_name,
        build_log_dir=None,
        sandbox_name=None,
        command="build",
        version=None,
        release=None,
        rebuild_id=None,
    ):
        """Track a package build process, saving temporary and result JSON files.

        Optionally attach a ``rebuild_id`` so downstream consumers can correlate
        rebuild attempts.
        """
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
        task = self._load_task_file(temp_json_path)
        if task:
            pid = task.get("pid")
            if pid and pid != own_pid and self.is_process_running(pid):
                logger.info(
                    f"A task is already running: {task['command']} (PID: {pid}, Sandbox: {task['sandbox_name']}). "
                    "Waiting for it to finish before starting build."
                )
                while self.is_process_running(pid):
                    time.sleep(1)
                self._remove_file(temp_json_path)
            else:
                logger.warning(f"Stale task file found for PID {pid}. Removing it.")
                self._remove_file(temp_json_path)

        start_time = datetime.now().isoformat()
        task_info = {
            "command": command,
            "package": package_name,
            "start_time": start_time,
            "pid": os.getpid(),
            "sandbox_name": sandbox_name or "unknown",
            "rebuild_id": rebuild_id,
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
                "rebuild_id": rebuild_id,
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
            self._remove_file(temp_json_path)
            if temp_result_path:
                self._remove_file(temp_result_path)

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
                    "rebuild_id": rebuild_id,
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
        self,
        command,
        package_name=None,
        log_dir=None,
        sandbox_name=None,
        rebuild_id=None,
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
        task = self._load_task_file(temp_json_path)
        if task:
            pid = task.get("pid")
            if pid and pid != own_pid and self.is_process_running(pid):
                logger.info(
                    f"A task is already running: {task['command']} (PID: {pid}, Sandbox: {task['sandbox_name']}). "
                    "Waiting for it to finish before starting command."
                )
                while self.is_process_running(pid):
                    time.sleep(1)
                self._remove_file(temp_json_path)
            else:
                logger.warning(f"Stale task file found for PID {pid}. Removing it.")
                self._remove_file(temp_json_path)

        start_time = datetime.now().isoformat()
        task_info = {
            "command": command,
            "package": package_name or "unknown",
            "start_time": start_time,
            "pid": os.getpid(),
            "sandbox_name": sandbox_name or "unknown",
            "rebuild_id": rebuild_id,
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
                "rebuild_id": rebuild_id,
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
            self._remove_file(temp_json_path)
            if temp_result_path:
                self._remove_file(temp_result_path)

            if log_dir:
                result = {
                    "command": command,
                    "package": package_name or "unknown",
                    "start_time": start_time,
                    "duration": duration,
                    "success": success,
                    "end_time": datetime.now().isoformat(),
                    "sandbox_name": sandbox_name or "unknown",
                    "rebuild_id": rebuild_id,
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
        task = self._load_task_file(temp_json_path)
        if not task:
            return None

        pid = task.get("pid")
        if pid and not self.is_process_running(pid):
            logger.warning(f"Stale task file found for PID {pid}. Removing it.")
            self._remove_file(temp_json_path)
            return None
        return task

    def _load_task_file(self, path):
        """Safely load a task tracking file, removing it when corrupt."""
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as err:
            logger.warning(
                f"Failed to read task tracking file {path}: {err}. Removing it and continuing."
            )
            self._remove_file(path)
        return None

    @staticmethod
    def _remove_file(path):
        """Best-effort removal of a file."""
        try:
            os.remove(path)
        except FileNotFoundError:
            return
        except OSError as err:
            logger.warning(f"Failed to remove file {path}: {err}")
