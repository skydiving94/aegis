"""SQLAlchemy ORM Dependency Registry entity definition."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class DependencyRegistry(Base):
    """ORM for tracking user-approved pip packages."""

    __tablename__ = "dependency_registry"
    __table_args__ = {"schema": "framework"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    package_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_install: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
