"""Knowledge Base Interface
This module defines the interface for managing and interacting with knowledge bases.
It includes models for knowledge bases, search results, and various exceptions related to knowledge base operations.
"""

from typing import List, Optional, Protocol

from pydantic import Field

from es_knowledge_base_mcp.errors.knowledge_base import KnowledgeBaseNonUniqueError, KnowledgeBaseNotFoundError, KnowledgeBaseRetrievalError
from es_knowledge_base_mcp.models.base import ExportableModel

# Manually define the fields for our Knowledge Base models so that we can order the fields
# in the order we want when we dump to yaml, json, or other formats... This is a workaround
kb_name_field = Field(description="The name of the knowledge base, used for identification and retrieval.")

kb_description_field = Field(description="A brief description of the knowledge base, providing context and purpose.")

kb_type_field = Field(description="The type of the knowledge base, e.g., 'docs', 'memory'")
kb_data_source_field = Field(
    description="The data source of the knowledge base, which could be a file path, url, or a description of the source."
)

kb_backend_id_field = Field(description="The backend ID of the knowledge base, used for internal identification.")

kb_doc_count_field = Field(description="Number of documents in the knowledge base, useful for monitoring and management.")


class KnowledgeBaseUpdateProto(ExportableModel):
    """Model for requesting an update to a Knowledge Base"""

    name: str = kb_name_field
    description: str = kb_description_field


class KnowledgeBaseCreateProto(ExportableModel):
    """Model for requesting the creation of a Knowledge Base"""

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
        """Converts the object to a KnowledgeBaseCreateProto."""

        return KnowledgeBaseCreateProto(
            name=self.name,
            type=self.type,
            data_source=self.data_source,
            description=self.description,
        )

    def to_update_proto(self) -> KnowledgeBaseUpdateProto:
        """Converts the object to a KnowledgeBaseUpdateProto."""

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

    knowledge_base_name: str = kb_name_field
    title: str = document_title_field
    url: str = Field(description="The original URL of the document searched.")
    score: float = Field(description="Relevance score of the search result, typically a float value.")
    content: List[str] = document_content_field


class KnowledgeBaseSearchResult(ExportableModel):
    """Model for search results from a Knowledge Base."""

    phrase: str = Field(description="The search phrase used to query the knowledge base.")
    results: List[KnowledgeBaseDocument] = Field(default_factory=list, description="List of search results from the knowledge base.")


# @runtime_checkable
class KnowledgeBaseClient(Protocol):
    """
    Protocol defining the interface for a Knowledge Base client.
    Implementations of this protocol provide methods for managing and searching knowledge bases.
    """

    async def get(self) -> list[KnowledgeBase]:
        """Get a list of all knowledge bases."""
        ...

    async def create(self, knowledge_base_create_proto: KnowledgeBaseCreateProto) -> KnowledgeBase:
        """Create a new knowledge base."""
        ...

    async def update(self, knowledge_base: KnowledgeBase, knowledge_base_update: KnowledgeBaseUpdateProto):
        """Update editable fields of an existing knowledge base."""
        ...

    async def delete(self, knowledge_base: KnowledgeBase) -> None:
        """Delete a knowledge base."""
        ...

    async def search_all(self, phrases: list[str], results: int = 5, fragments: int = 5) -> list[KnowledgeBaseSearchResult]:
        """Search across all knowledge bases.
        Args:
            phrases (list[str]): List of phrases to search for across all knowledge bases.
            results (int): Number of search results to return for each phrase.
            fragments (int): Number of content fragments to return for each search result.
        """
        ...

    async def search(
        self, knowledge_base: KnowledgeBase, phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResult]:
        """Search within a specific knowledge base."""
        ...

    async def get_recent_documents(self, knowledge_base: KnowledgeBase, results: int = 5) -> list[KnowledgeBaseDocument]:
        """Get the most recent documents from a specific knowledge base."""
        ...

    async def insert_documents(self, knowledge_base: KnowledgeBase, documents: list[KnowledgeBaseDocumentProto]) -> None:
        """Add multiple documents to a specific knowledge base."""
        ...

    async def get_by_name(self, name: str) -> KnowledgeBase:
        """Get a knowledge base by its name."""

        kbs = await self.get()

        matching_kbs = [kb for kb in kbs if kb.name == name]

        return self._verify_just_one(matching_kbs)

    async def try_get_by_name(self, name: str) -> Optional[KnowledgeBase]:
        """Try to get a knowledge base by name, returning None if not found.
        Args:
            name (str): The name of the knowledge base to retrieve.
        """
        try:
            return await self.get_by_name(name)
        except (KnowledgeBaseNotFoundError, KnowledgeBaseNonUniqueError):
            return None

    async def get_by_backend_id(self, backend_id: str) -> KnowledgeBase:
        """Get a knowledge base by its backend ID. Raises KnowledgeBaseNotFoundError if not found.
        Args:
            backend_id (str): The backend ID of the knowledge base to retrieve.
        """

        kbs = await self.get()

        matching_kbs = [kb for kb in kbs if kb.backend_id == backend_id]

        return self._verify_just_one(matching_kbs)

    async def try_get_by_backend_id(self, backend_id: str) -> Optional[KnowledgeBase]:
        """Try to get a knowledge base by backend ID, returning None if not found.
        Args:
            backend_id (str): The backend ID of the knowledge base to retrieve.
        """
        try:
            return await self.get_by_backend_id(backend_id)
        except (KnowledgeBaseNotFoundError, KnowledgeBaseNonUniqueError):
            return None

    async def get_by_backend_id_or_name(self, backend_id_or_name: str) -> KnowledgeBase:
        """Get a knowledge base by its backend ID or name.
        This method first attempts to retrieve the knowledge base by backend ID.
        If not found, it then attempts to retrieve it by name.
        Args:
            backend_id_or_name (str): The backend ID or name of the knowledge base to retrieve."""

        # Try to get by backend ID first
        kb = await self.try_get_by_backend_id(backend_id_or_name)
        if kb is not None:
            return kb

        # If not found, try to get by name
        kb = await self.try_get_by_name(backend_id_or_name)
        if kb is not None:
            return kb

        raise KnowledgeBaseNotFoundError(f"Knowledge Base with ID or name '{backend_id_or_name}' not found.")

    async def update_by_backend_id(self, backend_id: str, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """Update the metadata of an existing knowledge base by its backend ID."""

        knowledge_base = await self.get_by_backend_id(backend_id)

        await self.update(knowledge_base, knowledge_base_update)

    async def update_by_name(self, name: str, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """Update the description of an existing knowledge base by its name."""

        knowledge_base = await self.get_by_name(name)

        await self.update(knowledge_base, knowledge_base_update)

    async def delete_by_backend_id(self, backend_id: str) -> None:
        """Delete a knowledge base by its backend ID.
        Args:
            backend_id (str): The backend ID of the knowledge base to delete.
        """

        knowledge_base = await self.get_by_backend_id(backend_id=backend_id)

        await self.delete(knowledge_base)

    async def delete_by_backend_ids(self, backend_ids: list[str]) -> None:
        """Delete knowledge bases by their backend IDs.
        Args:
            backend_ids (list[str]): The backend IDs of the knowledge base to delete.
        """

        for backend_id in backend_ids:
            knowledge_base = await self.get_by_backend_id(backend_id=backend_id)

            await self.delete(knowledge_base)

    async def delete_by_name(self, name: str) -> None:
        """Delete a knowledge base by its name.
        Args:
            name (str): The name of the knowledge base to delete.
        """

        knowledge_base = await self.get_by_name(name)

        await self.delete(knowledge_base)

    async def search_by_backend_id(
        self, backend_id: str, phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResult]:
        """Search within a knowledge base by its backend ID.
        Args:
            backend_id (str): The backend ID of the knowledge base to search within.
            phrases (list[str]): List of phrases to search for within the knowledge base.
            results (int): Number of search results to return for each question.
            fragments (int): Number of content fragments to return for each search result.
        """

        knowledge_base = await self.get_by_backend_id(backend_id)

        return await self.search(knowledge_base, phrases, results, fragments)

    async def search_by_name(self, name: str, phrases: list[str], results: int = 5, fragments: int = 5) -> list[KnowledgeBaseSearchResult]:
        """Search within a knowledge base by its name.
        Args:
            name (str): The name of the knowledge base to search within.
            phrases (list[str]): List of phrases to search for within the knowledge base.
            results (int): Number of search results to return for each question.
            fragments (int): Number of content fragments to return for each search result.
        """

        knowledge_base = await self.get_by_name(name)

        return await self.search(knowledge_base, phrases, results, fragments)

    async def insert_document(self, knowledge_base: KnowledgeBase, document: KnowledgeBaseDocumentProto) -> None:
        """Add a single document to a specific knowledge base."""

        await self.insert_documents(knowledge_base, [document])

    def _verify_just_one(self, knowledge_base: KnowledgeBase | list[KnowledgeBase] | None) -> KnowledgeBase:
        """Check if exactly one knowledge base is present."""

        if knowledge_base is None:
            raise KnowledgeBaseNotFoundError("No knowledge base found.")

        if isinstance(knowledge_base, list):
            if len(knowledge_base) == 0:
                raise KnowledgeBaseNotFoundError("No knowledge base found.")
            if len(knowledge_base) > 1:
                raise KnowledgeBaseNonUniqueError("Multiple knowledge bases found, expected one.")

            return knowledge_base[0]

        elif not isinstance(knowledge_base, KnowledgeBase):
            raise KnowledgeBaseRetrievalError("Expected a single KnowledgeBase instance or a list of KnowledgeBase instances.")

        return knowledge_base
