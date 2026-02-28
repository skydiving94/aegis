"""SQLAlchemy ORM Objective entity definition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Float, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class Objective(Base):
    """ORM for user objectives (for reuse matching)."""

    __tablename__ = "objectives"
    __table_args__ = {"schema": "framework"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    skill_id: Mapped[str | None] = mapped_column(String, nullable=True)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
