"""DAG executor with data policy enforcement and HITL approval checks."""

from __future__ import annotations

import json
import logging
import tempfile
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

from agent.executor.base_executor import AbstractDAGExecutor
from agent.models.edge import Edge
from agent.models.enums import DataPolicy, ExecutionStatus, PreconditionType, RiskLevel
from agent.models.skill import Skill, SkillNode
from agent.models.task import AbstractTask, ExecutionContext, TaskResult

logger = logging.getLogger(__name__)


class ApprovalDeniedError(Exception):
    """Raised when user denies task execution approval."""


class DAGExecutor(AbstractDAGExecutor):
    """Sequential DAG executor with data policy and approval gate enforcement.

    Limitation: nodes execute sequentially in topological order.
    v2: asyncio.gather() for parallel independent branches.
    """

    def __init__(
        self,
        task_repo: Any,  # TaskRepository
        toolkit_registry: Any,  # ToolkitRegistry
    ) -> None:
        self._task_repo = task_repo
        self._toolkit_registry = toolkit_registry

    async def execute_skill(
        self,
        skill: Skill,
        context: ExecutionContext,
        initial_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute all nodes in topological order, propagating outputs."""
        # Build networkx graph for topological sort
        graph = nx.DiGraph()
        for node in skill.nodes:
            graph.add_node(node.node_id)
        for edge in skill.edges:
            graph.add_edge(edge.source_node_id, edge.target_node_id)

        order = list(nx.topological_sort(graph))
        node_map: dict[str, SkillNode] = {n.node_id: n for n in skill.nodes}
        completed_outputs: dict[str, dict[str, Any]] = {}

        # Root nodes get initial_inputs
        for node_id in order:
            node = node_map[node_id]
            task = await self._resolve_node(node)
            payload = self._build_payload(node, completed_outputs, skill.edges, task, context)

            # Merge initial_inputs for root nodes (no incoming edges)
            incoming = [e for e in skill.edges if e.target_node_id == node_id]
            if not incoming:
                payload.update(initial_inputs)

            # Approval check
            self._check_approval(task, context)

            # Execute with retries
            result = await self._execute_node(task, context, payload)
            completed_outputs[node_id] = result.outputs

            # Post-execution approval for CRITICAL tasks
            if task.risk_level == RiskLevel.CRITICAL:
                approved = context.approval_gate.approve_task_output(task.name, result)
                if not approved:
                    raise ApprovalDeniedError(
                        f"Output of CRITICAL task '{task.name}' was rejected by user"
                    )

        # Collect outputs from terminal nodes (no outgoing edges)
        terminal_nodes = [n for n in order if graph.out_degree(n) == 0]
        final_outputs: dict[str, Any] = {}
        for node_id in terminal_nodes:
            final_outputs.update(completed_outputs.get(node_id, {}))

        return final_outputs

    async def _resolve_node(self, node: SkillNode) -> AbstractTask:
        """Load a task definition from the repository."""
        task = await self._task_repo.get_by_id(node.task_definition_id)
        if task is None:
            raise ValueError(f"Task '{node.task_definition_id}' not found in repository")
        return task

    def _build_payload(
        self,
        node: SkillNode,
        completed_outputs: dict[str, dict[str, Any]],
        edges: list[Edge],
        task: AbstractTask,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Map upstream outputs to current node inputs via edge output_mapping.

        Applies DataPolicy on each edge before injecting values.
        """
        payload: dict[str, Any] = {}
        incoming_edges = [e for e in edges if e.target_node_id == node.node_id]

        for edge in incoming_edges:
            source_outputs = completed_outputs.get(edge.source_node_id, {})
            for source_key, target_key in edge.output_mapping.items():
                raw_value = source_outputs.get(source_key)
                if raw_value is not None:
                    payload[target_key] = self._apply_data_policy(
                        raw_value, edge, context
                    )

        return payload

    def _apply_data_policy(
        self, value: Any, edge: Edge, context: ExecutionContext
    ) -> Any:
        """Enforce DataPolicy on a value flowing through an edge.

        PASS_THROUGH: return as-is.
        SUMMARIZE: LLM summarizes to max_chars.
        REFERENCE: store to temp file, return metadata.
        TRUNCATE: hard-truncate to max_chars.
        """
        policy = edge.data_policy
        max_chars = edge.max_chars or 4000

        if policy == DataPolicy.PASS_THROUGH:
            return value

        serialized = json.dumps(value) if not isinstance(value, str) else value

        if policy == DataPolicy.TRUNCATE:
            if len(serialized) > max_chars:
                return serialized[:max_chars] + "\n[...TRUNCATED]"
            return value

        if policy == DataPolicy.SUMMARIZE:
            if len(serialized) <= max_chars:
                return value  # small enough, no summarization needed
            summary_prompt = (
                f"Summarize the following data concisely in under {max_chars} characters. "
                f"Preserve all key facts, numbers, and field names:\n\n{serialized}"
            )
            response = context.llm_client.send(
                prompt=summary_prompt,
                usage_type="summarize",
                max_output_tokens=max_chars // 3,  # rough char-to-token ratio
            )
            return response.content

        if policy == DataPolicy.REFERENCE:
            # Store to temp file and return a reference
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="agent_ref_", delete=False
            ) as f:
                json.dump(value, f)
                ref_path = f.name
            summary = f"Data reference ({len(serialized)} chars)"
            return {"__ref": ref_path, "summary": summary}

        return value  # fallback

    def _check_approval(self, task: AbstractTask, context: ExecutionContext) -> None:
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

    async def _execute_node(
        self,
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
                    logger.info(
                        "Task '%s' succeeded on attempt %d", task.name, attempt
                    )
                    return result
                last_result = result
                logger.warning(
                    "Task '%s' failed (attempt %d/%d):\n%s",
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
                import asyncio
                import random
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info("Backing off for %.2fs before retry...", sleep_time)
                await asyncio.sleep(sleep_time)

        # All retries exhausted
        logger.error("Task '%s' failed after %d retries", task.name, max_retries)
        if last_result and last_result.status != ExecutionStatus.SUCCESS:
            print(f"[DEBUG EXECUTION EXHAUSTED] {task.name} failed. Logs:\n{last_result.logs}")
            
        return last_result or TaskResult(
            outputs={},
            logs=f"Task '{task.name}' failed to execute any attempts",
            status=ExecutionStatus.FAILED,
        )
