"""MCP Server for the Learn MCP Server."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from es_knowledge_base_mcp.clients.crawl import Crawler
from es_knowledge_base_mcp.clients.web import extract_urls_from_webpage
from es_knowledge_base_mcp.errors.crawler import CrawlerError, CrawlerValidationError
from es_knowledge_base_mcp.errors.knowledge_base import KnowledgeBaseCreationError
from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    kb_data_source_field,
    kb_description_field,
    kb_name_field,
)
from es_knowledge_base_mcp.models.base import ExportableModel
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME
from es_knowledge_base_mcp.models.settings import CrawlerSettings, ElasticsearchSettings

logger = get_logger(BASE_LOGGER_NAME).getChild("learn")


URL_FIELD = Field(description="The URL of the webpage to extract URLs from.")
LEARN_WEB_DOCUMENTATION_PROTO_FIELD = Field(
    description="The LearnWebDocumentationProto object containing the parameters for learning from web documentation.",
)
MAX_CHILD_PAGE_LIMIT_FIELD = Field(default=500, description="The maximum allowed number of child pages to crawl.")


# region Web Docs


class CrawlStartSuccess(ExportableModel):
    """Represents a successful crawl initiation."""

    url: str = Field(description="The URL for which the crawl was initiated.")
    knowledge_base_id: str = Field(description="The ID of the knowledge base created or updated.")
    container_id: str = Field(description="The ID of the started crawl container.")
    status: str = Field(default="success", description="The status of the crawl initiation.")


class CrawlStartFailure(ExportableModel):
    """Represents a failed crawl initiation."""

    url: str = Field(description="The URL for which the crawl initiation failed.")
    status: str = Field(default="failure", description="The status of the crawl initiation.")
    reason: str = Field(description="The reason for the crawl initiation failure.")


class LearnWebDocumentationProto(ExportableModel):
    """Represents the parameters for learning from web documentation."""

    name: str = kb_name_field
    version: str = Field(
        default="latest", description="The version of the documentation you are sourcing from.", examples=["latest", "v1.0", "v2.1"]
    )
    data_source: str = kb_data_source_field
    exclude_paths: list[str] = Field(
        default_factory=list,
        description="A list of paths to exclude from the crawl. Not normally necessary. For excluding certain sections of a website.",
        examples=[["/changelog", "/docs/old", "/docs/v1"]],
    )
    overwrite: bool = Field(
        default=True,
        description="Overwrite the existing knowledge base if it already exists. Defaults to True.",
    )
    description: str = kb_description_field

    def to_knowledge_base_create_proto(self) -> KnowledgeBaseCreateProto:
        """Convert the LearnWebDocumentationProto to a KnowledgeBaseCreateProto.

        Returns:
            KnowledgeBaseCreateProto: The converted knowledge base creation prototype.
        """
        return KnowledgeBaseCreateProto(
            name=self.name,
            data_source=self.data_source,
            description=self.description,
            type="docs",
        )


CrawlResult = CrawlStartSuccess | CrawlStartFailure


class LearnServer(MCPMixin):
    """MCP Server for the Learn tool.

    Provides tools for learning from various data sources, such as web documentation.
    """

    crawler: Crawler

    knowledge_base_client: KnowledgeBaseClient

    def __init__(
        self,
        knowledge_base_client: KnowledgeBaseClient,
        crawler_settings: CrawlerSettings,
        elasticsearch_settings: ElasticsearchSettings,
    ) -> None:
        """Initialize the LearnServer with a KnowledgeBaseClient and crawler settings."""
        self.knowledge_base_client = knowledge_base_client

        self.crawler = Crawler(settings=crawler_settings, elasticsearch_settings=elasticsearch_settings)

    # region Error Handling
    @classmethod
    @asynccontextmanager
    async def connection_context_manager(cls, learn_server: "LearnServer") -> AsyncGenerator["LearnServer", None]:
        """Context manager for Elasticsearch connection errors.

        Yields:
            LearnServer: An instance of LearnServer with an active crawler connection.
        """
        try:
            await learn_server.crawler.async_init()
            yield learn_server
        finally:
            await learn_server.crawler.async_shutdown()

    # endregion Error Handling

    # region Tools
    async def git_repository(self, directory_path: str) -> None:
        """Crawl a git repository for documentation."""
        error = "Git repository documentation is not implemented yet."
        raise NotImplementedError(error)

    async def directory_documentation(self, directory_path: str) -> None:
        """Crawl a directory for documentation."""
        error = "Directory documentation is not implemented yet."
        raise NotImplementedError(error)

    async def file_documentation(self, file_path: str) -> None:
        """Crawl a file for documentation."""
        msg = "File documentation is not implemented yet."
        raise NotImplementedError(msg)

    @mcp_tool()
    async def urls_from_webpage(self, url: str = URL_FIELD) -> list[str]:
        """Extract URLs from a webpage.

        This is extremely useful for determining what urls to crawl from a given seed page.
        For example, if you know you want rspec documentation, you can use this tool to find all the urls on the rspec
        documentation page and then use those urls to crawl the rspec documentation of the version and type you're looking for.

        Returns:
            A list of URLs extracted from the webpage.
        """
        return (await extract_urls_from_webpage(url=url, domain_filter=None, path_filter=None)).get("urls_to_crawl", [])

    @mcp_tool()
    async def from_web_documentation(
        self,
        learn_web_documentation_proto: LearnWebDocumentationProto = LEARN_WEB_DOCUMENTATION_PROTO_FIELD,
        max_child_page_limit: int = MAX_CHILD_PAGE_LIMIT_FIELD,
    ) -> CrawlResult:
        """Start a crawl job based on a seed page after validating the number of child URLs.

        Returns:
            A CrawlStartSuccess object if the crawl is initiated, otherwise a CrawlStartFailure object.
        """
        url = learn_web_documentation_proto.data_source
        overwrite = learn_web_documentation_proto.overwrite
        exclude_paths = learn_web_documentation_proto.exclude_paths

        try:
            crawl_parameters: dict[str, Any] = await Crawler.validate_crawl(url, max_child_page_limit)
        except CrawlerValidationError as e:
            msg = f"Validation failed for URL {url}: {e}"
            logger.exception(msg)
            return CrawlStartFailure(url=url, reason=str(e))

        target_knowledge_base: KnowledgeBase | None = await self.knowledge_base_client.try_get_by_name(learn_web_documentation_proto.name)

        if target_knowledge_base and not overwrite:
            message = f"Knowledge base with name '{learn_web_documentation_proto.name}' already exists. Use 'overwrite' to update it."
            logger.error(message)
            return CrawlStartFailure(url=url, reason=message)

        if not target_knowledge_base:
            try:
                target_knowledge_base = await self.knowledge_base_client.create(
                    knowledge_base_create_proto=learn_web_documentation_proto.to_knowledge_base_create_proto()
                )
            except KnowledgeBaseCreationError:
                message = f"Failed to create or update knowledge base for {url}."
                logger.exception(message)
                return CrawlStartFailure(url=url, reason=message)

        logger.debug("Starting crawl job for URL with parameters: %s", crawl_parameters)

        index_name = target_knowledge_base.backend_id

        try:
            container_id = await self.crawler.crawl_domain(
                elasticsearch_index_name=index_name, exclude_paths=exclude_paths, **crawl_parameters
            )
        except CrawlerError as e:
            msg = f"Failed to start crawl for {url}: {e}"
            logger.exception(msg)
            return CrawlStartFailure(url=url, reason=str(e))

        msg = f"Successfully started crawl for {url} with container ID {container_id}."
        logger.info(msg)

        return CrawlStartSuccess(url=url, knowledge_base_id=index_name, container_id=container_id)

    @mcp_tool()
    async def active_documentation_requests(self) -> list[dict[str, Any]]:
        """List of active documentation requests.

        This is useful for monitoring ongoing crawls and their statuses.

        Returns:
            list[dict[str, Any]]: A list of dictionaries, where each dictionary represents an active crawl request and its status.
        """
        return await self.crawler.list_crawls()
