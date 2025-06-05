from es_knowledge_base_mcp.errors.server import KnowledgeBaseMCPBaseError


class CrawlerError(KnowledgeBaseMCPBaseError):
    """Raised when the crawler encounters an error."""

    msg: str = "Unknown Crawler error"

    def __init__(self, message: str):
        super().__init__(message)
        self.msg = message


class CrawlerValidationError(CrawlerError):
    """Raised when the crawler encounters an error validating the URL to crawl."""

    msg: str = "Error while validating the URL to crawl"


class CrawlerValidationTooManyURLsError(CrawlerValidationError):
    """Raised when the crawler encounters too many URLs while validating a url to crawl."""

    msg: str = "Too many URLs to crawl"


class CrawlerValidationHTTPError(CrawlerValidationError):
    """Raised when the crawler encounters an error validating the URL to crawl."""

    msg: str = "Error while validating the URL to crawl"


class CrawlerDockerError(CrawlerError):
    """Raised when the crawler encounters a Docker error."""

    msg: str = "Unknown Crawler Docker error"


class CrawlerDockerImageError(CrawlerDockerError):
    """Raised when the crawler encounters an error checking or pulling Docker images."""

    msg: str = "Error checking or pulling the Docker image for the Crawler"


class CrawlerDockerContainerError(CrawlerDockerError):
    """Raised when the crawler encounters a Docker container error."""

    msg: str = "Error starting the Docker container for the Crawler"


class CrawlerValidationNoIndexNofollowError(CrawlerValidationError):
    """Raised when a seed URL is marked with both noindex and nofollow."""
