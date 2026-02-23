"""SQLAlchemy ORM table definitions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class TaskORM(Base):
    """ORM for task definitions (both Python and LLM tasks)."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # "python" | "llm"
    inputs: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    outputs: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    preconditions: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    toolkit_refs: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    risk_level: Mapped[str] = mapped_column(String, default="low")
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_budget: Mapped[int] = mapped_column(Integer, default=32000)
    max_retries: Mapped[int] = mapped_column(Integer, default=10)
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SkillORM(Base):
    """ORM for skill definitions."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    nodes: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    edges: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    is_meta: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ToolkitORM(Base):
    """ORM for toolkit modules."""

    __tablename__ = "toolkits"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    module_path: Mapped[str] = mapped_column(String, nullable=False)
    public_api: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    dependencies: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ObjectiveORM(Base):
    """ORM for user objectives (for reuse matching)."""

    __tablename__ = "objectives"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[dict] = mapped_column(JSON, default=list)  # type: ignore[assignment]
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


class DependencyRegistryORM(Base):
    """ORM for tracking user-approved pip packages."""

    __tablename__ = "dependency_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    package_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_install: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserPreferenceORM(Base):
    """ORM for persistent user preferences and feedback."""

    __tablename__ = "user_preferences"

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
