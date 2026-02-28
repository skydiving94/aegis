"""SQLAlchemy ORM definitions for pgvector embeddings."""

from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.vector.enums import EmbeddingCategory


class VectorBase(DeclarativeBase):
    """Base class for vector ORM models."""
    pass


class DocumentEmbedding(VectorBase):
    """ORM representing an embedded document with pgvector."""

    __tablename__ = "document_embeddings"
    __table_args__ = {"schema": "vector_store"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))  # Default OpenAI size
    category: Mapped[str] = mapped_column(String, nullable=False)  # EmbeddingCategory value
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
