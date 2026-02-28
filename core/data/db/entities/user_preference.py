"""SQLAlchemy ORM User Preference entity definition."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class UserPreference(Base):
    """ORM for persistent user preferences and feedback."""

    __tablename__ = "user_preferences"
    __table_args__ = {"schema": "framework"}

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="user")  # "user", "clarification", "feedback"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
