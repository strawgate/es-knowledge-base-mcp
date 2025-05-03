"""MCP Server for the Learn MCP Server."""

from collections.abc import Callable
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

from es_knowledge_base_mcp.models.base import ExportableModel
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME
from es_knowledge_base_mcp.models.settings import MemoryServerSettings
from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    KnowledgeBaseDocument,
    KnowledgeBaseDocumentProto,
    KnowledgeBaseSearchResultTypes,
)

from fastmcp.utilities.logging import get_logger

logger = get_logger(BASE_LOGGER_NAME).getChild("learn")

MEMORY_KNOWLEDGE_BASE_DEFAULT_ID = "default"
MEMORY_KNOWLEDGE_BASE_NAME = "Memory Knowledge Base"
MEMORY_KNOWLEDGE_DEFAULT_NAME = "Default Memory Knowledge Base"


class Memory(ExportableModel):
    """Memory model."""

    title: str = Field(default="A friendly `title` for the Memory.")
    content: str = Field(default="The Memory.")


class MemoryInitResponse(BaseModel):
    """Response model for initializing the memory server."""

    project_name: str
    memory_backend_id: str
    memory_count: int
    memories: list[KnowledgeBaseDocument] | None = None


class MemoryServer:
    """learn server for the learn tool."""

    knowledge_base_client: KnowledgeBaseClient

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

        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the learn server with the MCP."""
        mcp.add_tool(self.set_project)
        mcp.add_tool(self.response_wrapper(self.get_project_name))

        mcp.add_tool(self.encodings)
        mcp.add_tool(self.encoding)
        mcp.add_tool(self.update_encoding)
        mcp.add_tool(self.delete_encoding)
        mcp.add_tool(self.response_wrapper(self.recall))
        mcp.add_tool(self.response_wrapper(self.recall_last))

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass

    async def get_project_name(self, context: Context) -> str:
        """
        Get the project name from the context. If the project name is not set, it will return the default project name.

        Args:
            context (Context): The context containing the request context.

        Returns:
            str: The project name.
        """
        if project_name := context.request_context.lifespan_context.memory_context.project_name:
            return project_name

        raise ValueError("Project name not set in context. Please set the project name first using `set_project` method.")

    async def set_project(self, context: Context, project_name: str, return_memories: bool = True) -> MemoryInitResponse:
        """
        Set the project name for the memory server. The project name MUST BE SET before using any other
        methods in this server. This method will create a memory knowledge base if it does not already exist.
        The project name should typically be the current workspace or project name that the user is working on.

        Args:
            project_name (str): The name of the project.

        Returns:
            None.
        """

        if memory_knowledge_base := await self.knowledge_base_client.try_get_by_name(project_name):
            logger.debug(f"Using existing memory knowledge base: {memory_knowledge_base.name}")
            self.memory_knowledge_base = memory_knowledge_base
        else:
            knowledge_base_create_proto = KnowledgeBaseCreateProto(
                name=project_name,
                type="memory",
                data_source=f"Workspace-`{project_name}`",
                description=f"This is the memory knowledge base for {project_name}.",
            )

            memory_knowledge_base = await self.knowledge_base_client.create(
                knowledge_base_create_proto=knowledge_base_create_proto,
            )

        logger.debug(f"Project name set to: {project_name} using KB: {memory_knowledge_base.backend_id}")

        context.request_context.lifespan_context.memory_context.project_name = project_name
        context.request_context.lifespan_context.memory_context.knowledge_base = memory_knowledge_base

        memories: list[KnowledgeBaseDocument] | None = None

        if return_memories:
            memories = await self.knowledge_base_client.get_recent_documents(
                knowledge_base=memory_knowledge_base,
                results=50,
            )

        return MemoryInitResponse(
            project_name=project_name,
            memory_backend_id=memory_knowledge_base.backend_id,
            memory_count=memory_knowledge_base.doc_count,
            memories=memories,
        )

    def get_kb_from_context(self, context: Context) -> KnowledgeBase:
        """
        Get the knowledge base from the context.

        Args:
            context (Context): The context containing the request context.

        Returns:
            KnowledgeBase: The knowledge base associated with the current project.
        """
        if kb := context.request_context.lifespan_context.memory_context.knowledge_base:
            return kb

        raise ValueError("Knowledge base not found in context. Please set the project name first using `set_project` method.")

    async def encodings(
        self,
        context: Context,
        memories: list[Memory],
    ) -> None:
        """
        Encoding allows a perceived item of use or interest to be converted into a construct that can be stored
         within the memory bank and recalled later. You can encode as many memories at once as you would like but there
         is also no limit to how much information you can encode in a single memory. You can recall these encoded
         memories later using the `recall` method or by asking questions via the Ask server.

        Args:
            Memories: A list of Memories to encode.

        Returns:
            None: On success, this method does not return anything.

        Example:
            >>> await self.Memorys(Memorys=[Memory(title="Meeting Note", content="Discussed project plan"), Memory(title="Idea", content="New feature idea")])
        """

        await self.knowledge_base_client.insert_documents(
            knowledge_base=self.get_kb_from_context(context=context),
            documents=[KnowledgeBaseDocumentProto(title=memory.title, content=memory.content) for memory in memories],
        )

    async def encoding(
        self,
        context: Context,
        title: str = Field(default="A friendly `title` for the Memory."),
        content: str = Field(default="The Memory."),
    ) -> None:
        """
        Send a single Memory to be encoded into the memory knowledge base.

        Args:
            title: A friendly title for the Memory.
            content: The content of the Memory.

        Returns:
            None: On success, this method does not return anything.

        Example:
            >>> await self.Memory(title="Quick Memory", content="Remember to check the logs.")
        """

        await self.encodings(context=context, memories=[Memory(title=title, content=content)])

    async def recall(
        self,
        context: Context,
        questions: list[str],
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """
        Search the memory knowledge base.

        Args:
            questions (list[str]): A list of strings, where each string is a question to search for in the memory knowledge base.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each question.

        Example:
            >>> search_results = await self.recall(questions=["What was the project plan?", "Any ideas for new features?"])
            >>> for result in search_results:
            ...     print(f"Question: {result.phrase}")
            ...     for doc in result.results:
            ...         print(f"  - {doc.title} ({doc.score})")
        """

        return await self.knowledge_base_client.search_by_name(
            knowledge_base_names=[self.get_kb_from_context(context=context).name],
            phrases=questions,
        )

    async def recall_last(
        self,
        context: Context,
        count: int = 10,
    ) -> list[KnowledgeBaseDocument]:
        """
        Retrieve the most recent memories from the memory knowledge base.

        Args:
            count (int): The maximum number of recent memories to retrieve. Defaults to 10.

        Returns:
            list[KnowledgeBaseDocument]: A list of the most recent memories as KnowledgeBaseDocument objects.

        Example:
            >>> recent_memories = await self.recall_last(count=3)
            >>> for memory in recent_memories:
            ...     print(f"Title: {memory.title}, Content: {memory.content}")
        """

        return await self.knowledge_base_client.get_recent_documents(
            knowledge_base=self.get_kb_from_context(context=context),
            results=count,
        )

    async def update_encoding(
        self,
        context: Context,
        document_id: str,
        title: str,
        content: str,
    ) -> None:
        """
        Update an existing memory in the memory knowledge base.

        Args:
            document_id (str): The ID of the memory to update.
            title (str | None): sThe new title for the memory. If None, the title will not be updated.
            content (str | None): The new content for the memory. If None, the content will not be updated.

        Returns:
            KnowledgeBaseDocument: The updated memory document.

        Example:
            >>> updated_memory = await self.update_encoding(document_id="12345", title="Updated Memory", content="Updated content.")
            >>> print(f"Updated Memory: {updated_memory.title} - {updated_memory.content}")
        """

        await self.knowledge_base_client.update_document(
            knowledge_base=self.get_kb_from_context(context=context),
            document_id=document_id,
            document_update=KnowledgeBaseDocumentProto(
                title=title,
                content=content,
            ),
        )

    async def delete_encoding(
        self,
        context: Context,
        document_id: str,
    ) -> None:
        """
        Delete a memory from the memory knowledge base.

        Args:
            document_id (str): The ID of the memory to delete.

        Returns:
            None.

        Example:
            >>> await self.delete_encoding(document_id="12345")
        """

        await self.knowledge_base_client.delete_document(
            knowledge_base=self.get_kb_from_context(context=context),
            document_id=document_id,
        )
