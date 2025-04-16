import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator
from elasticsearch import AsyncElasticsearch
from fastmcp import FastMCP


from es_knowledge_base_mcp.clients.knowledge_base import KnowledgeBaseServer
from es_knowledge_base_mcp.models.errors import InvalidConfigurationError
from es_knowledge_base_mcp.models.settings import DocsManagerSettings
from es_knowledge_base_mcp.servers.ask import AskServer
from es_knowledge_base_mcp.servers.learn import LearnServer
from fastmcp.utilities.logging import get_logger

from es_knowledge_base_mcp.servers.manage import ManageServer
from es_knowledge_base_mcp.servers.remember import MemoryServer

logger = get_logger("knowledge-base-mcp")


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
        raise InvalidConfigurationError(f"Failed to load settings: {e}")


@dataclass
class RootContext:
    knowledge_base_server: KnowledgeBaseServer
    memory_server: MemoryServer
    ask_server: AskServer
    learn_server: LearnServer
    manage_server: ManageServer


async def main():
    arg_parsing()

    settings: DocsManagerSettings = load_settings()

    elasticsearch_client_args = settings.elasticsearch.to_client_settings()

    elasticsearch_client = AsyncElasticsearch(**elasticsearch_client_args)

    knowledge_base_server = KnowledgeBaseServer(
        settings=settings.knowledge_base,
        elasticsearch_client=elasticsearch_client,
    )

    memory_server = MemoryServer(
        knowledge_base_server=knowledge_base_server,
        memory_server_settings=settings.memory,
    )

    ask_server = AskServer(
        knowledge_base_server=knowledge_base_server,
    )

    learn_server = LearnServer(
        knowledge_base_server=knowledge_base_server,
        crawler_settings=settings.crawler,
        elasticsearch_settings=settings.elasticsearch,
    )

    manage_server = ManageServer(
        knowledge_base_server=knowledge_base_server,
    )

    await knowledge_base_server.async_init()
    await memory_server.async_init()
    await ask_server.async_init()
    await learn_server.async_init()
    await manage_server.async_init()

    root_mcp = FastMCP("knowledge-base-mcp")

    @asynccontextmanager
    async def root_lifespan(server: FastMCP) -> AsyncGenerator[RootContext, None]:
        """Lifespan for the FastMCP application."""

        yield RootContext(
            knowledge_base_server=knowledge_base_server,
            memory_server=memory_server,
            ask_server=ask_server,
            learn_server=learn_server,
            manage_server=manage_server,
        )

    root_mcp = FastMCP("kbmcp", lifespan=root_lifespan)

    manage_server.register_with_mcp(root_mcp)
    memory_server.register_with_mcp(root_mcp)
    learn_server.register_with_mcp(root_mcp)
    ask_server.register_with_mcp(root_mcp)

    try:
        await root_mcp.run_async(transport=settings.mcps.mcp_transport)
    finally:
        await knowledge_base_server.async_shutdown()
        await memory_server.async_shutdown()
        await ask_server.async_shutdown()
        await learn_server.async_shutdown()
        await manage_server.async_shutdown()

        await elasticsearch_client.close()


if __name__ == "__main__":
    asyncio.run(main())