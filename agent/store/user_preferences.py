"""Repository for persistent user preferences."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.store.orm_models import UserPreferenceORM

logger = logging.getLogger(__name__)


class UserPreferenceRepository:
    """Key-value store for user preferences, persisted in PostgreSQL."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def get(self, key: str) -> str | None:
        """Get a preference value by key."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserPreferenceORM).where(UserPreferenceORM.key == key)
            )
            row = result.scalar_one_or_none()
            return row.value if row else None

    async def set(self, key: str, value: str, domain: str = "", source: str = "user") -> None:
        """Set a preference. Creates or updates."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserPreferenceORM).where(UserPreferenceORM.key == key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.value = value
                existing.domain = domain
                existing.source = source
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(UserPreferenceORM(
                    key=key,
                    value=value,
                    domain=domain,
                    source=source,
                ))
            await session.commit()
            logger.info("Preference saved: %s = %s", key, value[:50])

    async def get_all(self) -> dict[str, str]:
        """Get all preferences as a dict."""
        async with self._session_factory() as session:
            result = await session.execute(select(UserPreferenceORM))
            rows = result.scalars().all()
            return {row.key: row.value for row in rows}

    async def get_by_domain(self, domain: str) -> dict[str, str]:
        """Get preferences for a specific domain."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserPreferenceORM).where(UserPreferenceORM.domain == domain)
            )
            rows = result.scalars().all()
            return {row.key: row.value for row in rows}
