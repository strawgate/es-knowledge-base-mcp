import logging

from typing import List, Dict, Any  # Added Coroutine

from elastic_transport import ObjectApiResponse
from pydantic import BaseModel
from elasticsearch import (
    AsyncElasticsearch,
    NotFoundError,
    ApiError,
)

# Import custom exceptions using absolute path
from esdocmanagermcp.components.errors import (
    IndexListingError,
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

    # region Indices

    async def list_doc_indices(self) -> List[str]:  # Changed signature
        """
        Lists Elasticsearch indices matching the configured prefix.
        Raises IndexListingError on failure.
        """
        index_pattern = f"{self.settings.es_index_prefix}-*"
        logger.info(f"Listing indices matching pattern: {index_pattern}")
        try:
            # Use indices.get to fetch matching indices
            response: ObjectApiResponse[dict] = await self.es_client.indices.get(
                index=index_pattern,
                # Ignore 404 if no indices match the pattern
                ignore=[404],
            )

            # Extract index names
            indices = list(response.body.keys())
            logger.info(f"Found indices: {indices}")
            return indices  # Return list of index names

        except ApiError as e:  # Catch specific ES API errors
            logger.error(f"Elasticsearch API error listing indices: {e}")
            raise IndexListingError(
                f"Elasticsearch API error listing indices: {e}"
            ) from e
        except Exception as e:  # Catch any other unexpected errors
            logger.exception("Unexpected error listing indices.")
            raise IndexListingError(f"Unexpected error listing indices: {e}") from e

    # endregion Indices

    # region Search Docs

    async def search_docs(
        self, index_name: str, query: str
    ) -> List[Dict[str, Any]]:  # Changed signature
        """
        Performs a search query against a specified documentation index using ELSER.
        Raises IndexNotFoundError or SearchExecutionError on failure.
        """
        # Removed check for index prefix - let ES handle non-existence

        logger.info(f"Searching index '{index_name}' for query: '{query}'")

        # Basic ELSER query structure
        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {"headings": {"query": query, "boost": 1}},
                        },
                        {
                            "semantic": {
                                "field": "body",
                                "query": query,
                                "boost": 2
                            }
                        },
                    ]
                }
            },
            "_source": ["title", "url", "crawled_at"],  # Return specific fields
            "size": 10,  # Limit results
            "highlight": {  # Add highlighting on the body field
                "fields": {"body": {"order": "score"}}
            },
        }

        try:
            response: ObjectApiResponse[dict] = await self.es_client.search(
                index=index_name, **search_body
            )

            hits = response.get("hits", {}).get("hits", [])
            results = hits
            logger.info(
                f"Search returned {len(results)} results from index '{index_name}'."
            )
            return results  # Return raw results list

        except NotFoundError as e:  # Catch specific ES NotFoundError
            logger.warning(
                f"Search failed: Index '{index_name}' not found during search operation."
            )
            raise IndexNotFoundError(
                f"Index '{index_name}' not found during search."
            ) from e
        except ApiError as e:  # Catch other ES API errors
            logger.error(f"Elasticsearch API error searching index '{index_name}': {e}")
            raise SearchExecutionError(
                f"Elasticsearch API error searching index '{index_name}': {e}"
            ) from e
        except Exception as e:  # Catch any other unexpected errors
            logger.exception(f"Unexpected error searching index '{index_name}'.")
            raise SearchExecutionError(
                f"Unexpected error searching index '{index_name}': {e}"
            ) from e

    # endregion


# endregion Class Definition
