"""DAG executor with data policy enforcement and HITL approval checks."""

from __future__ import annotations

import json
import logging
import tempfile
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

from helpers.executor.base_executor import AbstractDAGExecutor
from models.edge import Edge
from models.enums import DataPolicy, ExecutionStatus, PreconditionType, RiskLevel
from models.skill import Skill, SkillNode
from models.task import AbstractTask, ExecutionContext, TaskResult
from helpers.executor.approval import ApprovalManager, ApprovalDeniedError
from helpers.executor.policy import DataPolicyStrategy
from helpers.executor.node_runner import NodeRunner

logger = logging.getLogger(__name__)


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
            ApprovalManager.check(task, context)

            # Execute with retries
            result = await NodeRunner.execute(task, context, payload)
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
                    payload[target_key] = DataPolicyStrategy.apply(
                        raw_value, edge, context
                    )

        return payload


