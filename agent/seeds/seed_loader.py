"""Seed loader for meta-skill and task JSON definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.models.edge import Edge
from agent.models.enums import RiskLevel, TaskType
from agent.models.io_types import Precondition, TypedIOField
from agent.models.skill import Skill, SkillNode
from agent.models.task import AbstractTask, LLMTask, PythonTask
from agent.schemas.validator import SchemaValidator


_SEEDS_DIR = Path(__file__).parent
_SKILLS_DIR = _SEEDS_DIR / "skills"
_TASKS_DIR = _SEEDS_DIR / "tasks"


class SeedLoader:
    """Loads and validates seed meta-skill and task JSON files.

    Loads both standalone task definitions from seeds/tasks/
    and skill definitions from seeds/skills/.
    """

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        tasks_dir: str | Path | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir) if skills_dir else _SKILLS_DIR
        self._tasks_dir = Path(tasks_dir) if tasks_dir else _TASKS_DIR
        self._validator = SchemaValidator()

    # ── Skill loading ──────────────────────────────────────

    def load_all_skills(self) -> list[Skill]:
        """Load and validate all seed skill JSON files."""
        skills: list[Skill] = []
        if not self._skills_dir.exists():
            return skills
        for path in sorted(self._skills_dir.glob("*.json")):
            skills.append(self._parse_skill(str(path)))
        return skills

    def load_all(self) -> list[Skill]:
        """Alias for backward compat."""
        return self.load_all_skills()

    def load_one(self, name: str) -> Skill:
        """Load a single seed skill by name (without .json extension)."""
        path = self._skills_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Seed skill '{name}' not found at {path}")
        return self._parse_skill(str(path))

    def _parse_skill(self, path: str) -> Skill:
        """Read JSON, validate against skill_schema.json, construct Skill."""
        with open(path) as f:
            data: dict[str, object] = json.load(f)

        errors = self._validator.validate_skill(data)
        if errors:
            raise ValueError(f"Invalid seed skill at {path}: {errors}")

        nodes = [SkillNode(**n) for n in data.get("nodes", [])]  # type: ignore[arg-type]
        edges = [Edge(**e) for e in data.get("edges", [])]  # type: ignore[arg-type]

        return Skill(
            id=data.get("id", Path(path).stem),  # type: ignore[arg-type]
            name=data["name"],  # type: ignore[arg-type]
            description=data["description"],  # type: ignore[arg-type]
            tags=data.get("tags", []),  # type: ignore[arg-type]
            nodes=nodes,
            edges=edges,
            is_meta=data.get("is_meta", True),  # type: ignore[arg-type]
            version=data.get("version", 1),  # type: ignore[arg-type]
        )

    # ── Task loading ───────────────────────────────────────

    def load_all_tasks(self) -> list[AbstractTask]:
        """Load and validate all seed task JSON files."""
        tasks: list[AbstractTask] = []
        if not self._tasks_dir.exists():
            return tasks
        for path in sorted(self._tasks_dir.glob("*.json")):
            tasks.append(self._parse_task(str(path)))
        return tasks

    def load_task(self, name: str) -> AbstractTask:
        """Load a single seed task by name (without .json extension)."""
        path = self._tasks_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Seed task '{name}' not found at {path}")
        return self._parse_task(str(path))

    def _parse_task(self, path: str) -> AbstractTask:
        """Read JSON, validate against task_schema.json, construct task."""
        with open(path) as f:
            data: dict[str, Any] = json.load(f)

        errors = self._validator.validate_task(data)
        if errors:
            raise ValueError(f"Invalid seed task at {path}: {errors}")

        common: dict[str, Any] = {
            "id": data.get("id", Path(path).stem),
            "name": data["name"],
            "description": data.get("description", ""),
            "inputs": [TypedIOField(**f) for f in data.get("inputs", [])],
            "outputs": [TypedIOField(**f) for f in data.get("outputs", [])],
            "preconditions": [
                Precondition(**p) for p in data.get("preconditions", [])
            ],
            "toolkit_refs": data.get("toolkit_refs", []),
            "risk_level": RiskLevel(data["risk_level"]) if data.get("risk_level") else RiskLevel.LOW,
            "max_retries": data.get("max_retries", 10),
            "version": data.get("version", 1),
            "tags": data.get("tags", []),
        }

        if data.get("task_type") == TaskType.PYTHON.value:
            return PythonTask(
                **common,
                code=data.get("code", ""),
                test_code=data.get("test_code", ""),
            )
        else:
            return LLMTask(
                **common,
                prompt_template=data.get("prompt_template", ""),
                system_instruction=data.get("system_instruction", ""),
                context_budget=data.get("context_budget", 32000),
            )
