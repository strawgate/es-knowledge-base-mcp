"""MCP Server for the Learn MCP Server."""

import sys
from typing import Callable, List
from fastmcp import FastMCP
from pydantic import Field

from es_knowledge_base_mcp.models.base import ExportableModel
from es_knowledge_base_mcp.models.settings import MemoryServerSettings
from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    KnowledgeBaseDocument,
    KnowledgeBaseDocumentProto,
    KnowledgeBaseSearchResult,
)

from fastmcp.utilities.logging import get_logger

logger = get_logger("knowledge-base-mcp.learn")

MEMORY_KNOWLEDGE_BASE_DEFAULT_ID = "default"
MEMORY_KNOWLEDGE_BASE_NAME = "Memory Knowledge Base"
MEMORY_KNOWLEDGE_DEFAULT_NAME = "Default Memory Knowledge Base"


class Memory(ExportableModel):
    """Memory model."""

    title: str = Field(default="A friendly `title` for the Memory.")
    content: str = Field(default="The Memory.")


class MemoryServer:
    """learn server for the learn tool."""

    knowledge_base_client: KnowledgeBaseClient

    project_name: str
    project_source: str = "memory"

    response_wrapper: Callable

    # memory_knowledge_base: KnowledgeBase

    def __init__(
        self,
        knowledge_base_client: KnowledgeBaseClient,
        memory_server_settings: MemoryServerSettings,
        response_wrapper: Callable | None = None,
    ):
        self.knowledge_base_client = knowledge_base_client

        if project_name := memory_server_settings.project_name:
            self.project_name = project_name
        else:
            cwd_basename = self._get_current_working_directory().split("/")[-1]
            self.project_source = cwd_basename
            self.project_name = cwd_basename

        logger.debug(f"Memory Server initialized with project name: {self.project_name}")

        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the learn server with the MCP."""
        mcp.add_tool(self.response_wrapper(self.encodings))
        mcp.add_tool(self.response_wrapper(self.encoding))
        mcp.add_tool(self.response_wrapper(self.recall))
        mcp.add_tool(self.response_wrapper(self.recall_last))

    def _get_current_working_directory(self) -> str:
        """Get the current working directory."""
        return sys.modules["os"].getcwd()

    async def async_init(self):
        if memory_knowledge_base := await self.knowledge_base_client.try_get_by_name(self.project_name):
            logger.debug(f"Using existing memory knowledge base: {memory_knowledge_base.name}")
            self.memory_knowledge_base = memory_knowledge_base
        else:
            await self.create_memory_knowledge_base(name=self.project_name)

    async def create_memory_knowledge_base(self, name: str):
        """Create a new memory knowledge base."""

        knowledge_base_create_proto = KnowledgeBaseCreateProto(
            name=name,
            type="memory",
            data_source="memory",
            description="This is the memory knowledge base.",
        )

        new_knowledge_base = await self.knowledge_base_client.create(
            knowledge_base_create_proto=knowledge_base_create_proto,
        )

        assert new_knowledge_base is not None

        self.memory_knowledge_base = new_knowledge_base

    async def async_shutdown(self):
        pass

    async def encodings(
        self,
        memories: List[Memory],
    ) -> None:
        """
        Encoding allows a perceived item of use or interest to be converted into a construct that can be stored
         within the memory bank and recalled later. You can encode as many memories at once as you would like but there
         is also no limit to how much information you can encode in a single memory. You can recall these encoded
         memories later using the `recall` method or by asking questions via the Ask server.

        Args:
            Memories: A list of Memories to encode.

        Returns:
            None.

        Example:
            >>> await self.Memorys(Memorys=[Memory(title="Meeting Note", content="Discussed project plan"), Memory(title="Idea", content="New feature idea")])
        """

        await self.knowledge_base_client.insert_documents(
            knowledge_base=self.memory_knowledge_base,
            documents=[KnowledgeBaseDocumentProto(title=memory.title, content=memory.content) for memory in memories],
        )

    async def encoding(
        self,
        title: str = Field(default="A friendly `title` for the Memory."),
        content: str = Field(default="The Memory."),
    ) -> None:
        """
        Send a single Memory to be encoded into the memory knowledge base.

        Args:
            title: A friendly title for the Memory.
            content: The content of the Memory.

        Returns:
            None.

        Example:
            >>> await self.Memory(title="Quick Memory", content="Remember to check the logs.")
        """

        await self.encodings(memories=[Memory(title=title, content=content)])

    async def recall(
        self,
        questions: list[str],
    ) -> List[KnowledgeBaseSearchResult]:
        """
        Search the memory knowledge base.

        Args:
            questions (list[str]): A list of strings, where each string is a question to search for in the memory knowledge base.

        Returns:
            List[KnowledgeBaseSearchResult]: A list of search results, one for each question.

        Example:
            >>> search_results = await self.recall(questions=["What was the project plan?", "Any ideas for new features?"])
            >>> for result in search_results:
            ...     print(f"Question: {result.phrase}")
            ...     for doc in result.results:
            ...         print(f"  - {doc.title} ({doc.score})")
        """

        return await self.knowledge_base_client.search(
            knowledge_bases=[self.memory_knowledge_base],
            phrases=questions,
        )

    async def recall_last(
        self,
        count: int = 5,
    ) -> List[KnowledgeBaseDocument]:
        """
        Retrieve the most recent memories from the memory knowledge base.

        Args:
            count (int): The maximum number of recent memories to retrieve. Defaults to 5.

        Returns:
            List[KnowledgeBaseDocument]: A list of the most recent memories as KnowledgeBaseDocument objects.

        Example:
            >>> recent_memories = await self.recall_last(count=3)
            >>> for memory in recent_memories:
            ...     print(f"Title: {memory.title}, Content: {memory.content}")
        """

        return await self.knowledge_base_client.get_recent_documents(
            knowledge_base=self.memory_knowledge_base,
            results=count,
        )
