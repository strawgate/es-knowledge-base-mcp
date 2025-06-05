"""Main entry point for the Knowledge Base MCP Server."""

import argparse
import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import Logger
from typing import Any

import yaml
from elasticsearch import AsyncElasticsearch
from fastmcp import FastMCP
from fastmcp.contrib.bulk_tool_caller import BulkToolCaller
from fastmcp.utilities.logging import get_logger
from pydantic import BaseModel

from es_knowledge_base_mcp.clients.es_knowledge_base import ElasticsearchKnowledgeBaseClient
from es_knowledge_base_mcp.errors.server import ConfigurationError
from es_knowledge_base_mcp.interfaces.knowledge_base import KnowledgeBase
from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME
from es_knowledge_base_mcp.models.settings import CrawlerSettings, DocsManagerSettings, ElasticsearchSettings, MemoryServerSettings
from es_knowledge_base_mcp.servers.ask import AskServer
from es_knowledge_base_mcp.servers.learn import LearnServer
from es_knowledge_base_mcp.servers.manage import ManageServer
from es_knowledge_base_mcp.servers.remember import MemoryServer

logger: Logger = get_logger(name=BASE_LOGGER_NAME)
logger.setLevel(level="DEBUG")


def arg_parsing() -> None:
    """Parse command line arguments for the server."""
    parser = argparse.ArgumentParser(
        description="Knowledge Base MCP Server",
        add_help=True,
    )
    parser.add_argument("--smoke", action="help", help="To run this script please provide two arguments")

    parser.parse_known_args()


def load_settings() -> DocsManagerSettings:
    """Load application settings from environment variables or a .env file.

    Returns:
        DocsManagerSettings: An instance of DocsManagerSettings containing the loaded configuration.

    Raises:
        ConfigurationError: If the settings cannot be loaded or are invalid.
    """
    try:
        return DocsManagerSettings()
    except Exception as e:
        error_message = f"Failed to load settings: {e}"
        raise ConfigurationError(error_message) from e


class MemoryContext(BaseModel):
    """Context for memory-related operations."""

    project_name: str | None
    knowledge_base: KnowledgeBase | None


class RootContext(BaseModel):
    """Root context for the FastMCP server."""

    memory_context: MemoryContext = MemoryContext(project_name=None, knowledge_base=None)


def yaml_serializer(obj: Any) -> str:
    """Serialize to YAML for Pydantic models.

    Returns:
        str: YAML representation of the Pydantic model.

    Raises:
        ValueError: If the object is not a Pydantic model or cannot be serialized.
    """
    if isinstance(obj, BaseModel):
        return yaml.dump(obj.model_dump(), default_flow_style=False, width=10000, sort_keys=False)
    error_message = f"Object of type {type(obj)} is not serializable to YAML"
    raise ValueError(error_message)


@asynccontextmanager
async def root_lifespan(_: FastMCP) -> AsyncGenerator[RootContext, None]:
    """Lifespan context manager for the root FastMCP server.

    Yields:
        RootContext: An instance of RootContext to be used during the server's lifespan.
    """
    yield RootContext()


async def setup_learn_server(
    server: FastMCP,
    knowledge_base_client: ElasticsearchKnowledgeBaseClient,
    crawler_settings: CrawlerSettings,
    elasticsearch_settings: ElasticsearchSettings,
) -> FastMCP:
    """Set up the Learn Server with the provided FastMCP server.

    This function registers the LearnServer with the given FastMCP instance,
    allowing it to handle learning operations within the MCP framework.

    Returns:
        FastMCP: The configured LearnServer instance.
    """
    learn_mcp = FastMCP(name="learn-mcp", tool_serializer=yaml_serializer)

    learn_server = LearnServer(
        knowledge_base_client=knowledge_base_client,
        crawler_settings=crawler_settings,
        elasticsearch_settings=elasticsearch_settings,
    )

    await learn_server.crawler.async_init()

    learn_server.register_tools(mcp_server=learn_mcp)

    server.mount(prefix="learn", server=learn_mcp)

    return learn_mcp


def setup_manage_server(server: FastMCP, knowledge_base_client: ElasticsearchKnowledgeBaseClient) -> FastMCP:
    """Set up the Manage Server with the provided FastMCP server.

    This function registers the ManageServer with the given FastMCP instance,
    allowing it to handle management operations within the MCP framework.

    Returns:
        FastMCP: The configured ManageServer instance.
    """
    manage_mcp = FastMCP(name="manage-mcp", tool_serializer=yaml_serializer)

    manage_server = ManageServer(
        knowledge_base_client=knowledge_base_client,
    )

    manage_server.register_tools(mcp_server=manage_mcp)

    server.mount(prefix="manage", server=manage_mcp)

    return manage_mcp


def setup_memory_server(
    server: FastMCP, memory_server_settings: MemoryServerSettings, knowledge_base_client: ElasticsearchKnowledgeBaseClient
) -> FastMCP:
    """Set up the Memory Server with the provided FastMCP server.

    This function registers the MemoryServer with the given FastMCP instance,
    allowing it to handle memory-related operations within the MCP framework.

    Returns:
        FastMCP: The configured MemoryServer instance.
    """
    memory_mcp = FastMCP(name="memory-mcp", tool_serializer=yaml_serializer)

    MemoryServer(
        knowledge_base_client=knowledge_base_client,
        memory_server_settings=memory_server_settings,
    ).register_all(mcp_server=memory_mcp)

    server.mount(prefix="memory", server=memory_mcp)

    return memory_mcp


def setup_ask_server(server: FastMCP, knowledge_base_client: ElasticsearchKnowledgeBaseClient) -> FastMCP:
    """Set up the Ask Server with the provided FastMCP server.

    This function registers the AskServer with the given FastMCP instance,
    allowing it to handle question-answering operations within the MCP framework.

    Returns:
        FastMCP: The configured AskServer instance.
    """
    ask_mcp = FastMCP(name="ask-mcp", tool_serializer=yaml_serializer)

    AskServer(
        knowledge_base_client=knowledge_base_client,
    ).register_all(mcp_server=ask_mcp)

    server.mount(prefix="ask", server=ask_mcp)

    return ask_mcp


async def main() -> None:
    """Entry point for the Knowledge Base MCP Server.

    Raises:
        ConfigurationError: If the Elasticsearch client fails to ping or if settings cannot be loaded.
    """
    arg_parsing()

    logger.info("Starting Knowledge Base MCP Server...")
    settings: DocsManagerSettings = load_settings()

    settings.logging.configure_logging()

    elasticsearch_client_args = settings.elasticsearch.to_client_settings()
    elasticsearch_client = AsyncElasticsearch(**elasticsearch_client_args)

    if not await elasticsearch_client.options(request_timeout=5).ping():
        error_message = "Elasticsearch client failed to ping. Please check your Elasticsearch configuration."
        raise ConfigurationError(error_message)

    # monkey patch so our yaml emitter doesnt include class names in output
    yaml.emitter.Emitter.prepare_tag = lambda self, tag: ""  # noqa: ARG005

    async with ElasticsearchKnowledgeBaseClient.connection_context_manager(elasticsearch_client) as handled_elasticsearch_client:
        knowledge_base_client = ElasticsearchKnowledgeBaseClient(
            settings=settings.knowledge_base,
            elasticsearch_client=handled_elasticsearch_client,
        )

    # Begin initializing MCP Servers
    root_mcp = FastMCP(name="knowledge-base-mcp", lifespan=root_lifespan, tool_serializer=yaml_serializer)

    setup_manage_server(server=root_mcp, knowledge_base_client=knowledge_base_client)

    setup_memory_server(server=root_mcp, memory_server_settings=settings.memory, knowledge_base_client=knowledge_base_client)

    setup_ask_server(server=root_mcp, knowledge_base_client=knowledge_base_client)

    await setup_learn_server(
        server=root_mcp,
        knowledge_base_client=knowledge_base_client,
        crawler_settings=settings.crawler,
        elasticsearch_settings=settings.elasticsearch,
    )

    bulk_tool_caller = BulkToolCaller()

    bulk_tool_caller.register_tools(root_mcp)

    logger.info("All MCP servers initialized successfully.")
    await root_mcp.run_async(transport=settings.mcps.mcp_transport)


def run() -> None:
    """Run the main asynchronous server."""
    try:
        asyncio.run(main=main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
    except Exception as e:
        error_message = f"An error occurred: {e}"
        logger.exception(error_message)
    finally:
        logger.info("Server shutdown complete.")


if __name__ == "__main__":
    logger.error("This script is not meant to be run directly. Please use the MCP CLI to start the server.")
    run()
