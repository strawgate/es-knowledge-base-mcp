import argparse
import asyncio
from dataclasses import dataclass
import functools
from typing import Callable
from elasticsearch import AsyncElasticsearch
from fastmcp import FastMCP
import yaml
from es_knowledge_base_mcp.clients.es_knowledge_base import ElasticsearchKnowledgeBaseClient
from es_knowledge_base_mcp.interfaces.knowledge_base import KnowledgeBaseClient
from es_knowledge_base_mcp.errors.server import ConfigurationError
from es_knowledge_base_mcp.models.settings import DocsManagerSettings
from es_knowledge_base_mcp.servers.ask import AskServer
from es_knowledge_base_mcp.servers.learn import LearnServer
from fastmcp.utilities.logging import get_logger

from es_knowledge_base_mcp.servers.contrib.bulk_tool_caller import BulkToolCaller
from es_knowledge_base_mcp.servers.manage import ManageServer
from es_knowledge_base_mcp.servers.remember import MemoryServer
from es_knowledge_base_mcp.servers.fetch import FetchServer

logger = get_logger("knowledge-base-mcp")
logger.setLevel("DEBUG")


def arg_parsing():
    parser = argparse.ArgumentParser(
        description="Knowledge Base MCP Server",
        add_help=True,
    )
    parser.add_argument("--smoke", action="help", help="To run this script please provide two arguments")

    args, unknown = parser.parse_known_args()


def load_settings():
    try:
        return DocsManagerSettings()
    except Exception as e:
        raise ConfigurationError(f"Failed to load settings: {e}")


@dataclass
class RootContext:
    knowledge_base_client: KnowledgeBaseClient
    memory_server: MemoryServer
    ask_server: AskServer
    manage_server: ManageServer
    learn_server: LearnServer | None
    fetch_server: FetchServer


async def main():
    """
    Main entry point for the Knowledge Base MCP Server.

    This asynchronous function initializes the server by:
    1. Parsing command line arguments.
    2. Loading application settings.
    3. Configuring logging.
    4. Initializing the Elasticsearch client.
    5. Setting up and registering the various MCP servers (Manage, Memory, Ask, Learn, Fetch).
    6. Registering the bulk tool caller.
    7. Running the main MCP server loop.
    8. Ensuring proper shutdown of all initialized components upon exit or interruption.
    """
    arg_parsing()

    settings: DocsManagerSettings = load_settings()

    settings.logging.configure_logging()

    elasticsearch_client_args = settings.elasticsearch.to_client_settings()

    elasticsearch_client = AsyncElasticsearch(**elasticsearch_client_args)

    # monkey patch so our yaml emitter doesnt include class names in output
    yaml.emitter.Emitter.prepare_tag = lambda self, tag: ""

    def text_response_wrapper(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            response = await func(*args, **kwargs)
            return response

        return wrapper

    def yaml_response_wrapper(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            response = await func(*args, **kwargs)

            if isinstance(response, list):
                # If the response is a list, convert each item to a dictionary
                return "\n\n".join([yaml.dump(item, default_flow_style=False, width=10000, sort_keys=False) for item in response])

            return yaml.dump(response, default_flow_style=False, width=10000, sort_keys=False)

        return wrapper

    root_mcp = FastMCP("knowledge-base-mcp")

    knowledge_base_client = ElasticsearchKnowledgeBaseClient(
        settings=settings.knowledge_base,
        elasticsearch_client=elasticsearch_client,
    )

    # Setup the Manage server
    manage_server = ManageServer(
        knowledge_base_client=knowledge_base_client,
        response_wrapper=yaml_response_wrapper,
    )
    manage_mcp = FastMCP("manage-mcp")

    await manage_server.async_init()
    manage_server.register_with_mcp(manage_mcp)

    root_mcp.mount("knowledge_base", manage_mcp)

    # Setup the Memory server
    memory_server = MemoryServer(
        knowledge_base_client=knowledge_base_client,
        memory_server_settings=settings.memory,
        response_wrapper=yaml_response_wrapper,
    )

    memory_mcp = FastMCP("memory-mcp")
    await memory_server.async_init()

    memory_server.register_with_mcp(memory_mcp)

    root_mcp.mount("memory", memory_mcp)

    # Initialize the Ask server
    ask_server = AskServer(
        knowledge_base_client=knowledge_base_client,
        response_wrapper=yaml_response_wrapper,
    )

    ask_mcp = FastMCP("ask-mcp")

    await ask_server.async_init()
    ask_server.register_with_mcp(ask_mcp)

    root_mcp.mount("ask", ask_mcp)

    # Initialize the Learn server
    learn_server = LearnServer(
        knowledge_base_client=knowledge_base_client,
        crawler_settings=settings.crawler,
        elasticsearch_settings=settings.elasticsearch,
        response_wrapper=yaml_response_wrapper,
    )

    learn_mcp = FastMCP("learn-mcp")

    try:
        await learn_server.async_init()
        learn_server.register_with_mcp(learn_mcp)
        root_mcp.mount("learn", learn_mcp)
    except Exception as e:
        logger.warning(f"Failed to initialize Learn server, likely due to Docker not being available. Error: {e}")
        learn_server = None

    # Initialize the Fetch server
    fetch_server = FetchServer(response_wrapper=text_response_wrapper)

    fetch_mcp = FastMCP("fetch-mcp")

    await fetch_server.async_init()
    fetch_server.register_with_mcp(fetch_mcp)

    root_mcp.mount("fetch", fetch_mcp)

    bulk_tool_caller = BulkToolCaller()

    bulk_tool_caller.register_tools(root_mcp)

    try:
        await root_mcp.run_async(transport=settings.mcps.mcp_transport)
    finally:
        await knowledge_base_client.async_shutdown()
        await memory_server.async_shutdown()
        await ask_server.async_shutdown()

        if learn_server:
            await learn_server.async_shutdown()

        await fetch_server.async_shutdown()
        await manage_server.async_shutdown()

        await elasticsearch_client.close()


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Server shutdown complete.")


if __name__ == "__main__":
    logger.error("This script is not meant to be run directly. Please use the MCP CLI to start the server.")
    run()
