"""PGVector implementation of the AbstractVectorStore."""

from typing import Any

from core.vector.base import AbstractVectorStore
from core.vector.enums import EmbeddingCategory
from core.vector.pgvector.repository import PGVectorRepository


class PGVectorStore(AbstractVectorStore):
    """Adapter for pgvector storage matching the AbstractVectorStore interface."""

    def __init__(self, repository: PGVectorRepository) -> None:
        self._repository = repository

    async def upsert(
        self,
        id: str,
        text: str,
        embedding: list[float],
        category: EmbeddingCategory,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert document embedding using the repository."""
        await self._repository.upsert(
            id=id,
            text=text,
            embedding=embedding,
            category=category.value,
            metadata_json=metadata or {},
        )

    async def similarity_search(
        self,
        query_embedding: list[float],
        category: EmbeddingCategory | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Perform a similarity search."""
        cat_val = category.value if category else None
        results = await self._repository.similarity_search(
            query_embedding=query_embedding,
            category=cat_val,
            limit=limit,
        )
        return [
            {
                "id": r.id,
                "text": r.text,
                "category": r.category,
                "metadata": r.metadata_json,
            }
            for r in results
        ]
