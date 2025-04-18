"""MCP Server for the Manage tool."""

from typing import Callable
from fastmcp import FastMCP

from es_knowledge_base_mcp.clients.knowledge_base import KnowledgeBaseProto, KnowledgeBaseServer

from fastmcp.utilities.logging import get_logger


logger = get_logger("knowledge-base-mcp.manage")


MANAGE_RESOURCE_PREFIX = "kb://"


class ManageServer:
    """Manage server for managing the Knowledge Base."""

    knowledge_base_server: KnowledgeBaseServer
    
    response_formatter: Callable

    def __init__(self, knowledge_base_server: KnowledgeBaseServer, response_formatter: Callable | None = None):
        self.knowledge_base_server = knowledge_base_server

        self.response_formatter = response_formatter or (lambda response: response)


    def register_with_mcp(self, mcp: FastMCP):
        """Register the tools with the MCP server."""

        mcp.add_tool(self.get)
        mcp.add_tool(self.get_by_id_or_name)
        mcp.add_tool(self.update)
        mcp.add_tool(self.update_name)
        mcp.add_tool(self.update_description)
        mcp.add_tool(self.delete)

        mcp.add_resource_fn(uri=MANAGE_RESOURCE_PREFIX + "entry", fn=self.knowledge_base_server.get_kb)


    async def get(self) -> str:
        """Get all knowledge base entries."""

        return self.response_formatter(await self.knowledge_base_server.get_kb())

    async def get_by_id_or_name(self, id_or_name: str) -> str:
        """Get a knowledge base entry."""

        knowledge_base = await self.knowledge_base_server.get_kb_by_id_or_name(id_or_name=id_or_name)

        return self.response_formatter(knowledge_base)

    async def delete(self, id_or_name: str):
        """Delete a knowledge base entry."""

        knowledge_base = await self.knowledge_base_server.get_kb_by_id_or_name(id_or_name=id_or_name)

        await self.knowledge_base_server.delete_kb(knowledge_base=knowledge_base)

    async def update(self, id_or_name: str, knowledge_base_proto: KnowledgeBaseProto):
        """Update a knowledge base entry."""

        knowledge_base = await self.knowledge_base_server.get_kb_by_id_or_name(id_or_name=id_or_name)

        await self.knowledge_base_server.update_kb(id=knowledge_base.id, knowledge_base_proto=knowledge_base_proto)

    async def update_name(self, id_or_name: str, new_name: str):
        """Update the name of a knowledge base entry."""
        knowledge_base = await self.knowledge_base_server.get_kb_by_id_or_name(id_or_name=id_or_name)

        knowledge_base_proto = KnowledgeBaseProto(
            name=new_name,
            source=knowledge_base.source,
            description=knowledge_base.description,
        )

        await self.knowledge_base_server.update_kb(id=knowledge_base.id, knowledge_base_proto=knowledge_base_proto)

    async def update_description(self, id_or_name: str, new_description: str):
        """Update the description of a knowledge base entry."""
        knowledge_base = await self.knowledge_base_server.get_kb_by_id_or_name(id_or_name=id_or_name)

        knowledge_base_proto = KnowledgeBaseProto(
            name=knowledge_base.name,
            source=knowledge_base.source,
            description=new_description,
        )

        await self.knowledge_base_server.update_kb(id=knowledge_base.id, knowledge_base_proto=knowledge_base_proto)

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass
