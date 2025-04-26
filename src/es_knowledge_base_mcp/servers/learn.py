"""MCP Server for the Learn MCP Server."""

from typing import Any, Callable
from fastmcp import FastMCP
from pydantic import Field

from typing import Union
from es_knowledge_base_mcp.clients.crawl import Crawler, CrawlerSettings

from es_knowledge_base_mcp.errors.knowledge_base import KnowledgeBaseCreationError
from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    kb_data_source_field,
    kb_description_field,
    kb_name_field,
)
from es_knowledge_base_mcp.errors.crawler import CrawlerError, CrawlerValidationError
from es_knowledge_base_mcp.models.base import ExportableModel
from es_knowledge_base_mcp.models.settings import ElasticsearchSettings
from es_knowledge_base_mcp.clients.web import extract_urls_from_webpage

from fastmcp.utilities.logging import get_logger

logger = get_logger("knowledge-base-mcp.learn")

MEMORY_KNOWLEDGE_BASE_NAME = "Memory Knowledge Base"


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
    version: str = Field(default="latest", description="The version of the documentation you are sourcing from.")
    data_source: str = kb_data_source_field
    exclude_paths: list[str] = Field(
        default_factory=list,
        description="A list of paths to exclude from the crawl. Not normally necessary. Useful for excluding certain sections of a website."
    )
    overwrite: bool = Field(
        default=False,
        description="If true, will overwrite the existing knowledge base with the same name. If false, will not crawl if the knowledge base already exists.",
    )
    description: str = kb_description_field

    def to_knowledge_base_create_proto(self) -> KnowledgeBaseCreateProto:
        """Converts the LearnWebDocumentationProto to a KnowledgeBaseCreateProto."""
        return KnowledgeBaseCreateProto(
            name=self.name,
            data_source=self.data_source,
            description=self.description,
            type="docs",
        )


CrawlResult = Union[CrawlStartSuccess, CrawlStartFailure]


class LearnServer:
    """
    MCP Server for the Learn tool.

    Provides tools for learning from various data sources, such as web documentation.
    """

    crawler: Crawler

    knowledge_base_client: KnowledgeBaseClient

    response_wrapper: Callable

    def __init__(
        self,
        knowledge_base_client: KnowledgeBaseClient,
        crawler_settings: CrawlerSettings,
        elasticsearch_settings: ElasticsearchSettings,
        response_wrapper: Callable | None = None,
    ):
        self.knowledge_base_client = knowledge_base_client

        self.crawler = Crawler(settings=crawler_settings, elasticsearch_settings=elasticsearch_settings)

        self.response_wrapper = response_wrapper or (lambda response: response)

    async def async_init(self):
        """Initialize the learn server."""

        await self.crawler.async_init()

    async def async_shutdown(self):
        """Shutdown the learn server."""

        await self.crawler.async_shutdown()

        pass

    def register_with_mcp(self, mcp: FastMCP):
        """Register the learn server tools with the MCP."""
        mcp.add_tool(self.response_wrapper(extract_urls_from_webpage))
        mcp.add_tool(self.response_wrapper(self.from_web_documentation))
        mcp.add_tool(self.response_wrapper(self.active_documentation_requests))

    async def git_repository(self, directory_path: str):
        pass

    async def directory_documentation(self, directory_path: str):
        raise NotImplementedError("Directory documentation is not implemented yet.")

    async def file_documentation(self, file_path: str):
        raise NotImplementedError("File documentation is not implemented yet.")

    async def urls_from_webpage(self, url: str):
        """
        Extracts URLs from a webpage. This is extremely useful for determining what urls to crawl from a given seed page.
        For example, if you know you want rspec documentation, you can use this tool to find all the urls on the rspec
        documentation page and then use those urls to crawl the rspec documentation of the version and type you're looking for.

        Args:
            url: The URL of the webpage to extract URLs from.

        Returns:
            A list of URLs extracted from the webpage.
        """
        return await extract_urls_from_webpage(url=url, domain_filter=None, path_filter=None)

    # async def from_web_documentation(
    #     self, url: str, knowledge_base_name: str, knowledge_base_description: str, max_child_page_limit: int | None = None
    # ) -> CrawlResult:
    #     """
    #     Starts a crawl job based on a seed page and creates a knowledge base entry for it, with URL validation.

    #     Args:
    #         url: The seed URL to start the crawl from.
    #         knowledge_base_name: The name for the new or existing knowledge base.
    #         knowledge_base_description: A description for the new or existing knowledge base.
    #         max_child_page_limit: (Optional) The maximum allowed number of child pages to crawl from the seed URL.

    #     Returns:
    #         CrawlResult: An object indicating the result of the crawl initiation (success or failure).

    #     Example:
    #         >>> await self.from_web_documentation(url="http://example.com/docs", knowledge_base_name="Example Docs", knowledge_base_description="Documentation for Example.com")
    #         CrawlStartSuccess(url='http://example.com/docs', knowledge_base_id='...', container_id='...', status='success')
    #     """

    #     learn_web_documentation_proto = LearnWebDocumentationProto(
    #         name=knowledge_base_name,
    #         data_source=url,
    #         description=knowledge_base_description,
    #     )

    #     return await self._from_web_documentation_request(learn_web_documentation_proto=learn_web_documentation_proto)

    async def from_web_documentation(
        self, learn_web_documentation_proto: LearnWebDocumentationProto #, max_child_page_limit: int = 500
    ) -> CrawlResult:
        """
        Starts a crawl job based on a seed page after validating the number of child URLs.

        Args:
            learn_web_documentation_proto: The LearnWebDocumentationProto object containing the name, source URL, and description for the knowledge base.
            max_child_page_limit: The maximum allowed number of child pages to crawl. Defaults to 500.

        Returns:
            A CrawlStartSuccess object if the crawl is initiated, otherwise a CrawlStartFailure object.
        """
        url = learn_web_documentation_proto.data_source
        overwrite = learn_web_documentation_proto.overwrite
        exclude_paths = learn_web_documentation_proto.exclude_paths

        try:
            crawl_parameters: dict[str, Any] = await Crawler.validate_crawl(url)
        except CrawlerValidationError as e:
            logger.error(f"Validation failed for URL {url}: {e}")
            return CrawlStartFailure(url=url, reason=str(e))

        # Check if the knowledge base already exists
        target_knowledge_base: KnowledgeBase | None


        if target_knowledge_base := await self.knowledge_base_client.try_get_by_name(learn_web_documentation_proto.name):
            if not overwrite:
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
                logger.error(message)
                return CrawlStartFailure(url=url, reason=message)


        logger.debug("Starting crawl job for URL with parameters: %s", crawl_parameters)

        index_name = target_knowledge_base.backend_id

        try:
            container_id = await self.crawler.crawl_domain(elasticsearch_index_name=index_name, exclude_paths=exclude_paths, **crawl_parameters)
        except CrawlerError as e:
            logger.error(f"Starting crawl failed for {url}: {e}")
            return CrawlStartFailure(url=url, reason=str(e))

        logger.info(f"Crawl initiated successfully for {url} with container ID {container_id}")

        return CrawlStartSuccess(url=url, knowledge_base_id=index_name, container_id=container_id)

    async def active_documentation_requests(self) -> list[dict[str, Any]]:
        """
        Returns a list of active documentation requests.

        This is useful for monitoring ongoing crawls and their statuses.

        Returns:
            list[dict[str, Any]]: A list of dictionaries, where each dictionary represents an active crawl request and its status.

        Example:
            >>> await self.active_documentation_requests()
            [{'container_id': '...', 'status': 'running', ...}]
        """
        return await self.crawler.list_crawls()
