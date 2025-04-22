from es_knowledge_base_mcp.errors.server import KnowledgeBaseMCPBaseError


class AskError(KnowledgeBaseMCPBaseError):
    """Raised when the Ask operation encounters an error."""

    msg: str = "Unknown Ask error"


class AskQuestionAnswerError(AskError):
    """Raised when the Ask operation fails to answer a question."""

    msg: str = "Unable to answer the question"
