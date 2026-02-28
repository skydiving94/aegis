"""Repository for PGVector database interactions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.vector.enums import EmbeddingCategory
from core.vector.pgvector.entities import DocumentEmbedding


class PGVectorRepository:
    """Repository handling raw DB operations for pgvector entities."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def upsert(
        self,
        id: str,
        text: str,
        embedding: list[float],
        category: str,
        metadata_json: dict[str, Any],
    ) -> None:
        """Upsert a document embedding."""
        async with self._session_factory() as session:
            orm = DocumentEmbedding(
                id=id,
                text=text,
                embedding=embedding,
                category=category,
                metadata_json=metadata_json,
            )
            await session.merge(orm)
            await session.commit()

    async def similarity_search(
        self,
        query_embedding: list[float],
        category: str | None = None,
        limit: int = 5,
    ) -> list[DocumentEmbedding]:
        """Search similar documents by distance."""
        async with self._session_factory() as session:
            stmt = select(DocumentEmbedding)
            if category:
                stmt = stmt.where(DocumentEmbedding.category == category)
            
            # Using pgvector cosine distance: embedding.cosine_distance(query)
            stmt = stmt.order_by(DocumentEmbedding.embedding.cosine_distance(query_embedding)).limit(limit)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
