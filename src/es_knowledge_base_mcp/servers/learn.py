"""MCP Server for the Learn MCP Server."""

from typing import Callable
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from es_knowledge_base_mcp.clients.crawl import Crawler, CrawlerSettings
from es_knowledge_base_mcp.clients.knowledge_base import KnowledgeBaseProto, KnowledgeBaseServer
from es_knowledge_base_mcp.models.settings import ElasticsearchSettings

from fastmcp.utilities.logging import get_logger

logger = get_logger("knowledge-base-mcp.learn")

MEMORY_KNOWLEDGE_BASE_NAME = "Memory Knowledge Base"


# region Web Docs
class LearnWebDocumentationRequestArgs(BaseModel):
    """Parameters for the web documentation request."""

    url: str = Field(default="The URL to crawl.")
    knowledge_base_name: str = Field(default="Name of the new or existing knowledge base to place the documents into.")
    knowledge_base_description: str = Field(default="Description of the new or existing knowledge base to place the documents into.")


class LearnServer:
    """learn server for the learn tool."""

    crawler: Crawler

    knowledge_base_server: KnowledgeBaseServer

    response_formatter: Callable

    def __init__(
        self, knowledge_base_server: KnowledgeBaseServer, crawler_settings: CrawlerSettings, elasticsearch_settings: ElasticsearchSettings, response_formatter: Callable | None = None
    ):
        self.knowledge_base_server = knowledge_base_server

        self.crawler = Crawler(settings=crawler_settings, elasticsearch_settings=elasticsearch_settings)

        self.response_formatter = response_formatter or (lambda response: response)

    async def async_init(self):
        """Initialize the learn server."""

        await self.crawler.async_init()

    async def async_shutdown(self):
        """Shutdown the learn server."""

        await self.crawler.async_shutdown()

        pass

    def register_with_mcp(self, mcp: FastMCP):
        mcp.add_tool(self.from_web_documentation_requests)
        mcp.add_tool(self.from_web_documentation_request)
        mcp.add_tool(self.from_web_documentation)

    async def git_repository(self, directory_path: str):
        pass

    async def directory_documentation(self, directory_path: str):
        raise NotImplementedError("Directory documentation is not implemented yet.")

    async def file_documentation(self, file_path: str):
        raise NotImplementedError("File documentation is not implemented yet.")

    async def from_web_documentation(self, url: str, knowledge_base_name: str, knowledge_base_description: str):
        """Starts a crawl job based on a seed page."""

        knowledge_base_proto = KnowledgeBaseProto(
            name=knowledge_base_name,
            source=url,
            description=knowledge_base_description,
        )

        return self.response_formatter(await self._from_web_documentation_request(knowledge_base_proto=knowledge_base_proto))

    async def from_web_documentation_request(self, knowledge_base_proto: KnowledgeBaseProto):
        """Starts a crawl job based on a seed page."""

        return self.response_formatter(await self._from_web_documentation_request(knowledge_base_proto=knowledge_base_proto))

    async def from_web_documentation_requests(self, knowledge_base_protos: list[KnowledgeBaseProto]):
        return self.response_formatter([
            await self._from_web_documentation_request(knowledge_base_proto=knowledge_base_proto)
            for knowledge_base_proto in knowledge_base_protos
        ])

    async def _from_web_documentation_request(self, knowledge_base_proto: KnowledgeBaseProto):
        """Starts a crawl job based on a seed page."""

        new_knowledge_base = await self.knowledge_base_server.create_kb_with_scope(scope="docs", knowledge_base_proto=knowledge_base_proto)

        url = new_knowledge_base.source

        assert new_knowledge_base is not None, f"Failed to create new knowledge base for {url}."

        logger.debug("Starting crawl job for URL: %s", url)

        crawl_parameters = self.crawler.derive_crawl_params(url)

        container_id = await self.crawler.crawl_domain(elasticsearch_index_name=new_knowledge_base.id, **crawl_parameters)

        return (new_knowledge_base, container_id)
