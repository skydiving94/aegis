"""Approval manager for HITL checks."""

import logging

from models.enums import PreconditionType, RiskLevel
from models.task import AbstractTask, ExecutionContext

logger = logging.getLogger(__name__)


class ApprovalDeniedError(Exception):
    """Raised when user denies task execution approval."""
    pass


class ApprovalManager:
    """Manages hitl approval checks for tasks."""

    @staticmethod
    def check(task: AbstractTask, context: ExecutionContext) -> None:
        """Check risk_level and REQUIRES_APPROVAL preconditions.

        Raises ApprovalDeniedError if user rejects.
        """
        # Check risk level
        if task.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            approved = context.approval_gate.approve_task_execution(
                task.name, task.description, task.risk_level
            )
            if not approved:
                raise ApprovalDeniedError(
                    f"Execution of {task.risk_level.value} task '{task.name}' denied by user"
                )
        elif task.risk_level == RiskLevel.MEDIUM:
            logger.warning(
                "Executing MEDIUM-risk task '%s': %s", task.name, task.description
            )

        # Check REQUIRES_APPROVAL preconditions
        for precondition in task.preconditions:
            if precondition.type == PreconditionType.REQUIRES_APPROVAL:
                approved = context.approval_gate.approve_task_execution(
                    task.name,
                    f"{task.description} [scope: {precondition.value}]",
                    RiskLevel.HIGH,  # treat REQUIRES_APPROVAL as HIGH
                )
                if not approved:
                    raise ApprovalDeniedError(
                        f"Approval denied for task '{task.name}' "
                        f"(scope: {precondition.value})"
                    )
