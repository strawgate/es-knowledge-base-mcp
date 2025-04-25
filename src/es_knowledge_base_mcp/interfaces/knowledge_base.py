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
        """
        Get a list of all knowledge bases.

        Returns:
            list[KnowledgeBase]: A list of all KnowledgeBase objects currently available.

        Example:
            >>> kbs = await client.get()
            >>> for kb in kbs:
            ...     print(f"Name: {kb.name}, Type: {kb.type}, Docs: {kb.doc_count}")
        """
        ...

    async def create(self, knowledge_base_create_proto: KnowledgeBaseCreateProto) -> KnowledgeBase:
        """
        Create a new knowledge base.

        Args:
            knowledge_base_create_proto (KnowledgeBaseCreateProto): The prototype object containing the details for the new knowledge base.

        Returns:
            KnowledgeBase: The newly created KnowledgeBase object.

        Example:
            >>> create_proto = KnowledgeBaseCreateProto(name="My Docs", type="docs", data_source="http://example.com/docs", description="Documentation for My Project")
            >>> new_kb = await client.create(knowledge_base_create_proto=create_proto)
        """
        ...

    async def update(self, knowledge_base: KnowledgeBase, knowledge_base_update: KnowledgeBaseUpdateProto):
        """
        Update editable fields of an existing knowledge base.

        Args:
            knowledge_base (KnowledgeBase): The KnowledgeBase object to update.
            knowledge_base_update (KnowledgeBaseUpdateProto): The prototype object containing the updated details.
        """
        ...

    async def delete(self, knowledge_base: KnowledgeBase) -> None:
        """
        Delete a knowledge base.

        Args:
            knowledge_base (KnowledgeBase): The KnowledgeBase object to delete.
        """
        ...

    async def search_all(self, phrases: list[str], results: int = 5, fragments: int = 5) -> list[KnowledgeBaseSearchResult]:
        """
        Search across all knowledge bases.

        Args:
            phrases (list[str]): List of phrases to search for across all knowledge bases.
            results (int): Number of search results to return for each phrase.
            fragments (int): Number of content fragments to return for each search result.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each phrase.
        """
        ...

    async def search(
        self, knowledge_bases: list[KnowledgeBase], phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResult]:
        """
        Search within specific knowledge bases.

        Args:
            knowledge_bases (list[KnowledgeBase]): A list of KnowledgeBase objects to search within.
            phrases (list[str]): List of phrases to search for within the specified knowledge bases.
            results (int): Number of search results to return for each phrase.
            fragments (int): Number of content fragments to return for each search result.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each phrase.
        """
        ...

    async def get_recent_documents(self, knowledge_base: KnowledgeBase, results: int = 5) -> list[KnowledgeBaseDocument]:
        """
        Get the most recent documents from a specific knowledge base.

        Args:
            knowledge_base (KnowledgeBase): The KnowledgeBase object to retrieve recent documents from.
            results (int): The maximum number of recent documents to return.

        Returns:
            list[KnowledgeBaseDocument]: A list of the most recent documents.
        """
        ...

    async def insert_documents(self, knowledge_base: KnowledgeBase, documents: list[KnowledgeBaseDocumentProto]) -> None:
        """
        Add multiple documents to a specific knowledge base.

        Args:
            knowledge_base (KnowledgeBase): The KnowledgeBase object to add documents to.
            documents (list[KnowledgeBaseDocumentProto]): A list of document prototypes to insert.
        """
        ...

    async def get_by_name(self, name: str) -> KnowledgeBase:
        """
        Get a knowledge base by its name.

        Args:
            name (str): The name of the knowledge base to retrieve.

        Returns:
            KnowledgeBase: The KnowledgeBase object with the specified name.

        Raises:
            KnowledgeBaseNotFoundError: If no knowledge base with the given name is found.
            KnowledgeBaseNonUniqueError: If multiple knowledge bases with the same name are found.

        Example:
            >>> kb = await client.get_by_name(name="My Docs")
            >>> print(f"Found knowledge base: {kb.backend_id}")
        """

        kbs = await self.get()

        matching_kbs = [kb for kb in kbs if kb.name == name]

        return self._verify_just_one(matching_kbs)

    async def try_get_by_name(self, name: str) -> Optional[KnowledgeBase]:
        """
        Try to get a knowledge base by name, returning None if not found.

        Args:
            name (str): The name of the knowledge base to retrieve.

        Returns:
            Optional[KnowledgeBase]: The KnowledgeBase object if found, otherwise None.
        """
        try:
            return await self.get_by_name(name)
        except (KnowledgeBaseNotFoundError, KnowledgeBaseNonUniqueError):
            return None

    async def get_by_backend_id(self, backend_id: str) -> KnowledgeBase:
        """
        Get a knowledge base by its backend ID.

        Args:
            backend_id (str): The backend ID of the knowledge base to retrieve.

        Returns:
            KnowledgeBase: The KnowledgeBase object with the specified backend ID.

        Raises:
            KnowledgeBaseNotFoundError: If no knowledge base with the given backend ID is found.
            KnowledgeBaseNonUniqueError: If multiple knowledge bases with the same backend ID are found (should not happen with unique IDs).

        Example:
            >>> kb = await client.get_by_backend_id(backend_id="my-kb-12345")
            >>> print(f"Found knowledge base: {kb.name}")
        """

        kbs = await self.get()

        matching_kbs = [kb for kb in kbs if kb.backend_id == backend_id]

        return self._verify_just_one(matching_kbs)

    async def try_get_by_backend_id(self, backend_id: str) -> Optional[KnowledgeBase]:
        """
        Try to get a knowledge base by backend ID, returning None if not found.

        Args:
            backend_id (str): The backend ID of the knowledge base to retrieve.

        Returns:
            Optional[KnowledgeBase]: The KnowledgeBase object if found, otherwise None.
        """
        try:
            return await self.get_by_backend_id(backend_id)
        except (KnowledgeBaseNotFoundError, KnowledgeBaseNonUniqueError):
            return None

    async def get_by_backend_id_or_name(self, backend_id_or_name: str) -> KnowledgeBase:
        """
        Get a knowledge base by its backend ID or name.

        This method first attempts to retrieve the knowledge base by backend ID.
        If not found, it then attempts to retrieve it by name.

        Args:
            backend_id_or_name (str): The backend ID or name of the knowledge base to retrieve.

        Returns:
            KnowledgeBase: The KnowledgeBase object with the specified ID or name.

        Raises:
            KnowledgeBaseNotFoundError: If no knowledge base with the given ID or name is found.
            KnowledgeBaseNonUniqueError: If multiple knowledge bases match the provided name.

        Example:
            >>> kb = await client.get_by_backend_id_or_name("my-kb-12345") # By ID
            >>> print(f"Found knowledge base: {kb.name}")
            >>> kb = await client.get_by_backend_id_or_name("My Docs") # By Name
            >>> print(f"Found knowledge base: {kb.backend_id}")
        """

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
        """
        Update the metadata of an existing knowledge base by its backend ID.

        Args:
            backend_id (str): The backend ID of the knowledge base to update.
            knowledge_base_update (KnowledgeBaseUpdateProto): The prototype object containing the updated details.

        Example:
            >>> update_proto = KnowledgeBaseUpdateProto(name="Updated Docs", description="Revised documentation")
            >>> await client.update_by_backend_id(backend_id="my-kb-12345", knowledge_base_update=update_proto)
        """

        knowledge_base = await self.get_by_backend_id(backend_id)

        await self.update(knowledge_base, knowledge_base_update)

    async def update_by_name(self, name: str, knowledge_base_update: KnowledgeBaseUpdateProto) -> None:
        """
        Update the description of an existing knowledge base by its name.

        Args:
            name (str): The name of the knowledge base to update.
            knowledge_base_update (KnowledgeBaseUpdateProto): The prototype object containing the updated details.

        Example:
            >>> update_proto = KnowledgeBaseUpdateProto(name="Updated Docs", description="Revised documentation")
            >>> await client.update_by_name(name="My Docs", knowledge_base_update=update_proto)
        """

        knowledge_base = await self.get_by_name(name)

        await self.update(knowledge_base, knowledge_base_update)

    async def delete_by_backend_id(self, backend_id: str) -> None:
        """
        Delete a knowledge base by its backend ID.

        Args:
            backend_id (str): The backend ID of the knowledge base to delete.

        Example:
            >>> await client.delete_by_backend_id(backend_id="my-kb-12345")
        """

        knowledge_base = await self.get_by_backend_id(backend_id=backend_id)

        await self.delete(knowledge_base)

    async def delete_by_backend_ids(self, backend_ids: list[str]) -> None:
        """
        Delete knowledge bases by their backend IDs.

        Args:
            backend_ids (list[str]): The backend IDs of the knowledge bases to delete.

        Example:
            >>> await client.delete_by_backend_ids(backend_ids=["kb-1", "kb-2"])
        """

        for backend_id in backend_ids:
            knowledge_base = await self.get_by_backend_id(backend_id=backend_id)

            await self.delete(knowledge_base)

    async def delete_by_name(self, name: str) -> None:
        """
        Delete a knowledge base by its name.

        Args:
            name (str): The name of the knowledge base to delete.

        Example:
            >>> await client.delete_by_name(name="My Docs")
        """

        knowledge_base = await self.get_by_name(name)

        await self.delete(knowledge_base)

    async def search_by_backend_id(
        self, backend_id: str, phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResult]:
        """
        Search within a knowledge base by its backend ID.

        Args:
            backend_id (str): The backend ID of the knowledge base to search within.
            phrases (list[str]): List of phrases to search for within the knowledge base.
            results (int): Number of search results to return for each question.
            fragments (int): Number of content fragments to return for each search result.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each phrase.

        Example:
            >>> search_results = await client.search_by_backend_id(backend_id="my-kb-12345", phrases=["search term"])
            >>> for result in search_results:
            ...     print(f"Phrase: {result.phrase}")
            ...     for doc in result.results:
            ...         print(f"  - {doc.title} ({doc.score})")
        """

        knowledge_base = await self.get_by_backend_id(backend_id)

        return await self.search([knowledge_base], phrases, results, fragments)

    async def search_by_names(
        self, names: list[str], phrases: list[str], results: int = 5, fragments: int = 5
    ) -> list[KnowledgeBaseSearchResult]:
        """
        Search within knowledge bases by their names.

        Args:
            names (list[str]): The names of the knowledge bases to search within.
            phrases (list[str]): List of phrases to search for within the specified knowledge bases.
            results (int): Number of search results to return for each question.
            fragments (int): Number of content fragments to return for each search result.

        Returns:
            list[KnowledgeBaseSearchResult]: A list of search results, one for each phrase.

        Example:
            >>> search_results = await client.search_by_names(names=["My Docs", "Another KB"], phrases=["search term"])
            >>> for result in search_results:
            ...     print(f"Phrase: {result.phrase}")
            ...     for doc in result.results:
            ...         print(f"  - {doc.title} ({doc.score})")
        """

        knowledge_bases = [await self.get_by_name(name) for name in names]

        return await self.search(knowledge_bases, phrases, results, fragments)

    async def insert_document(self, knowledge_base: KnowledgeBase, document: KnowledgeBaseDocumentProto) -> None:
        """
        Add a single document to a specific knowledge base.

        Args:
            knowledge_base (KnowledgeBase): The KnowledgeBase object to add the document to.
            document (KnowledgeBaseDocumentProto): The document prototype to insert.

        Example:
            >>> doc_proto = KnowledgeBaseDocumentProto(title="New Article", content="This is the content of the new article.")
            >>> await client.insert_document(knowledge_base=my_kb, document=doc_proto)
        """

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
