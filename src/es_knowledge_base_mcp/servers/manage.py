"""MCP Server for the Manage tool."""

from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    KnowledgeBaseUpdateProto,
)
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = get_logger(BASE_LOGGER_NAME).getChild("manage")


logger = get_logger(BASE_LOGGER_NAME).getChild("manage")


MANAGE_RESOURCE_PREFIX = "kb://"

BACKEND_ID_FIELD = Field(description="The backend ID of the knowledge base.")
NAME_FIELD = Field(description="The name of the knowledge base.")
KNOWLEDGE_BASE_CREATE_PROTO_FIELD = Field(description="The prototype object containing the details for the new knowledge base.")
KNOWLEDGE_BASE_UPDATE_PROTO_FIELD = Field(description="The prototype object containing the updated details.")


class ManageServer(MCPMixin):
    """Manage server for managing the Knowledge Base."""

    knowledge_base_client: KnowledgeBaseClient

    def __init__(self, knowledge_base_client: KnowledgeBaseClient) -> None:
        """Initialize the ManageServer with a KnowledgeBaseClient."""
        self.knowledge_base_client = knowledge_base_client

    @mcp_tool()
    async def create(self, knowledge_base_create_proto: KnowledgeBaseCreateProto = KNOWLEDGE_BASE_CREATE_PROTO_FIELD) -> KnowledgeBase:
        """Create a new knowledge base.

        Returns:
            KnowledgeBase: The created knowledge base object.
        """
        return await self.knowledge_base_client.create(knowledge_base_create_proto=knowledge_base_create_proto)

    @mcp_tool()
    async def get(self, name: str = NAME_FIELD) -> KnowledgeBase:
        """Get a knowledge base by its name.

        Returns:
            KnowledgeBase: The knowledge base object corresponding to the provided name.
        """
        return await self.knowledge_base_client.get_by_name(name=name)

    @mcp_tool()
    async def delete(self, name: str = NAME_FIELD) -> None:
        """Delete a knowledge base by its name."""
        await self.knowledge_base_client.delete_by_name(name=name)

    @mcp_tool()
    async def update(
        self, name: str = NAME_FIELD, knowledge_base_update: KnowledgeBaseUpdateProto = KNOWLEDGE_BASE_UPDATE_PROTO_FIELD
    ) -> None:
        """Update the description of an existing knowledge base by its name."""
        await self.knowledge_base_client.update_by_name(name=name, knowledge_base_update=knowledge_base_update)
