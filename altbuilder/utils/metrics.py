import time
from contextlib import contextmanager
from .logger import logger

class Metrics:
    def __init__(self):
        self.builds = []

    @contextmanager
    def track_build(self, package_name):
        start_time = time.time()
        success = False
        try:
            yield
            success = True
        finally:
            duration = time.time() - start_time
            self.builds.append({'package': package_name, 'duration': duration, 'success': success})
            logger.info(f"Build of {package_name} {'succeeded' if success else 'failed'} in {duration:.2f}s")

    def report(self):
        success_rate = sum(1 for b in self.builds if b['success']) / len(self.builds) if self.builds else 0
        avg_time = sum(b['duration'] for b in self.builds) / len(self.builds) if self.builds else 0
        return {'success_rate': success_rate, 'avg_build_time': avg_time}
