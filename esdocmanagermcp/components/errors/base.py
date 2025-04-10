# esdocmanagermcp/components/errors/base.py
class ComponentError(Exception):
    """Base class for component-specific errors."""

    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.original_exception = original_exception


class CrawlError(ComponentError):
    """Base class for crawler errors."""

    pass


class ContainerStartFailedError(CrawlError):
    """Error during container start sequence (create, copy, start)."""

    pass


class ConfigGenerationError(CrawlError):
    """Error generating configuration."""

    pass


class ContainerNotFoundError(CrawlError):
    """Specific container ID not found."""

    pass


class SearchError(ComponentError):
    """Base class for searcher errors."""

    pass


class IndexListingError(SearchError):
    """Error listing indices."""

    pass


class IndexNotFoundError(SearchError):
    """Specific index not found during search or other operation."""

    pass


class SearchExecutionError(SearchError):
    """Error during the execution of an Elasticsearch search query."""

    pass

class UnknownSearchError(SearchError):
    """An unknown error occurred during the search operation."""

    pass