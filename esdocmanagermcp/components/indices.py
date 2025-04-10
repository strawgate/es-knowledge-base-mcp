import logging
from typing import List, Dict, Any, Optional
from elasticsearch import AsyncElasticsearch, ApiError, ConnectionError

from esdocmanagermcp.components.errors.base import IndexListingError, UnknownSearchError

logger = logging.getLogger(__name__)


class IndicesManager:
    es_client: AsyncElasticsearch

    def __init__(self, es_client: AsyncElasticsearch):
        self.es_client = es_client
        logger.info("IndicesManager component initialized.")

    async def list_elasticsearch_indices(self, index_patterns: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Retrieves a list of indices with specific details from Elasticsearch,
        optionally filtering by index patterns.

        Args:
            index_patterns: A list of index patterns to filter by (e.g., ["my-index-*", "another-index"]).
                            If None or empty, retrieves all indices.

        Returns:
            A list of dictionaries, each representing an index and its details.
        """
        cat_args = {"index": index_patterns, "format": "json", "h": ["index", "docs.count", "creation.date.string"]}

        try:
            response: List[Dict[str, Any]] = await self.es_client.cat.indices(**cat_args)

            logger.info(f"Successfully retrieved {len(response)} indices.")

            return response
        except (ApiError, ConnectionError) as e:
            raise IndexListingError(f"API/Connection Error while retrieving indices: {e}") from e
        except Exception as e:
            raise UnknownSearchError(f"Unexpected error while retrieving indices: {e}") from e

    async def delete_elasticsearch_index(self, index_name: str) -> bool:
        """
        Deletes a specific Elasticsearch index.

        Args:
            index_name: The exact name of the index to delete.

        Returns:
            True if the index was deleted or didn't exist, False otherwise.
        """
        try:
            await self.es_client.indices.delete(index=index_name, ignore=[400, 404])
            logger.info(f"Attempted deletion for index '{index_name}'. It was either deleted or did not exist.")
            return True
        except (ApiError, ConnectionError) as e:
            logger.error(f"Failed to delete index '{index_name}': {e}", exc_info=True)
            return False
