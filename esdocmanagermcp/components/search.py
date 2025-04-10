from contextlib import asynccontextmanager
import logging

from typing import List, Dict, Any, Optional

from elastic_transport import ObjectApiResponse
from pydantic import BaseModel
from elasticsearch import (
    AsyncElasticsearch,
    NotFoundError,
    ApiError,
)

from esdocmanagermcp.components.errors import (
    IndexNotFoundError,
    SearchExecutionError,
)

# region Settings
logger = logging.getLogger(__name__)


class SearcherSettings(BaseModel):
    """Settings specific to the Searcher component."""

    es_index_prefix: str


# endregion Settings


class Searcher:
    """Handles searching documents within Elasticsearch indices."""

    es_client: AsyncElasticsearch
    settings: SearcherSettings

    def __init__(self, es_client: AsyncElasticsearch, settings: SearcherSettings):
        """Initializes the Searcher component."""
        self.es_client = es_client
        self.settings = settings
        logger.info("Searcher component initialized.")

    # region Doc Search
    @asynccontextmanager
    async def error_wrapper(self, operation: str, description: str):
        """Context manager to wrap Elasticsearch operations with common error handling."""
        logger.debug(f"Attempting {operation} for {description}.")
        try:
            yield
        except NotFoundError as e:
            raise IndexNotFoundError(f"Index not found error while {operation}: {description}") from e
        except ApiError as e:
            raise SearchExecutionError(f"Elasticsearch API error while {operation}: {description}': {e}") from e
        except Exception as e:
            raise SearchExecutionError(f"Unexpected error while {operation}: {description}': {e}") from e

        logger.debug(f"Completed {operation} for {description}.")

    async def documentation_search(self, type: str, query: str, results: int = 10) -> List[Dict[str, Any]]:
        """
        Performs a search query against a specified documentation index.
        Raises IndexNotFoundError or SearchExecutionError on failure.
        """

        target_indices = self._convert_index_name(type)

        logger.info(f"Searching index '{target_indices}' for query: '{query}'")

        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {"headings": {"query": query, "boost": 1}},
                        },
                        {"semantic": {"field": "body", "query": query, "boost": 2}},
                    ]
                }
            },
            "_source": ["title", "url"],
            "size": results,
            "highlight": {"fields": {"body": {}}},
        }

        async with self.error_wrapper("searching", f"index '{target_indices}'"):
            response: ObjectApiResponse[dict] = await self.es_client.search(index=target_indices, **search_body)

        hits = response.get("hits", {}).get("hits", [])

        logger.info(f"Search returned {len(hits)} results from index '{target_indices}'.")

        return [
            {
                "title": hit["_source"].get("title"),
                "url": hit["_source"].get("url"),
                "match": hit.get("highlight", {}).get("body", []),
            }
            for hit in hits
        ]

    # endregion

    # region Get Document
    async def get_document_by_query(self, query_body: Dict[str, Any], types: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single document based on a specific query body part.

        Args:
            query_body: The specific query part (e.g., {"term": {"url.keyword": "..."}}).
            types: Comma-separated list of documentation types (indices) to search.

        Returns:
            A dictionary containing the document's title, url, and content, or None if not found.
        """
        target_indices = self._convert_index_name(types)

        logger.info(f"Attempting to get document from indices '{','.join(target_indices)}' using query: {query_body}")

        async with self.error_wrapper("searching", f"index '{target_indices}'"):
            response: ObjectApiResponse[dict] = await self.es_client.search(
                index=target_indices,
                query=query_body,
                _source=["title", "url", "body"],
                size=1,
                ignore_unavailable=True,
            )

        hits = response.get("hits", {}).get("hits", [])

        logger.info(f"Search returned {len(hits)} results from index '{target_indices}'.")

        return [
            {
                "title": hit["_source"].get("title"),
                "url": hit["_source"].get("url"),
                "content": hit["_source"].get("body"),
            }
            for hit in hits
        ]

    # endregion Get Document

    def _convert_index_name(self, index_name: str) -> str:
        """
        Converts a user provided index pattern to the actual index name used in Elasticsearch by prepending the index prefix.
        """
        return [f"{self.settings.es_index_prefix}-{index.strip()}" for index in index_name.split(",") if index.strip()]
