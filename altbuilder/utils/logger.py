import os
import sys
from loguru import logger


def init_logger(sandbox_name=None, log_dir=None, config=None):
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
        log_file = os.path.join(log_dir, sandbox_name, "sandbox.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logger.add(
            log_file,
            rotation=log_config["rotation"],
            level=log_config["file_level"],
            format=log_config["format"],
        )


logger = logger
