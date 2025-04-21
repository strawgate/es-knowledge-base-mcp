class KnowledgeBaseError(Exception):
    """Raised when the Knowledge Base encounters an error."""

    msg: str = "Unknown Knowledge Base error"


class KnowledgeBaseNotFoundError(KnowledgeBaseError):
    """Raised when the Knowledge Base is not found."""


class KnowledgeBaseNonUniqueError(KnowledgeBaseError):
    """Raised when multiple Knowledge Bases are found when only one is expected."""

    msg: str = "Multiple Knowledge Bases found, expected one"


class KnowledgeBaseAlreadyExistsError(KnowledgeBaseError):
    """Raised when the Knowledge Base already exists."""

    msg: str = "Knowledge Base already exists"


class KnowledgeBaseCreationError(KnowledgeBaseError):
    """Raised when creating the knowledge base fails."""

    msg: str = "Knowledge Base could not be created"


class KnowledgeBaseDeletionError(KnowledgeBaseError):
    """Raised when deleting the knowledge base fails."""

    msg: str = "Knowledge Base could not be deleted"


class KnowledgeBaseUpdateError(KnowledgeBaseError):
    """Raised when updating the knowledge base fails."""

    msg: str = "Knowledge Base could not be updated"


class KnowledgeBaseRetrievalError(KnowledgeBaseError):
    """Raised when retrieving the knowledge base fails."""

    msg: str = "Knowledge Base could not be retrieved"


class KnowledgeBaseSearchError(KnowledgeBaseError):
    """Raised when searching the knowledge base fails."""

    msg: str = "Knowledge Base search failed"
