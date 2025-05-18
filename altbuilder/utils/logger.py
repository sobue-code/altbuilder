import os
import sys
import time
from datetime import datetime
from loguru import logger


def init_logger(
    sandbox_name=None, log_dir=None, config=None, build_log=None, cmd_log=None
):
    """Initialize logger with settings from configuration."""
    logger.remove()
    log_config = (
        config["logging"]
        if config
        else {
            "level": "INFO",
            "file_level": "DEBUG",
            "rotation": "10 MB",
            "format": "{time} | {level} | {message}",
        }
    )

    # Add console handler
    logger.add(sys.stderr, level=log_config["level"], format=log_config["format"])

    # Add global log file handler
    if config and "base_dir" in config:
        global_log_file = os.path.join(config["base_dir"], "altbuilder.log")
        os.makedirs(os.path.dirname(global_log_file), exist_ok=True)
        logger.add(
            global_log_file,
            rotation=log_config["rotation"],
            level=log_config["file_level"],
            format=log_config["format"],
        )

    # Add sandbox-specific file handler if sandbox_name and log_dir are provided
    if sandbox_name and log_dir:
        os.makedirs(log_dir, exist_ok=True)

        # Use provided build log file or create a default one
        if not build_log:
            log_file = os.path.join(log_dir, "sandbox.log")
        else:
            log_file = build_log

        logger.add(
            log_file,
            rotation=log_config["rotation"],
            level=log_config["file_level"],
            format=log_config["format"],
        )

        # If a command log file is specified, create a specific logger for commands
        if cmd_log:
            cmd_logger = logger.bind(type="command")
            logger.add(
                cmd_log,
                rotation=log_config["rotation"],
                level=log_config["file_level"],
                format="{time} | CMD | {message}",
                filter=lambda record: record["extra"].get("type") == "command",
            )


def cmd_logger():
    """Get a logger specifically for command execution."""
    return logger.bind(type="command")


logger = logger
