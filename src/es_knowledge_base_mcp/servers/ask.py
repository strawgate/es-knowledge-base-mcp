"""MCP Server for the Ask tool."""

from enum import StrEnum

from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseSearchResultTypes,
)
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = get_logger(BASE_LOGGER_NAME).getChild("ask")


class QuestionAnswerStyle(StrEnum):
    """Enum for answer styles. Representing the thoroughness of the answer: Concise, Normal, Comprehensive, or Exhaustive."""

    CONCISE = "concise"
    NORMAL = "normal"
    COMPREHENSIVE = "comprehensive"
    EXHAUSTIVE = "exhaustive"

    def to_search_size(self) -> int:
        """Convert the answer style to a search size.

        Returns:
            An integer representing the number of results to return based on the answer style.
            - CONCISE: 1 result
            - NORMAL: 3 results
            - COMPREHENSIVE: 6 results
            - EXHAUSTIVE: 9 results
        """
        return {
            self.CONCISE: 1,
            self.NORMAL: 3,
            self.COMPREHENSIVE: 6,
            self.EXHAUSTIVE: 9,
        }[self]


QUESTIONS_FIELD = Field(
    description="A list of strings, where each string is a question to ask the knowledge base.",
    examples=[["What is the capital of France?", "What is the highest mountain in the world?"]],
)
ANSWER_STYLE_FIELD = Field(
    default=QuestionAnswerStyle.NORMAL,
    description="The desired thoroughness of the answer. Defaults to QuestionAnswerStyle.NORMAL.",
)


class AskServer(MCPMixin):
    """Ask server for the Ask tool."""

    knowledge_base_client: KnowledgeBaseClient

    def __init__(self, knowledge_base_client: KnowledgeBaseClient) -> None:
        """Initialize the Ask server."""
        self.knowledge_base_client = knowledge_base_client

    @mcp_tool()
    async def documentation_available(self) -> list[KnowledgeBase]:
        """Get a list of the documentation that's available.

        Returns:
            A list of KnowledgeBase objects that represent the available documentation.

        """
        knowledge_bases = await self.knowledge_base_client.get()

        return [knowledge_base for knowledge_base in knowledge_bases if knowledge_base.type == "docs"]

    @mcp_tool()
    async def questions(
        self,
        questions: list[str] = QUESTIONS_FIELD,
        answer_style: QuestionAnswerStyle = ANSWER_STYLE_FIELD,
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Ask questions of the knowledge base.

        This is the main entry point for asking questions. Ask questions in plain English and the knowledge base
        will return the most relevant results. You can ask as many questions as you want, as often
        as you want. The knowledge base will return the most relevant results for each question.

        Returns:
            A list of KnowledgeBaseSearchResultTypes objects, where each object contains the answer to a question.

        Raises:
            ValueError: If no questions are provided.
        """
        if len(questions) == 0:
            msg = "At least one question must be provided."
            raise ValueError(msg)

        return await self.knowledge_base_client.search(
            phrases=questions, results=answer_style.to_search_size(), fragments=answer_style.to_search_size()
        )

    @mcp_tool()
    async def questions_for_kb(
        self,
        knowledge_base_names: list[str],
        questions: list[str] = QUESTIONS_FIELD,
        answer_style: QuestionAnswerStyle = ANSWER_STYLE_FIELD,
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Ask questions of a specific knowledge base.  Ask questions in plain English and the knowledge base
        will return the most relevant results. You can ask as many questions as you want, as often
        as you want. The knowledge base will return the most relevant results for each question.

        Returns:
            A list of KnowledgeBaseSearchResultTypes objects, where each object contains the answer to a question.
        """
        return await self.knowledge_base_client.search_by_name(
            phrases=questions,
            knowledge_base_names=knowledge_base_names,
            results=answer_style.to_search_size(),
            fragments=answer_style.to_search_size(),
        )
