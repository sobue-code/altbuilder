import requests
from .logger import logger


def fetch_task_info(task_id, rdb_url=None):
    try:
        response = requests.get(f"{rdb_url}/api/task/task_info/{task_id}")
        response.raise_for_status()
        task_info = response.json()
        return task_info
    except requests.RequestException as e:
        logger.error(f"Error fetching task info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None
