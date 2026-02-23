"""Abstract base for DAG executors."""

from abc import ABC, abstractmethod
from typing import Any

from agent.models.skill import Skill
from agent.models.task import ExecutionContext


class AbstractDAGExecutor(ABC):
    """ABC for skill execution engines."""

    @abstractmethod
    async def execute_skill(
        self,
        skill: Skill,
        context: ExecutionContext,
        initial_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a skill's DAG of tasks.

        Args:
            skill: The skill containing nodes and edges.
            context: Runtime dependencies (sandbox, LLM, approval gate, etc.).
            initial_inputs: Initial payload for root nodes.

        Returns:
            Combined outputs from all terminal nodes.
        """
        ...
