from es_knowledge_base_mcp.errors.server import KnowledgeBaseMCPBaseError


class LearnError(KnowledgeBaseMCPBaseError):
    """Raised when the crawler encounters an error."""

    msg: str = "Unknown Learn error"


class LearnWebDocumentationError(LearnError):
    """Raised when the crawler encounters an error while fetching web documentation."""

    msg: str = "Error while fetching web documentation for the URL to crawl"


class LearnWebDocumentationTooManyURLsError(LearnWebDocumentationError):
    """Raised when the crawler encounters too many URLs while fetching web documentation."""

    msg: str = "Too many URLs to fetch web documentation for the URL to crawl"


class LearnWebDocumentationHTTPError(LearnWebDocumentationError):
    """Raised when the crawler encounters an HTTP error while fetching web documentation."""

    msg: str = "Error while fetching web documentation for the URL to crawl"
