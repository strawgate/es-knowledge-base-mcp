from typing import Any, AsyncIterator
from elasticsearch import ApiError, AsyncElasticsearch, AuthenticationException, AuthorizationException, BadRequestError, ConnectionError
from contextlib import asynccontextmanager
from es_knowledge_base_mcp.models.errors import ElasticsearchConnectionError, ElasticsearchError, InvalidConfigurationError
from es_knowledge_base_mcp.models.settings import ElasticsearchSettings

from fastmcp.utilities.logging import get_logger

logger = get_logger("knowledge-base-mcp.elasticsearch")


@asynccontextmanager
async def elasticsearch_manager(elasticsearch_settings: ElasticsearchSettings) -> AsyncIterator[AsyncElasticsearch]:
    """Context manager for Elasticsearch client."""

    es_client_args = elasticsearch_settings.to_client_settings()

    elasticsearch_client = AsyncElasticsearch(**es_client_args)

    try:
        await elasticsearch_client.info()
    except AuthenticationException as e:
        raise InvalidConfigurationError("Authentication failed for Elasticsearch.") from e
    except AuthorizationException as e:
        raise InvalidConfigurationError("Authorization failed for Elasticsearch.") from e
    except ConnectionError as e:
        raise InvalidConfigurationError("Could not connect to Elasticsearch.") from e
    except Exception as e:
        raise InvalidConfigurationError("Unknown error connecting to Elasticsearch.") from e
    finally:
        await elasticsearch_client.close()

    try:
        async with handle_errors("Elasticsearch client initialization"):
            yield elasticsearch_client
    finally:
        await elasticsearch_client.close()


@asynccontextmanager
async def handle_errors(operation: str) -> AsyncIterator[None]:
    """Context manager for error handling."""

    logger.debug(f"Attempting {operation}...")

    try:
        yield
    except ConnectionError as e:
        raise ElasticsearchConnectionError("Connection error occurred during {operation}.") from e
    except BadRequestError as e:
        raise ElasticsearchError("Elasticsearch returned 'Bad Request' during {operation}.") from e
    except ApiError as e:
        raise ElasticsearchError("Elasticsearch returned an Api Error during {operation}.") from e
    except Exception as e:
        raise ElasticsearchError("Unknown error during Elasticsearch {operation}.") from e

    logger.debug(f"Completed {operation}.")


# region Index Handling


async def create_index(elasticsearch_client, index_name: str, meta: dict[str, Any]) -> None:
    """Creates an index in Elasticsearch."""
    mappings = {"_meta": meta}

    logger.debug(f"Creating index '{index_name}' with mappings: {mappings}")

    async with handle_errors("create index"):
        await elasticsearch_client.indices.create(index=index_name, mappings=mappings)

    logger.debug(f"Index '{index_name}' created successfully.")


# endregion Index Handling
