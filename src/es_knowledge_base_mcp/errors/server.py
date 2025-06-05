"""Errors for the Knowledge Base MCP Server."""


class KnowledgeBaseMCPBaseError(Exception):
    """Base class for all Knowledge Base errors."""

    msg: str = "Generic Knowledge Base error"

    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.msg = message
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Return a user-friendly string representation."""
        cause = self.__cause__
        if cause:
            self.msg += f": {cause}"
        return self.msg


class ConfigurationError(KnowledgeBaseMCPBaseError):
    """Raised when there is a configuration error."""

    msg: str = "Unknown Configuration error"


class InvalidSettingError(KnowledgeBaseMCPBaseError):
    """Raised when a setting is invalid."""

    msg: str = "Invalid setting"

    def __init__(self, setting: str, error: str):
        super().__init__(f"Invalid setting: {setting}: {error}")
        self.setting = setting
        self.error = error
