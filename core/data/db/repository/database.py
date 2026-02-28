"""SQLAlchemy async engine and session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(url: str) -> AsyncEngine:
    """Create and cache the SQLAlchemy async engine."""
    global _engine, _session_factory  # noqa: PLW0603
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a DB session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call create_engine() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables from ORM metadata."""
    from core.data.db.entities.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
