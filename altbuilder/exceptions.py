class AltBuilderError(Exception):
    """Base exception for altbuilder errors."""
    pass

class ConfigError(AltBuilderError):
    """Raised for configuration-related errors."""
    pass

class ToolError(AltBuilderError):
    """Raised for errors interacting with external tools."""
    pass

class BuildError(AltBuilderError):
    """Raised for build process errors."""
    pass

class EnvironmentError(AltBuilderError):
    """Raised for sandbox environment errors."""
    pass
