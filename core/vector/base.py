"""Abstract base class for vector storage operations."""

import abc
from typing import Any

from core.vector.enums import EmbeddingCategory


class AbstractVectorStore(abc.ABC):
    """Abstract interface for vector stores (e.g., pgvector, pinecone)."""

    @abc.abstractmethod
    async def upsert(
        self,
        id: str,
        text: str,
        embedding: list[float],
        category: EmbeddingCategory,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a document embedding."""
        ...

    @abc.abstractmethod
    async def similarity_search(
        self,
        query_embedding: list[float],
        category: EmbeddingCategory | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar embeddings.

        Returns:
            A list of dicts containing id, text, distance, and metadata.
        """
        ...
