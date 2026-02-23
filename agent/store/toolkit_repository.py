"""Toolkit repository for persisting and querying toolkit modules."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.models.toolkit import ToolkitModule
from agent.store.base_repository import AbstractRepository
from agent.store.orm_models import ToolkitORM


class ToolkitRepository(AbstractRepository[ToolkitModule]):
    """Repository for ToolkitModule persistence via SQLAlchemy."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, id: str) -> ToolkitModule | None:
        """Load a toolkit by ID."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(ToolkitORM, id)
            if row is None:
                return None
            return self._orm_to_model(row)

    async def save(self, entity: ToolkitModule) -> ToolkitModule:
        """Persist a toolkit."""
        async with self._session_factory() as session:
            session: AsyncSession
            orm = self._model_to_orm(entity)
            merged = await session.merge(orm)
            await session.commit()
            return self._orm_to_model(merged)

    async def delete(self, id: str) -> bool:
        """Delete a toolkit by ID."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(ToolkitORM, id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_all(self) -> list[ToolkitModule]:
        """List all toolkits."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(select(ToolkitORM))
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    async def get_by_name(self, name: str) -> ToolkitModule | None:
        """Find a toolkit by name."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(
                select(ToolkitORM).where(ToolkitORM.name == name)
            )
            row = result.scalars().first()
            if row is None:
                return None
            return self._orm_to_model(row)

    async def list_requiring_approval(self) -> list[ToolkitModule]:
        """List toolkits that require user approval."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(
                select(ToolkitORM).where(ToolkitORM.requires_approval.is_(True))
            )
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    @staticmethod
    def _orm_to_model(row: ToolkitORM) -> ToolkitModule:
        """Convert ORM row to domain model."""
        return ToolkitModule(
            id=row.id,
            name=row.name,
            description=row.description,
            module_path=row.module_path,
            public_api=row.public_api or [],
            dependencies=row.dependencies or [],
            requires_approval=row.requires_approval,
            created_at=row.created_at,
        )

    @staticmethod
    def _model_to_orm(entity: ToolkitModule) -> ToolkitORM:
        """Convert domain model to ORM row."""
        return ToolkitORM(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            module_path=entity.module_path,
            public_api=entity.public_api,
            dependencies=entity.dependencies,
            requires_approval=entity.requires_approval,
            created_at=entity.created_at,
        )
