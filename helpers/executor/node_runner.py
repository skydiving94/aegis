"""Node runner for retry strategies and backoff during execution."""

import asyncio
import logging
import random
from typing import Any

from models.enums import ExecutionStatus
from models.task import AbstractTask, ExecutionContext, TaskResult

logger = logging.getLogger(__name__)


class NodeRunner:
    """Executes a single task node with retries and exponential backoff."""

    @staticmethod
    async def execute(
        task: AbstractTask,
        context: ExecutionContext,
        payload: dict[str, Any],
        max_retries: int = 5,
    ) -> TaskResult:
        """Execute a task with retries."""
        last_result: TaskResult | None = None

        for attempt in range(1, max_retries + 1):
            try:
                result = task.execute(context, payload)
                if result.status == ExecutionStatus.SUCCESS:
                    logger.info("Task '%s' succeeded on attempt %d", task.name, attempt)
                    return result
                last_result = result
                logger.warning(
                    "Task '%s' failed (attempt %d/%d):\\n%s",
                    task.name,
                    attempt,
                    max_retries,
                    result.logs,
                )
            except Exception as e:
                logger.error(
                    "Task '%s' raised exception (attempt %d/%d): %s",
                    task.name,
                    attempt,
                    max_retries,
                    str(e),
                )
                last_result = TaskResult(
                    outputs={},
                    logs=str(e),
                    status=ExecutionStatus.FAILED,
                )

            # Backoff before returning if not the last attempt
            if attempt < max_retries:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info("Backing off for %.2fs before retry...", sleep_time)
                await asyncio.sleep(sleep_time)

        # All retries exhausted
        logger.error("Task '%s' failed after %d retries", task.name, max_retries)
        if last_result and last_result.status != ExecutionStatus.SUCCESS:
            print(f"[DEBUG EXECUTION EXHAUSTED] {task.name} failed. Logs:\\n{last_result.logs}")
            
        return last_result or TaskResult(
            outputs={},
            logs=f"Task '{task.name}' failed to execute any attempts",
            status=ExecutionStatus.FAILED,
        )
