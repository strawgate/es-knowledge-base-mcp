"""MCP Server for the Ask tool."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List
from fastmcp import FastMCP
from pydantic import BaseModel, Field
import yaml

from es_knowledge_base_mcp.clients.knowledge_base import KnowledgeBaseServer, SearchResult

from fastmcp.utilities.logging import get_logger


logger = get_logger("knowledge-base-mcp.ask")

class AskQuestionResponse(BaseModel):
    question: str = Field(description="The question.")
    results: List[SearchResult] = Field(description="The search results.")

    def __getstate__(self):
        """Only include the underlying dictionary in the state for serialization."""
        return self.__dict__
    
    def to_yaml(self) -> str:
        """Converts the search result to a string."""

        formatted = yaml.dump(
            {"Question": self.question, "Results": [result.to_dict() for result in self.results]},
            indent=2,
            width=10000,
            sort_keys=False,
            default_style="",
        )

        return formatted


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

    knowledge_base_server: KnowledgeBaseServer
    response_formatter: Callable

    def __init__(self, knowledge_base_server: KnowledgeBaseServer, response_formatter: Callable | None = None):
        """Initialize the Ask server."""
        self.knowledge_base_server = knowledge_base_server
        self.response_formatter = response_formatter or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the tools with the MCP server."""
        mcp.add_tool(self.questions)
        mcp.add_tool(self.questions_for_kb)

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass

    def _questions_to_queries(self, questions: list[str], answer_style: QuestionAnswerStyle) -> list[dict]:
        """Convert questions to queries."""

        fragments = results = answer_style.to_search_size()
        queries = [
            {
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"headings": {"query": question, "boost": 1}}},
                            {"semantic": {"field": "body", "query": question, "boost": 2}},
                        ]
                    }
                },
                "_source": ["title", "url"],
                "size": results,
                "highlight": {"number_of_fragments": fragments, "fragment_size": 500, "fields": {"body": {}}},
            }
            for question in questions
        ]

        return queries

    async def questions(self, questions: list[str], answer_style: QuestionAnswerStyle = QuestionAnswerStyle.NORMAL) -> list[str]:
        """Ask questions of the knowledge base."""

        question_results = zip(
            questions,
            await self.knowledge_base_server.search_kb_all(questions=questions, results=answer_style.to_search_size(), fragments=answer_style.to_search_size())
        )

        return self.response_formatter([AskQuestionResponse(question=question, results=results) for question, results in question_results])
        #return "\n".join([AskQuestionResponse(question=question, results=results).to_yaml() for question, results in question_results])

    async def questions_for_kb(
        self, questions: list[str], knowledge_base_name: str, answer_style: QuestionAnswerStyle = QuestionAnswerStyle.NORMAL
    )  -> str:
        """Ask questions of the knowledge base."""

        knowledge_base = await self.knowledge_base_server.get_kb_by_name(name=knowledge_base_name)

        question_results = zip(
            questions,
            await self.knowledge_base_server.search_kb(
                knowledge_base=knowledge_base, questions=questions, results=answer_style.to_search_size(), fragments=answer_style.to_search_size(
            ),
        ))

        return self.response_formatter([AskQuestionResponse(question=question, results=results) for question, results in question_results])
        #return "\n".join([AskQuestionResponse(question=question, results=results).to_yaml() for question, results in question_results])

