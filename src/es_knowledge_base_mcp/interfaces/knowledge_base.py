"""Knowledge Base Interface."""

# This module defines the interface for managing and interacting with knowledge bases.
# It includes models for knowledge bases, search results, and various exceptions related to knowledge base operations.

from typing import Protocol

from pydantic import Field

from es_knowledge_base_mcp.errors.knowledge_base import KnowledgeBaseNonUniqueError, KnowledgeBaseNotFoundError
from es_knowledge_base_mcp.models.base import ExportableModel

kb_name_field = Field(description="The name of the knowledge base, used for identification and retrieval.")

kb_description_field = Field(description="A brief description of the knowledge base, providing context and purpose.")

kb_type_field = Field(description="The type of the knowledge base, e.g., 'docs', 'memory'")
kb_data_source_field = Field(
    description="The data source of the knowledge base, which could be a file path, url, or a description of the source.",
    examples=["http://example.com/docs"],
)

kb_backend_id_field = Field(description="The backend ID of the knowledge base, used for internal identification.")

kb_doc_count_field = Field(description="Number of documents in the knowledge base, useful for monitoring and management.")


class KnowledgeBaseUpdateProto(ExportableModel):
    """Model for requesting an update to a Knowledge Base."""

    name: str = kb_name_field
    description: str = kb_description_field


class KnowledgeBaseCreateProto(ExportableModel):
    """Model for requesting the creation of a Knowledge Base."""

    name: str = kb_name_field
    type: str = kb_type_field
    data_source: str = kb_data_source_field
    description: str = kb_description_field


class KnowledgeBase(ExportableModel):
    """Model representing a Knowledge Base entry."""

    name: str = kb_name_field
    type: str = kb_type_field
    description: str = kb_description_field
    data_source: str = kb_data_source_field
    backend_id: str = kb_backend_id_field
    doc_count: int = kb_doc_count_field

    def to_create_proto(self) -> KnowledgeBaseCreateProto:
        """Convert the object to a KnowledgeBaseCreateProto.

        Returns:
            KnowledgeBaseCreateProto: The converted knowledge base creation prototype.
        """
        return KnowledgeBaseCreateProto(
            name=self.name,
            type=self.type,
            data_source=self.data_source,
            description=self.description,
        )

    def to_update_proto(self) -> KnowledgeBaseUpdateProto:
        """Convert the object to a KnowledgeBaseUpdateProto.

        Returns:
            KnowledgeBaseUpdateProto: The converted knowledge base update prototype.
        """
        return KnowledgeBaseUpdateProto(
            name=self.name,
            description=self.description,
        )


document_title_field = Field(description="A friendly `title` for knowledge base document.")
document_content_field = Field(description="The content of the search result, typically a list of text fragments.")


class KnowledgeBaseDocumentProto(ExportableModel):
    """Model for requesting a document be added to a Knowledge Base."""

    title: str = document_title_field
    content: str = document_content_field


class KnowledgeBaseDocument(ExportableModel):
    """Model for a search result from a Knowledge Base."""

    id: str = Field(description="The Elasticsearch document ID.")
    knowledge_base_name: str = kb_name_field
    title: str = document_title_field
    url: str | None = Field(description="The original URL of the document searched.")
    score: float | None = Field(description="Relevance score of the search result, typically a float value.")
    content: list[str] = document_content_field


class PerKnowledgeBaseSummary(ExportableModel):
    """A summary of the number of results found in each knowledge base for the provided search phrases."""

    knowledge_base_name: str = kb_name_field
    matches: int = Field(description="The number of documents that matched the search phrase in this knowledge base.")


type KnowledgeBaseSearchResultTypes = KnowledgeBaseSearchResult | KnowledgeBaseSearchResultError


class KnowledgeBaseSearchResult(ExportableModel):
    """Model for search results from a Knowledge Base."""

    phrase: str = Field(description="The search phrase used to query the knowledge base.")
    summaries: list[PerKnowledgeBaseSummary] = Field(
        default_factory=list, description="Summary of other results found in each knowledge base for the search phrase."
    )
    results: list[KnowledgeBaseDocument] = Field(
        default_factory=list, description="List of highest scoring search results from the knowledge base."
    )


class KnowledgeBaseSearchResultError(ExportableModel):
    """Model for errors encountered during a knowledge base search."""

    phrase: str = Field(description="The search phrase that caused the error.")
    error: str = Field(description="Description of the error encountered during the search.")


# @runtime_checkable
class KnowledgeBaseClient(Protocol):
    """Protocol defining the interface for a Knowledge Base client."""

    # Implementations of this protocol provide methods for managing and searching knowledge bases.

    async def get(self) -> list[KnowledgeBase]:
        """Get a list of all knowledge bases.

        Returns:
            list[KnowledgeBase]: A list of all KnowledgeBase objects currently available.
        """
        ...

    async def create(self, knowledge_base_create_proto: KnowledgeBaseCreateProto) -> KnowledgeBase:
        """Create a new knowledge base.

        Returns:
            KnowledgeBase: The newly created KnowledgeBase object.
        """
        ...

    async def update(self, knowledge_base: KnowledgeBase, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """Update editable fields of an existing knowledge base."""
        ...

    async def delete(self, knowledge_base: KnowledgeBase) -> None:
        """Delete a knowledge base."""
        ...

    async def search(self, phrases: list[str], results: int = 5, fragments: int = 5) -> list[KnowledgeBaseSearchResultTypes]:
        """Search across all knowledge bases.

        Returns:
            list[KnowledgeBaseSearchResultTypes]: A list of search results, one for each phrase.
        """
        ...

    async def search_by_name(
        self, knowledge_base_names: list[str], phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResultTypes]:
        """Search within specific knowledge bases.

        Returns:
            list[KnowledgeBaseSearchResultTypes]: A list of search results, one for each phrase.
        """
        ...

    async def get_recent_documents(self, knowledge_base: KnowledgeBase, results: int = 5) -> list[KnowledgeBaseDocument]:
        """Get the most recent documents from a specific knowledge base.

        Returns:
            list[KnowledgeBaseDocument]: A list of the most recent documents.
        """
        ...

    async def insert_documents(self, knowledge_base: KnowledgeBase, documents: list[KnowledgeBaseDocumentProto]) -> None:
        """Add multiple documents to a specific knowledge base."""
        ...

    async def delete_document(self, knowledge_base: KnowledgeBase, document_id: str) -> None:
        """Delete multiple documents from a specific knowledge base."""
        ...

    async def update_document(self, knowledge_base: KnowledgeBase, document_id: str, document_update: KnowledgeBaseDocumentProto) -> None:
        """Update multiple documents in a specific knowledge base."""
        ...

    async def get_by_name(self, name: str) -> KnowledgeBase:
        """Get a knowledge base by its name.

        Returns:
            KnowledgeBase: The KnowledgeBase object with the specified name.
        """
        kbs = await self.get()

        matching_kbs = [kb for kb in kbs if kb.name == name]

        return self._verify_just_one(matching_kbs)

    async def try_get_by_name(self, name: str) -> KnowledgeBase | None:
        """Try to get a knowledge base by name, returning None if not found.

        Returns:
            Optional[KnowledgeBase]: The KnowledgeBase object if found, otherwise None.
        """
        try:
            return await self.get_by_name(name)
        except (KnowledgeBaseNotFoundError, KnowledgeBaseNonUniqueError):
            return None

    async def update_by_name(self, name: str, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """Update the description of an existing knowledge base by its name."""
        knowledge_base = await self.get_by_name(name)

        await self.update(knowledge_base, knowledge_base_update)

    async def delete_by_name(self, name: str) -> None:
        """Delete a knowledge base by its name."""
        knowledge_base = await self.get_by_name(name)

        await self.delete(knowledge_base)

    async def insert_document(self, knowledge_base: KnowledgeBase, document: KnowledgeBaseDocumentProto) -> None:
        """Add a single document to a specific knowledge base."""
        await self.insert_documents(knowledge_base, [document])

    def _verify_just_one(self, knowledge_base: KnowledgeBase | list[KnowledgeBase] | None) -> KnowledgeBase:
        """Check if exactly one knowledge base is present.

        Returns:
            KnowledgeBase: The single KnowledgeBase instance if found, otherwise raises an error.

        Raises:
            KnowledgeBaseNotFoundError: If no knowledge base is found.
            KnowledgeBaseNonUniqueError: If multiple knowledge bases are found.
        """
        if knowledge_base is None:
            msg = "No knowledge base found."
            raise KnowledgeBaseNotFoundError(msg)

        if isinstance(knowledge_base, list):
            if not knowledge_base:
                msg = "No knowledge base found."
                raise KnowledgeBaseNotFoundError(msg)
            if len(knowledge_base) > 1:
                msg = "Multiple knowledge bases found, expected one."
                raise KnowledgeBaseNonUniqueError(msg)

            return knowledge_base[0]

        return knowledge_base
