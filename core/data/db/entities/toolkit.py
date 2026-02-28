"""SQLAlchemy ORM Toolkit entity definition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class Toolkit(Base):
    """ORM for toolkit modules."""

    __tablename__ = "toolkits"
    __table_args__ = {"schema": "framework"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    module_path: Mapped[str] = mapped_column(String, nullable=False)
    public_api: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    dependencies: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
