from ..adapters.apt_repo import AptRepoAdapter
from ..utils.logger import logger

class RepoManager:
    def __init__(self, adapter=None):
        self.adapter = adapter or AptRepoAdapter()

    def add_repo(self, source):
        logger.info(f"Adding repository: {source}")
        self.adapter.add(source)

    def list_repos(self):
        return self.adapter.list()
