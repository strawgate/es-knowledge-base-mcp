"""Elasticsearch client for managing and searching knowledge bases."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from elasticsearch import (
    ApiError,
    AsyncElasticsearch,
    AuthenticationException,
    AuthorizationException,
    ConflictError,
    ConnectionError,  # noqa: A004
    NotFoundError,
)
from fastmcp.utilities.logging import get_logger

from es_knowledge_base_mcp.errors.knowledge_base import (
    KnowledgeBaseAlreadyExistsError,
    KnowledgeBaseCreationError,
    KnowledgeBaseDeletionError,
    KnowledgeBaseError,
    KnowledgeBaseNotFoundError,
    KnowledgeBaseRetrievalError,
    KnowledgeBaseSearchError,
    KnowledgeBaseUpdateError,
)
from es_knowledge_base_mcp.interfaces.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseClient,
    KnowledgeBaseCreateProto,
    KnowledgeBaseDocument,
    KnowledgeBaseDocumentProto,
    KnowledgeBaseSearchResult,
    KnowledgeBaseSearchResultError,
    KnowledgeBaseSearchResultTypes,
    KnowledgeBaseUpdateProto,
    PerKnowledgeBaseSummary,
)
from es_knowledge_base_mcp.models.constants import CRAWLER_INDEX_MAPPING
from es_knowledge_base_mcp.models.settings import KnowledgeBaseServerSettings

logger = get_logger("knowledge-base-mcp.elasticsearch")

# endregion Index Handling


logger = get_logger("knowledge-base-mcp.knowledge-base")

HITS_CACHE_BUST_INTERVAL = 60  # seconds


class ElasticsearchError(KnowledgeBaseError):
    """Base class for Elasticsearch-related errors."""

    msg: str = "An error occurred with Elasticsearch."


class ElasticsearchConnectionError(ElasticsearchError):
    """Raised when there is an error with Elasticsearch."""

    msg: str = "Error connecting to Elasticsearch."


class ElasticsearchAuthenticationError(ElasticsearchError):
    """Raised when there is an authentication error with Elasticsearch."""

    msg: str = "Authentication failed for Elasticsearch."


class ElasticsearchAuthorizationError(ElasticsearchError):
    """Raised when there is an authorization error with Elasticsearch."""

    msg: str = "Authorization failed for Elasticsearch."


class ElasticsearchKnowledgeBaseClient(KnowledgeBaseClient):
    """Elasticsearch implementation of the KnowledgeBaseClient protocol.

    Handles the logic for managing and searching knowledge bases via Elasticsearch.
    """

    index_prefix: str
    index_pattern: str

    elasticsearch_client: AsyncElasticsearch

    def __init__(self, settings: KnowledgeBaseServerSettings, elasticsearch_client: AsyncElasticsearch) -> None:
        """Initialize the ElasticsearchKnowledgeBaseClient."""
        self.index_prefix = settings.base_index_prefix
        self.index_pattern = settings.base_index_pattern

        self.elasticsearch_client = elasticsearch_client

        self._last_cache_bust = datetime.now(tz=UTC)

    # region Error Handling

    @classmethod
    @asynccontextmanager
    async def connection_context_manager(cls, elasticsearch_client: AsyncElasticsearch) -> AsyncGenerator[AsyncElasticsearch, None]:
        """Context manager for Elasticsearch connection errors.

        Yields:
            AsyncElasticsearch: The Elasticsearch client to use within the context.

        Raises:
            ElasticsearchAuthenticationError: If authentication fails.
            ElasticsearchAuthorizationError: If authorization fails.
            ElasticsearchConnectionError: If connection to Elasticsearch fails.
            ElasticsearchError: For any other unexpected errors.
        """
        try:
            yield elasticsearch_client
        except AuthenticationException as e:
            err_text = "Authentication failed for Elasticsearch."
            logger.exception(err_text)
            raise ElasticsearchAuthenticationError from e
        except AuthorizationException as e:
            err_text = "Authorization failed for Elasticsearch."
            logger.exception(err_text)
            raise ElasticsearchAuthorizationError from e
        except ConnectionError as e:
            err_text = "Could not connect to Elasticsearch."
            logger.exception(err_text)
            raise ElasticsearchConnectionError(err_text) from e
        except Exception as e:
            err_text = "Unknown error connecting to Elasticsearch."
            logger.exception(err_text)
            raise ElasticsearchError(err_text) from e
        finally:
            await elasticsearch_client.close()

        logger.debug("Elasticsearch connection established successfully.")

    @asynccontextmanager
    async def error_handler(self, operation: str) -> AsyncGenerator[None, None]:  # noqa: PLR0912
        """Context manager for Elasticsearch client.

        Raises:
            KnowledgeBaseNotFoundError: If a knowledge base is not found.
            KnowledgeBaseAlreadyExistsError: If a knowledge base already exists.
            KnowledgeBaseCreationError: If there is an error creating a knowledge base.
            KnowledgeBaseDeletionError: If there is an error deleting a knowledge base.
            KnowledgeBaseRetrievalError: If there is an error retrieving a knowledge base.
            KnowledgeBaseSearchError: If there is an error searching a knowledge base.
            KnowledgeBaseUpdateError: If there is an error updating a knowledge base.
            KnowledgeBaseError: For general knowledge base errors.
            ElasticsearchError: For any other unexpected errors.
        """
        msg = f"Starting operation: {operation}"
        logger.debug(msg)

        try:
            yield

        except NotFoundError as e:
            error_message = f"Not found error while {operation}"
            logger.exception(error_message)
            raise KnowledgeBaseNotFoundError(error_message) from e
        except ConflictError as e:
            error_message = f"Conflict error while {operation}"
            logger.exception(error_message)
            raise KnowledgeBaseAlreadyExistsError(error_message) from e
        except ApiError as e:
            error_message = f"Elasticsearch API error while {operation}: {e}"
            logger.exception(error_message)
            # Differentiate between update and other API errors if needed, for now general
            if "update" in operation.lower():
                raise KnowledgeBaseUpdateError(error_message) from e
            elif "create" in operation.lower():
                raise KnowledgeBaseCreationError(error_message) from e
            elif "delete" in operation.lower():
                raise KnowledgeBaseDeletionError(error_message) from e
            elif "search" in operation.lower():
                raise KnowledgeBaseSearchError(error_message) from e
            elif "get" in operation.lower():
                raise KnowledgeBaseRetrievalError(error_message) from e
            else:
                raise ElasticsearchError(error_message) from e

        except Exception as e:
            error_message = f"Unexpected error while {operation}."
            logger.exception(error_message)
            # Catch-all for other unexpected errors, map to appropriate KB error
            if "update" in operation.lower():
                raise KnowledgeBaseUpdateError(error_message) from e
            elif "create" in operation.lower():
                raise KnowledgeBaseCreationError(error_message) from e
            elif "delete" in operation.lower():
                raise KnowledgeBaseDeletionError(error_message) from e
            elif "search" in operation.lower():
                raise KnowledgeBaseSearchError(error_message) from e
            elif "get" in operation.lower():
                raise KnowledgeBaseRetrievalError(error_message) from e
            else:
                raise KnowledgeBaseError(error_message) from e

        msg = f"Operation {operation} completed successfully."
        logger.debug(msg)

    # endregion Error Handling

    # region Get KBs

    async def get(self) -> list[KnowledgeBase]:
        """Get a list of all knowledge bases.

        This requires querying the Elasticsearch indices and _cat to get doc counts.

        Returns:
            list[KnowledgeBase]: A list of KnowledgeBase objects representing the knowledge bases found in Elasticsearch.
        """
        async with self.error_handler("getting knowledge base indices"):
            indices_get_response = await self.elasticsearch_client.indices.get_mapping(index=self.index_pattern, allow_no_indices=True)

        if not indices_get_response.body or len(indices_get_response.body) == 0:
            logger.debug("No knowledge base indices found.")
            return []

        kb_name_to_metadata: dict[str, dict[str, Any]] = {
            index: metadata.get("mappings").get("_meta", {}).get("knowledge_base", {})
            for index, metadata in indices_get_response.body.items()
        }

        index_to_doc_counts: dict[str, int] = await self._get_doc_counts()

        knowledge_bases = [
            KnowledgeBase(
                name=metadata.get("name", "<Not Set>"),
                description=metadata.get("description", "<Not Set>"),
                data_source=metadata.get("data_source", "<Not Set>"),
                type=metadata.get("type", "<Not Set>"),
                doc_count=index_to_doc_counts.get(index, 0),
                backend_id=index,
            )
            for index, metadata in kb_name_to_metadata.items()
        ]

        return sorted(knowledge_bases, key=lambda kb: (kb.name.lower()))

    async def _get_doc_counts(self) -> dict[str, int]:
        """Get document counts for a list of indices.

        Uses the cat.indices API to retrieve document counts for the specified indices.

        Returns:
            dict[str, int]: A dictionary where keys are index names and values are document counts.
        """
        async with self.error_handler("getting document counts for indices"):
            cat_response = await self.elasticsearch_client.options(ignore_status=404).cat.indices(
                index=self.index_pattern, format="json", h=["index", "docs.count"]
            )

        if not cat_response.body or not isinstance(cat_response.body, list):
            return {}

        json_responses: list[dict[str, Any]] = cat_response.body

        return {item["index"]: int(item["docs.count"]) for item in json_responses}

    # endregion Get KBs
    # region Create / Update KBs

    async def create(self, knowledge_base_create_proto: KnowledgeBaseCreateProto) -> KnowledgeBase:
        """Create a new knowledge base.

        This method checks if a knowledge base with the same name already exists, and if not, creates a new Knowledge Base.

        Returns:
            KnowledgeBase: The created knowledge base object.

        Raises:
            KnowledgeBaseAlreadyExistsError: If a knowledge base with the same name already exists.
        """
        current_kbs = await self.get()
        if any(kb.name == knowledge_base_create_proto.name for kb in current_kbs):
            msg = f"Knowledge base with name '{knowledge_base_create_proto.name}' already exists."
            raise KnowledgeBaseAlreadyExistsError(msg)

        id_prefix = self.index_prefix + "-" + knowledge_base_create_proto.type
        id_middle: str = self._url_to_index_name(knowledge_base_create_proto.data_source)
        id_suffix = str(uuid.uuid4())[:8]

        index_name = f"{id_prefix}.{id_middle}-{id_suffix}"

        index_mappings = deepcopy(x=CRAWLER_INDEX_MAPPING)

        index_mappings = self._insert_metadata(index_mappings=index_mappings, knowledge_base_create_proto=knowledge_base_create_proto)

        index_mappings = self._insert_runtime_kb_name(index_mappings=index_mappings, kb_name=knowledge_base_create_proto.name)

        async with self.error_handler(f"creating knowledge base index '{index_name}' and mappings {index_mappings}"):
            await self.elasticsearch_client.indices.create(index=index_name, mappings=index_mappings)

        return KnowledgeBase(
            name=knowledge_base_create_proto.name,
            type=knowledge_base_create_proto.type,
            data_source=knowledge_base_create_proto.data_source,
            description=knowledge_base_create_proto.description,
            backend_id=index_name,
            doc_count=0,
        )

    async def update(self, knowledge_base: KnowledgeBase, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """Update editable fields of an existing knowledge base."""
        index_name = knowledge_base.backend_id

        create_proto = knowledge_base.to_create_proto()

        for field in knowledge_base_update.model_fields_set:
            setattr(create_proto, field, getattr(knowledge_base_update, field))

        mapping_update = {}

        mapping_update = self._insert_metadata(index_mappings=mapping_update, knowledge_base_create_proto=create_proto)

        mapping_update = self._insert_runtime_kb_name(index_mappings=mapping_update, kb_name=create_proto.name)

        async with self.error_handler(f"updating knowledge base metadata for '{index_name}'"):
            await self.elasticsearch_client.indices.put_mapping(index=index_name, **mapping_update)

    # endregion Create / Update KBs

    # region Delete KBs
    async def delete(self, knowledge_base: KnowledgeBase) -> None:
        """Delete a knowledge base."""
        async with self.error_handler(f"deleting knowledge base '{knowledge_base.backend_id}'"):
            await self.elasticsearch_client.indices.delete(index=knowledge_base.backend_id)

    # endregion Delete KBs

    async def search(self, phrases: list[str], results: int = 5, fragments: int = 5) -> list[KnowledgeBaseSearchResultTypes]:
        """Search within a specific knowledge base.

        Returns:
            list[KnowledgeBaseSearchResultTypes]: A list of search results containing the phrase, results, and summaries.
        """
        return await self._search_by_knowledge_base_names(
            phrases=phrases,
            knowledge_base_names=[],
            results=results,
            fragments=fragments,
        )

    async def search_by_name(
        self, knowledge_base_names: list[str], phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Search within a specific knowledge base.

        Returns:
            list[KnowledgeBaseSearchResultTypes]: A list of search results containing the phrase, results, and summaries.
        """
        return await self._search_by_knowledge_base_names(
            phrases=phrases,
            knowledge_base_names=knowledge_base_names,
            results=results,
            fragments=fragments,
        )

    async def get_recent_documents(self, knowledge_base: KnowledgeBase, results: int = 5) -> list[KnowledgeBaseDocument]:
        """Get the most recent documents from a specific knowledge base.

        Returns:
            list[KnowledgeBaseDocument]: A list of the most recent documents.
        """
        index_name = knowledge_base.backend_id

        async with self.error_handler("multi-search operation"):
            search_response = await self.elasticsearch_client.search(
                index=index_name,
                query={"match_all": {}},
                fields=["title", "url", "body"],  # type: ignore
                size=results,
                sort=[{"@timestamp": {"order": "desc"}}],
            )

        if not search_response or not search_response.body or "hits" not in search_response.body:
            msg = f"No recent documents found in knowledge base '{knowledge_base.name}' ({index_name})."
            logger.warning(msg)
            return []

        return [self._hit_to_document(hit=hit) for hit in search_response.body["hits"].get("hits", [])]

    @classmethod
    def _phrase_to_query(cls, phrase: str, knowledge_base_names: list[str], size: int = 5, fragments: int = 5) -> dict[str, Any]:
        """Convert phrase to queries.

        Returns:
            dict[str, Any]: The Elasticsearch query dictionary.
        """
        knowledge_base_match = {"terms": {"knowledge_base_name": knowledge_base_names}} if knowledge_base_names else {"match_all": {}}
        heading_match = {"match": {"headings": {"query": phrase, "boost": 1}}}
        semantic_match = {"semantic": {"field": "body", "query": phrase, "boost": 5}}

        return {
            "query": {"bool": {"filter": knowledge_base_match, "should": [heading_match, semantic_match]}},
            "min_score": 10,
            "sort": [{"_score": {"order": "desc"}}],
            "size": size,
            "highlight": {"number_of_fragments": fragments, "fragment_size": 500, "fields": {"body": {}}},
            "fields": ["title", "url", "body", "knowledge_base_name"],
            "aggs": {"by_kb_name": {"terms": {"field": "knowledge_base_name"}}},
        }

    async def _search_by_knowledge_base_names(
        self, phrases: list[str], knowledge_base_names: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Search across specific indices.

        Returns:
            list[KnowledgeBaseSearchResultTypes]: A list of search results containing the phrase, results, and summaries.
        """
        operations = []

        for phrase in phrases:
            operations.extend(
                (
                    {"index": self.index_pattern},
                    self._phrase_to_query(phrase, knowledge_base_names=knowledge_base_names, size=results, fragments=fragments),
                )
            )

        async with self.error_handler("multi-search operation"):
            msearch_results = await self.elasticsearch_client.options(retry_on_timeout=True).msearch(searches=operations)

        if not msearch_results or "responses" not in msearch_results:
            msg = "No results returned from multi-search operation."
            logger.warning(msg)
            return []

        search_results: list[KnowledgeBaseSearchResultTypes] = []

        for i, response in enumerate(msearch_results["responses"]):
            phrase = phrases[i]

            if not response.get("hits", {}).get("hits"):
                error_message = "No hits found in one of the search responses."
                search_results.append(KnowledgeBaseSearchResultError(phrase=phrase, error=error_message))
                logger.warning(error_message)
                logger.warning(response)
                continue

            summaries: list[PerKnowledgeBaseSummary] = [
                PerKnowledgeBaseSummary(
                    knowledge_base_name=bucket["key"],
                    matches=bucket["doc_count"],
                )
                for bucket in response["aggregations"]["by_kb_name"]["buckets"]
            ]

            phrase_results: list[KnowledgeBaseDocument] = [
                self._hit_to_document(hit=hit) for hit in response.get("hits", {}).get("hits", [])
            ]

            search_results.append(
                KnowledgeBaseSearchResult(
                    phrase=phrase,
                    results=phrase_results,
                    summaries=summaries,
                )
            )

        return search_results

    @classmethod
    def _hit_to_document(cls, hit: dict[str, Any]) -> KnowledgeBaseDocument:
        """Convert an Elasticsearch hit to a KnowledgeBaseDocument.

        Returns:
            KnowledgeBaseDocument: The converted document object.
        """
        doc_id = hit.get("_id", "")

        highlights = hit.get("highlight", {}).get("body", [])

        score = hit.get("_score", 0.0)

        fields = hit.get("fields", {})

        knowledge_base_name = next(iter(fields.get("knowledge_base_name", [])), "<Unknown KB>")

        content = highlights or fields.get("body")

        title: str = next(iter(fields.get("title", ["<No Title>"])))

        url: str = next(iter(fields.get("url", [None])))

        return KnowledgeBaseDocument(
            id=doc_id,
            knowledge_base_name=knowledge_base_name,
            title=title,
            url=url,
            score=score,
            content=content,
        )

    # endregion Search KBs

    # region Insert Documents
    async def insert_documents(self, knowledge_base: KnowledgeBase, documents: list[KnowledgeBaseDocumentProto]) -> None:
        """Add multiple documents to a specific knowledge base.

        Uses _bulk API to insert requested documents into the knowledge base index.

        Raises:
            KnowledgeBaseError: If there is an error inserting documents.
        """
        index_name = knowledge_base.backend_id
        operations = []

        now = round(datetime.now(tz=UTC).timestamp() * 1000)

        for document_proto in documents:
            operations.extend(
                (
                    {"index": {"_index": index_name}},
                    {"@timestamp": now, "title": document_proto.title, "body": document_proto.content},
                )
            )

        if not operations:
            msg = f"Requested to insert documents into knowledge base '{knowledge_base.name}', but no documents provided."
            logger.warning(msg)
            return

        async with self.error_handler(f"inserting documents into knowledge base '{knowledge_base.name} ({index_name})'"):
            result = await self.elasticsearch_client.bulk(operations=operations)

        if result and result.get("errors", False):
            error_message = (
                f"Failed to insert documents into knowledge base '{knowledge_base.name} ({index_name})': {result.get('items', [])}"
            )
            raise KnowledgeBaseError(error_message)

    # endregion Insert Documents

    # region Update Documents
    async def update_document(self, knowledge_base: KnowledgeBase, document_id: str, document_update: KnowledgeBaseDocumentProto) -> None:
        """Update multiple documents in a specific knowledge base."""
        index_name = knowledge_base.backend_id

        async with self.error_handler(f"updating document {document_id} in knowledge base '{knowledge_base.name} ({index_name})'"):
            await self.elasticsearch_client.update(index=index_name, id=document_id, doc=document_update.model_dump())

    # endregion Update Documents

    # region Delete Documents
    async def delete_document(self, knowledge_base: KnowledgeBase, document_id: str) -> None:
        """Delete multiple documents from a specific knowledge base."""
        index_name = knowledge_base.backend_id

        async with self.error_handler(f"deleting document {document_id} from knowledge base '{knowledge_base.name} ({index_name})'"):
            await self.elasticsearch_client.delete(index=index_name, id=document_id)

    # endregion Delete Documents

    @classmethod
    def _url_to_index_name(cls, url: str) -> str:
        """Convert URL to a valid Elasticsearch index name.

        Returns:
            str: The converted index name.
        """
        # Convert URL to a valid index name
        # We can have 256 characters of lowercase alphanumeric characters, underscores, hyphens and periods

        # We'll want to keep only the first 50 characters of the URL
        # we want www.python.org/docs/index.html to turn into www_python_org.docs.index_html
        # so we replace dots with underscores
        # slashes with dots
        # strip all other characters
        new_index_name = url.replace("https://", "").replace("http://", "").replace(".", "_").replace("/", ".").replace("-", "_")
        new_index_name = "".join(c for c in new_index_name if c.isalnum() or c in {"_", "-", "."})
        # trim off any leading or trailing dashes, underscores, or periods

        return new_index_name[:50].strip("-_.").lower()

    @classmethod
    def _insert_runtime_kb_name(cls, index_mappings: dict[str, Any], kb_name: str) -> dict[str, Any]:
        """Insert a runtime mapping value into the given mapping.

        Returns:
            dict[str, Any]: The updated index mappings with the runtime field.
        """
        escaped_value = kb_name.replace('"', '\\"')

        return index_mappings | {
            "runtime": {
                "knowledge_base_name": {
                    "type": "keyword",
                    "script": {
                        "source": f"emit('{escaped_value}')",
                    },
                }
            },
        }

    @classmethod
    def _insert_metadata(cls, index_mappings: dict[str, Any], knowledge_base_create_proto: KnowledgeBaseCreateProto) -> dict[str, Any]:
        """Build the Elasticsearch _meta mapping from a KnowledgeBaseCreateProto.

        Returns:
            dict[str, Any]: The updated index mappings with the metadata.
        """
        return index_mappings | {
            "_meta": {
                "knowledge_base": {
                    "name": knowledge_base_create_proto.name,
                    "data_source": knowledge_base_create_proto.data_source,
                    "description": knowledge_base_create_proto.description,
                    "type": knowledge_base_create_proto.type,
                }
            }
        }
