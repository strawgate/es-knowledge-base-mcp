"""MCP Server for the Manage tool."""

from typing import Callable
from fastmcp import FastMCP

from es_knowledge_base_mcp.interfaces.knowledge_base import KnowledgeBaseClient

from fastmcp.utilities.logging import get_logger

from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = get_logger(BASE_LOGGER_NAME).getChild("manage")


MANAGE_RESOURCE_PREFIX = "kb://"


class ManageServer:
    """Manage server for managing the Knowledge Base."""

    knowledge_base_client: KnowledgeBaseClient

    response_wrapper: Callable

    def __init__(self, knowledge_base_client: KnowledgeBaseClient, response_wrapper: Callable | None = None):
        self.knowledge_base_client = knowledge_base_client

        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the tools with the MCP server."""

        # Register the tools with the MCP server.
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.create))
        # mcp.add_tool(self.response_wrapper(self.knowledge_base_client.get))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.get_by_backend_id))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.get_by_name))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.delete_by_backend_id))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.delete_by_name))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.update_by_backend_id))
        mcp.add_tool(self.response_wrapper(self.knowledge_base_client.update_by_name))

        mcp.add_resource_fn(uri=MANAGE_RESOURCE_PREFIX + "entry", fn=self.knowledge_base_client.get)

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass
