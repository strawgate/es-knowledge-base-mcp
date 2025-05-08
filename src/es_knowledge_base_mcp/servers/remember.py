"""MCP Server for the Learn MCP Server."""

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from fastmcp.utilities.logging import get_logger
from pydantic import BaseModel, Field

from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    KnowledgeBaseDocument,
    KnowledgeBaseDocumentProto,
    KnowledgeBaseSearchResultTypes,
)
from es_knowledge_base_mcp.models.base import ExportableModel
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME
from es_knowledge_base_mcp.models.settings import MemoryServerSettings

logger = get_logger(BASE_LOGGER_NAME).getChild("learn")

PROJECT_NAME_FIELD = Field(
    description="The name of the project for which the memory is being managed.", examples=["my-project", "another-project"]
)
QUESTIONS_FIELD = Field(
    description="A list of plain-language questions you'd like answers for from information in the memory knowledge base.",
    examples=[["What is the project plan?", "What are the key features?"]],
)
DOCUMENT_ID_FIELD = Field(description="The ID of the memory.", examples=["12345", "abcde"])
MEMORIES_FIELD = Field(
    description="A list of Memory objects to encode into the memory knowledge base.",
    examples=[
        [
            {"title": "Architectural Summary", "content": "The project is focused on..."},
            {"title": "Test Writing Guidelines", "content": "When writing tests, ensure that..."},
        ]
    ],
)
TITLE_FIELD = Field(
    description="A concise and descriptive title for the memory.",
    examples=["Architectural Summary", "Detailed rules for writing tests"],
)
CONTENT_FIELD = Field(
    description="The detailed content of the memory.",
    examples=["The project is focus on...", "When writing tests, ensure that..."],
)


class Memory(ExportableModel):
    """Memory model."""

    title: str = TITLE_FIELD
    content: str = CONTENT_FIELD


class MemoryInitResponse(BaseModel):
    """Response model for initializing the memory server."""

    project_name: str = Field(description="The name of the project. Typically the current workspace name.", examples=["my-project"])
    memory_backend_id: str = Field(description="The backend ID of the memory knowledge base.", examples=["default", "my-project-kb"])
    memory_count: int = Field(description="The number of memories in the knowledge base.", examples=[0, 10, 100])
    memories: list[KnowledgeBaseDocument] | None = Field(None, description="A list of recent memories, if requested.")


class MemoryServer(MCPMixin):
    """learn server for the learn tool."""

    knowledge_base_client: KnowledgeBaseClient

    def __init__(
        self,
        knowledge_base_client: KnowledgeBaseClient,
        memory_server_settings: MemoryServerSettings,
    ) -> None:
        """Initialize the MemoryServer."""
        self.knowledge_base_client = knowledge_base_client

        self.memory_server_settings = memory_server_settings

    @mcp_tool()
    async def get_project_name(self, context: Context) -> str:
        """Get the currently set project name.

        Returns:
            str: The project name.

        Raises:
            ValueError: If the project name is not set.
        """
        if project_name := context.request_context.lifespan_context.memory_context.project_name:
            return project_name

        msg = "Project name not set in context. Please set the project name first using `set_project` method."
        raise ValueError(msg)

    @mcp_tool()
    async def set_project(
        self,
        context: Context,
        project_name: str = PROJECT_NAME_FIELD,
        return_memories: bool = True,
    ) -> MemoryInitResponse:
        """Set the project name for the memory server.

        The project name MUST BE SET before using any other methods in this server.
        The project name should typically be the name of the current workspace (not full path) or project name that the user is working on.

        Returns:
            MemoryInitResponse: A response containing the project name, memory backend ID, memory count, and optionally recent memories.
        """
        if memory_knowledge_base := await self.knowledge_base_client.try_get_by_name(project_name):
            debug_msg = f"Using existing memory knowledge base: {memory_knowledge_base.name}"
            logger.debug(debug_msg)
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

        debug_msg = f"Project name set to: {project_name} using KB: {memory_knowledge_base.backend_id}"
        logger.debug(debug_msg)

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
        """Get the knowledge base from the context.

        Returns:
            KnowledgeBase: The knowledge base associated with the current project.

        Raises:
            ValueError: If the knowledge base is not found in the context.
        """
        if kb := context.request_context.lifespan_context.memory_context.knowledge_base:
            return kb

        msg = "Knowledge base not found in context. Please set the project name first using `set_project` method."
        raise ValueError(msg)

    @mcp_tool()
    async def encodings(
        self,
        context: Context,
        memories: list[Memory] = MEMORIES_FIELD,
    ) -> None:
        """Encode a memory into the memory bank.

        Encoding stores the provided information into the memory bank for later recall. You can encode as many memories at once
          as you would like. You can recall these encoded memories later using the `recall` method.
        """
        await self.knowledge_base_client.insert_documents(
            knowledge_base=self.get_kb_from_context(context=context),
            documents=[KnowledgeBaseDocumentProto(title=memory.title, content=memory.content) for memory in memories],
        )

    @mcp_tool()
    async def encoding(
        self,
        context: Context,
        title: str = TITLE_FIELD,
        content: str = CONTENT_FIELD,
    ) -> None:
        """Send a single Memory to be encoded into the memory knowledge base."""
        await self.encodings(context=context, memories=[Memory(title=title, content=content)])

    @mcp_tool()
    async def recall(
        self,
        context: Context,
        questions: list[str] = QUESTIONS_FIELD,
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Search the memory knowledge base.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each question.
        """
        return await self.knowledge_base_client.search_by_name(
            knowledge_base_names=[self.get_kb_from_context(context=context).name],
            phrases=questions,
        )

    @mcp_tool()
    async def recall_last(
        self,
        context: Context,
        count: int = Field(default=10, description="The number of most recent memories to retrieve.", examples=[10, 5, 3]),
    ) -> list[KnowledgeBaseDocument]:
        """Retrieve the most recent memories from the memory knowledge base.

        Returns:
            list[KnowledgeBaseDocument]: A list of the most recent memories as KnowledgeBaseDocument objects.
        """
        return await self.knowledge_base_client.get_recent_documents(
            knowledge_base=self.get_kb_from_context(context=context),
            results=count,
        )

    @mcp_tool()
    async def update_encoding(
        self,
        context: Context,
        document_id: str = DOCUMENT_ID_FIELD,
        title: str = TITLE_FIELD,
        content: str = CONTENT_FIELD,
    ) -> None:
        """Update an existing memory in the memory knowledge base.

        This method allows you to correct inaccurate, misleading or incomplete memories in the memory knowledge base.
        """
        await self.knowledge_base_client.update_document(
            knowledge_base=self.get_kb_from_context(context=context),
            document_id=document_id,
            document_update=KnowledgeBaseDocumentProto(
                title=title,
                content=content,
            ),
        )

    @mcp_tool()
    async def delete_encoding(
        self,
        context: Context,
        document_id: str = DOCUMENT_ID_FIELD,
    ) -> None:
        """Delete a memory from the memory knowledge base."""
        await self.knowledge_base_client.delete_document(
            knowledge_base=self.get_kb_from_context(context=context),
            document_id=document_id,
        )
