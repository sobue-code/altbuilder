from ..utils.logger import logger

class DependencyResolver:
    def resolve(self, package):
        logger.info(f"Resolving dependencies for {package}")
