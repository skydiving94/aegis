"""SQLAlchemy ORM Skill entity definition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class Skill(Base):
    """ORM for skill definitions."""

    __tablename__ = "skills"
    __table_args__ = {"schema": "framework"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    nodes: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    edges: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    is_meta: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
