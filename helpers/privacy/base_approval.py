"""Abstract base for approval gates (HITL)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.enums import RiskLevel
    from models.task import TaskResult


class AbstractApprovalGate(ABC):
    """ABC for human-in-the-loop approval gates."""

    @abstractmethod
    def approve_file_read(self, path: str) -> bool:
        """Request approval to read a file."""
        ...

    @abstractmethod
    def approve_file_write(self, path: str) -> bool:
        """Request approval to write a file."""
        ...

    @abstractmethod
    def approve_pip_install(self, package: str) -> bool:
        """Request approval to install a pip package."""
        ...

    @abstractmethod
    def approve_task_execution(
        self, task_name: str, description: str, risk_level: RiskLevel
    ) -> bool:
        """Request approval before executing a HIGH/CRITICAL risk task.

        Args:
            task_name: Name of the task to execute.
            description: Human-readable description of what the task does.
            risk_level: The assessed risk level.

        Returns:
            True if the user approves execution.
        """
        ...

    @abstractmethod
    def approve_task_output(self, task_name: str, result: TaskResult) -> bool:
        """Request approval of a CRITICAL task's output before propagation.

        Args:
            task_name: Name of the completed task.
            result: The TaskResult to review.

        Returns:
            True if the user approves propagating the output.
        """
        ...

    @abstractmethod
    def seek_clarification(
        self, question: str, context: dict | None = None
    ) -> str:
        """Ask the user a clarifying question and return their answer.

        Args:
            question: The question to ask the user.
            context: Optional context about why this is being asked.

        Returns:
            The user's text answer.
        """
        ...

    @abstractmethod
    def get_approved_paths(self) -> list[str]:
        """Return a list of file paths approved this session."""
        ...
