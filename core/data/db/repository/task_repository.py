"""Task repository for persisting and querying task definitions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import IOType, RiskLevel, TaskType
from models.io_types import Precondition, TypedIOField
from models.task import AbstractTask, LLMTask, PythonTask
from core.data.db.repository.base_repository import AbstractRepository
from core.data.db.entities.task import Task as TaskORM
from core.data.db.repository.task_mapper import TaskMapper


class TaskRepository(AbstractRepository[AbstractTask]):
    """Repository for AbstractTask persistence via SQLAlchemy."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, id: str) -> AbstractTask | None:
        """Load a task by ID, constructing the correct subclass."""
        async with self._session_factory() as session:
            row = await session.get(TaskORM, id)
            if row is None:
                return None
            return TaskMapper.orm_to_model(row)

    async def save(self, entity: AbstractTask) -> AbstractTask:
        """Persist a task definition."""
        async with self._session_factory() as session:
            orm = TaskMapper.model_to_orm(entity)
            merged = await session.merge(orm)
            await session.commit()
            return TaskMapper.orm_to_model(merged)

    async def delete(self, id: str) -> bool:
        """Delete a task by ID."""
        async with self._session_factory() as session:
            row = await session.get(TaskORM, id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_all(self) -> list[AbstractTask]:
        """List all tasks."""
        async with self._session_factory() as session:
            result = await session.execute(select(TaskORM))
            rows = result.scalars().all()
            return [TaskMapper.orm_to_model(r) for r in rows]

    async def search_by_tags(
        self, tags: list[str], limit: int = 10
    ) -> list[AbstractTask]:
        """Search tasks by tag overlap."""
        all_tasks = await self.list_all()
        scored: list[tuple[int, AbstractTask]] = []
        tag_set = set(tags)
        for task in all_tasks:
            overlap = len(tag_set & set(task.tags))
            if overlap > 0:
                scored.append((overlap, task))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]

    async def search_by_preconditions(
        self, preconditions: list[Precondition]
    ) -> list[AbstractTask]:
        """Search tasks by exact precondition match."""
        all_tasks = await self.list_all()
        query_set = {(p.type.value, p.value) for p in preconditions}
        return [
            t
            for t in all_tasks
            if query_set <= {(p.type.value, p.value) for p in t.preconditions}
        ]

    async def get_versions(self, name: str) -> list[AbstractTask]:
        """Get all versions of a named task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(TaskORM.name == name)
            )
            rows = result.scalars().all()
            return [TaskMapper.orm_to_model(r) for r in rows]


