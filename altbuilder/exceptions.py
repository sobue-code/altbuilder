class AltBuilderError(Exception):
    """Base exception for altbuilder errors."""
    pass

class ConfigError(AltBuilderError):
    """Raised for configuration-related errors."""
    pass

class ToolError(AltBuilderError):
    """Raised for errors interacting with external tools."""

    def __init__(self, message: str, exit_code: int = None):
        super().__init__(message)
        self.exit_code = exit_code

class BuildError(AltBuilderError):
    """Raised for build process errors."""
    pass

class EnvironmentError(AltBuilderError):
    """Raised for sandbox environment errors."""
    pass


class RemoteError(AltBuilderError):
    """Raised for errors related to remote repository operations."""
    pass
