import os
import json
from altbuilder.core.environment import Environment


def read_sandbox_info(sandbox_path):
    info_path = os.path.join(sandbox_path, "hasher", "sandbox_info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path) as f:
                info = json.load(f)
            return info
        except Exception:
            return {}
    return {}


def get_sandbox_info(sandbox_name, config):
    sandbox_info_file = os.path.join(
        config["environment_dir"],
        sandbox_name,
        "hasher",
        "sandbox_info.json",
    )

    existing_info = None
    if os.path.exists(sandbox_info_file):
        try:
            existing_info = Environment.from_info_file(sandbox_info_file)
        except Exception:
            pass

    return existing_info
