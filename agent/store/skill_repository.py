"""Skill repository for persisting and querying skills."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.models.edge import Edge
from agent.models.skill import Skill, SkillNode
from agent.store.base_repository import AbstractRepository
from agent.store.orm_models import SkillORM


class SkillRepository(AbstractRepository[Skill]):
    """Repository for Skill persistence via SQLAlchemy."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, id: str) -> Skill | None:
        """Load a skill by ID."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(SkillORM, id)
            if row is None:
                return None
            return self._orm_to_model(row)

    async def save(self, entity: Skill) -> Skill:
        """Persist a skill."""
        async with self._session_factory() as session:
            session: AsyncSession
            orm = self._model_to_orm(entity)
            merged = await session.merge(orm)
            await session.commit()
            return self._orm_to_model(merged)

    async def delete(self, id: str) -> bool:
        """Delete a skill by ID."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(SkillORM, id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_all(self) -> list[Skill]:
        """List all skills."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(select(SkillORM))
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    async def search_by_tags(
        self, tags: list[str], limit: int = 10
    ) -> list[Skill]:
        """Search skills by tag overlap."""
        all_skills = await self.list_all()
        tag_set = set(tags)
        scored = [
            (len(tag_set & set(s.tags)), s)
            for s in all_skills
            if len(tag_set & set(s.tags)) > 0
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    async def get_meta_skills(self) -> list[Skill]:
        """Return only meta-skills."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(
                select(SkillORM).where(SkillORM.is_meta.is_(True))
            )
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    @staticmethod
    def _orm_to_model(row: SkillORM) -> Skill:
        """Convert ORM row to domain model."""
        return Skill(
            id=row.id,
            name=row.name,
            description=row.description,
            tags=row.tags or [],
            nodes=[SkillNode(**n) for n in (row.nodes or [])],
            edges=[Edge(**e) for e in (row.edges or [])],
            is_meta=row.is_meta,
            version=row.version,
            created_at=row.created_at,
        )

    @staticmethod
    def _model_to_orm(entity: Skill) -> SkillORM:
        """Convert domain model to ORM row."""
        return SkillORM(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            tags=entity.tags,
            nodes=[n.model_dump() for n in entity.nodes],
            edges=[e.model_dump() for e in entity.edges],
            is_meta=entity.is_meta,
            version=entity.version,
            created_at=entity.created_at,
        )
