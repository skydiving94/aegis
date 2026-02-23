"""Task repository for persisting and querying task definitions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.models.enums import IOType, RiskLevel, TaskType
from agent.models.io_types import Precondition, TypedIOField
from agent.models.task import AbstractTask, LLMTask, PythonTask
from agent.store.base_repository import AbstractRepository
from agent.store.orm_models import TaskORM


class TaskRepository(AbstractRepository[AbstractTask]):
    """Repository for AbstractTask persistence via SQLAlchemy."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, id: str) -> AbstractTask | None:
        """Load a task by ID, constructing the correct subclass."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(TaskORM, id)
            if row is None:
                return None
            return self._orm_to_model(row)

    async def save(self, entity: AbstractTask) -> AbstractTask:
        """Persist a task definition."""
        async with self._session_factory() as session:
            session: AsyncSession
            orm = self._model_to_orm(entity)
            merged = await session.merge(orm)
            await session.commit()
            return self._orm_to_model(merged)

    async def delete(self, id: str) -> bool:
        """Delete a task by ID."""
        async with self._session_factory() as session:
            session: AsyncSession
            row = await session.get(TaskORM, id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_all(self) -> list[AbstractTask]:
        """List all tasks."""
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(select(TaskORM))
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

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
            session: AsyncSession
            result = await session.execute(
                select(TaskORM).where(TaskORM.name == name)
            )
            rows = result.scalars().all()
            return [self._orm_to_model(r) for r in rows]

    # Map common LLM-generated io_type values to valid IOType enum values
    _IO_TYPE_ALIASES: dict[str, str] = {
        "str": "string",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "dict",
        "array": "list",
        "any": "string",
        "text": "string",
        "json": "dict",
        "map": "dict",
    }

    @classmethod
    def _sanitize_io_type(cls, raw: str) -> str:
        """Normalize an io_type string to a valid IOType enum value.

        Handles LLM-generated variants like 'list[string]', 'object', 'any'.
        """
        if not isinstance(raw, str):
            return "string"
        clean = raw.strip().lower()
        # Handle parameterized types like list[string], dict[str, Any]
        if "[" in clean:
            clean = clean.split("[")[0].strip()
        # Check aliases
        if clean in cls._IO_TYPE_ALIASES:
            return cls._IO_TYPE_ALIASES[clean]
        # Check if it's already a valid enum value
        try:
            IOType(clean)
            return clean
        except ValueError:
            return "string"  # safe fallback

    @classmethod
    def _safe_typed_io_field(cls, f: dict) -> TypedIOField | None:
        """Create a TypedIOField, sanitizing io_type to prevent crashes."""
        if not isinstance(f, dict) or "name" not in f:
            return None
        f = dict(f)  # copy to avoid mutating original
        f["io_type"] = cls._sanitize_io_type(f.get("io_type", "string"))
        try:
            return TypedIOField(**f)
        except Exception:
            return None

    @staticmethod
    def _orm_to_model(row: TaskORM) -> AbstractTask:
        """Convert ORM row to domain model (PythonTask or LLMTask)."""
        import json
        
        def _parse(val: Any) -> list[Any]:
            if not val:
                return []
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return []
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], str):
                parsed = []
                for item in val:
                    if isinstance(item, str) and item.strip().startswith(("{", "[")):
                        try:
                            parsed.append(json.loads(item))
                        except json.JSONDecodeError:
                            parsed.append(item)
                    else:
                        parsed.append(item)
                return parsed
            return val

        inputs_list = _parse(row.inputs)
        outputs_list = _parse(row.outputs)
        prec_list = _parse(row.preconditions)

        common = {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "inputs": [f for f in (TaskRepository._safe_typed_io_field(x) for x in inputs_list if isinstance(x, dict)) if f is not None],
            "outputs": [f for f in (TaskRepository._safe_typed_io_field(x) for x in outputs_list if isinstance(x, dict)) if f is not None],
            "preconditions": [Precondition(**p) for p in prec_list if isinstance(p, dict)],
            "toolkit_refs": _parse(row.toolkit_refs) if row.toolkit_refs else [],
            "risk_level": RiskLevel(row.risk_level) if row.risk_level else RiskLevel.LOW,
            "max_retries": row.max_retries,
            "version": row.version,
            "tags": _parse(row.tags) if row.tags else [],
            "created_at": row.created_at,
        }
        if row.task_type == TaskType.PYTHON.value:
            return PythonTask(
                **common,
                code=row.code or "",
                test_code=row.test_code or "",
            )
        else:
            return LLMTask(
                **common,
                prompt_template=row.prompt_template or "",
                system_instruction=row.system_instruction or "",
                context_budget=row.context_budget or 32000,
            )

    @staticmethod
    def _model_to_orm(entity: AbstractTask) -> TaskORM:
        """Convert domain model to ORM row."""
        orm = TaskORM(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            task_type=entity.task_type.value,
            inputs=[f.model_dump() for f in entity.inputs],
            outputs=[f.model_dump() for f in entity.outputs],
            preconditions=[p.model_dump() for p in entity.preconditions],
            toolkit_refs=entity.toolkit_refs,
            risk_level=entity.risk_level.value,
            max_retries=entity.max_retries,
            version=entity.version,
            tags=entity.tags,
            created_at=entity.created_at,
        )
        if isinstance(entity, PythonTask):
            orm.code = entity.code
            orm.test_code = entity.test_code
        elif isinstance(entity, LLMTask):
            orm.prompt_template = entity.prompt_template
            orm.system_instruction = entity.system_instruction
            orm.context_budget = entity.context_budget
        return orm
