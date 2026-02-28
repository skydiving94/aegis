"""SQLAlchemy ORM Task entity definition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.data.db.entities.base import Base

class Task(Base):
    """ORM for task definitions (both Python and LLM tasks)."""

    __tablename__ = "tasks"
    __table_args__ = {"schema": "framework"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # "python" | "llm"
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    preconditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    toolkit_refs: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String, default="low")
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_budget: Mapped[int] = mapped_column(Integer, default=32000)
    max_retries: Mapped[int] = mapped_column(Integer, default=10)
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
