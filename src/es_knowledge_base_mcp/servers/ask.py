"""MCP Server for the Ask tool."""

from enum import Enum
from typing import Callable, List
from fastmcp import FastMCP
from pydantic import Field

from es_knowledge_base_mcp.interfaces.knowledge_base import KnowledgeBase, KnowledgeBaseClient, KnowledgeBaseSearchResult

from fastmcp.utilities.logging import get_logger


logger = get_logger("knowledge-base-mcp.ask")


class QuestionAnswerStyle(str, Enum):
    """Enum for answer styles. Representing the thoroughness of the answer: Concise, Normal, Comprehensive, or Exhaustive."""

    CONCISE = "concise"
    NORMAL = "normal"
    COMPREHENSIVE = "comprehensive"
    EXHAUSTIVE = "exhaustive"

    def to_search_size(self) -> int:
        """Converts the answer style to a search size."""
        return {
            self.CONCISE: 1,
            self.NORMAL: 4,
            self.COMPREHENSIVE: 8,
            self.EXHAUSTIVE: 12,
        }[self]


class AskServer:
    """Ask server for the Ask tool."""

    knowledge_base_client: KnowledgeBaseClient
    response_wrapper: Callable

    def __init__(self, knowledge_base_client: KnowledgeBaseClient, response_wrapper: Callable | None = None):
        """Initialize the Ask server."""
        self.knowledge_base_client = knowledge_base_client
        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the tools with the MCP server."""
        mcp.add_tool(self.response_wrapper(self.questions))
        mcp.add_tool(self.response_wrapper(self.questions_for_kb))
        mcp.add_tool(self.response_wrapper(self.documentation_available))

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass

    async def documentation_available(self) -> List[KnowledgeBase]:
        """
        Get a list of the documentation that's available.

        Returns:
            A list of KnowledgeBase objects that represent the available documentation.
        """
        knowledge_bases = await self.knowledge_base_client.get()

        docs_knowledge_bases = [knowledge_base for knowledge_base in knowledge_bases if knowledge_base.type == "docs"]

        return docs_knowledge_bases

    async def questions(
        self, questions: list[str], answer_style: QuestionAnswerStyle = QuestionAnswerStyle.NORMAL
    ) -> List[KnowledgeBaseSearchResult]:
        """
        Ask questions of the knowledge base. This is the main entry point for asking questions. Ask questions in plain English
          and the knowledge base will return the most relevant results. You can ask as many questions as you want, as often
            as you want. The knowledge base will return the most relevant results for each question.

        Args:
            questions: A list of strings, where each string is a question to ask the knowledge base.
            answer_style: The desired thoroughness of the answer. Defaults to QuestionAnswerStyle.NORMAL.

        Returns:
            A list of formatted strings, where each string contains the answer to a question.

        Example:
            >>> await self.questions(questions=["What is the capital of France?", "What is the highest mountain in the world?"], answer_style=QuestionAnswerStyle.COMPREHENSIVE)
            [
                "Question: What is the capital of France?\nResults:\n  - Title: Paris\n    URL: http://example.com/paris\n    Content: Paris is the capital and most populous city of France.",
                "Question: What is the highest mountain in the world?\nResults:\n  - Title: Mount Everest\n    URL: http://example.com/everest\n    Content: Mount Everest is the Earth's highest mountain above sea level."
            ]
        """

        search_results = await self.knowledge_base_client.search_all(
            phrases=questions, results=answer_style.to_search_size(), fragments=answer_style.to_search_size()
        )

        return search_results

    async def questions_for_kb(
        self,
        questions: list[str],
        knowledge_base_names: list[str] = Field(description="Names of the Knowledge Bases"),
        answer_style: QuestionAnswerStyle = QuestionAnswerStyle.NORMAL,
    ) -> List[KnowledgeBaseSearchResult]:
        """
        Ask questions of a specific knowledge base.

        Args:
            questions: A list of strings, where each string is a question to ask the knowledge base.
            knowledge_base_names: The names of the knowledge bases to query.
            answer_style: The desired thoroughness of the answer. Defaults to QuestionAnswerStyle.NORMAL.

        Returns:
            A list of KnowledgeBaseSearchResult objects, where each object contains the answer to a question.

        Example:
            >>> await self.questions_for_kb(questions=["What is the capital of France?"], knowledge_base_names=["my_docs"])
            [KnowledgeBaseSearchResult(phrase='What is the capital of France?', results=[...])]
        """

        search_results = await self.knowledge_base_client.search_by_names(
            phrases=questions,
            names=knowledge_base_names,
            results=answer_style.to_search_size(),
            fragments=answer_style.to_search_size(),
        )
        return search_results
