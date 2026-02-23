"""Tests for DAG executor including data policy and approval checks."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent.executor.dag_executor import ApprovalDeniedError, DAGExecutor
from agent.models.edge import Edge
from agent.models.enums import DataPolicy, ExecutionStatus, PreconditionType, RiskLevel
from agent.models.io_types import Precondition
from agent.models.skill import Skill, SkillNode
from agent.models.task import (
    ExecutionContext,
    LLMTask,
    PythonTask,
    TaskResult,
)
from tests.conftest import MockApprovalGate, MockLLMClient, MockSandboxRunner, MockScrubber


def _make_context(**kwargs: Any) -> ExecutionContext:
    return ExecutionContext(
        sandbox=kwargs.get("sandbox", MockSandboxRunner()),
        llm_client=kwargs.get("llm_client", MockLLMClient()),
        approval_gate=kwargs.get("approval_gate", MockApprovalGate()),
        scrubber=kwargs.get("scrubber", MockScrubber()),
    )


def _make_task_repo(tasks: dict[str, Any]) -> MagicMock:
    repo = MagicMock()

    async def get_by_id(id: str) -> Any:
        return tasks.get(id)

    repo.get_by_id = get_by_id
    return repo


class TestLinearDAGExecution:
    @pytest.mark.asyncio
    async def test_single_node_execution(self) -> None:
        task = PythonTask(
            id="t1",
            name="add_one",
            description="Adds one",
            code="",
            test_code="",
            tags=[],
        )
        repo = _make_task_repo({"t1": task})
        executor = DAGExecutor(task_repo=repo, toolkit_registry=MagicMock())

        skill = Skill(
            id="s1",
            name="simple",
            description="Simple skill",
            nodes=[SkillNode(node_id="n1", task_definition_id="t1")],
            edges=[],
        )

        sandbox = MockSandboxRunner(outputs={"result": 42})
        context = _make_context(sandbox=sandbox)

        result = await executor.execute_skill(skill, context, {"x": 1})
        assert result == {"result": 42}

    @pytest.mark.asyncio
    async def test_two_node_linear_dag(self) -> None:
        t1 = PythonTask(
            id="t1", name="step1", description="", code="", test_code="", tags=[]
        )
        t2 = PythonTask(
            id="t2", name="step2", description="", code="", test_code="", tags=[]
        )
        repo = _make_task_repo({"t1": t1, "t2": t2})
        sandbox = MockSandboxRunner(outputs={"final": "done"})
        executor = DAGExecutor(task_repo=repo, toolkit_registry=MagicMock())

        skill = Skill(
            id="s1",
            name="linear",
            description="Two-step",
            nodes=[
                SkillNode(node_id="n1", task_definition_id="t1"),
                SkillNode(node_id="n2", task_definition_id="t2"),
            ],
            edges=[
                Edge(
                    source_node_id="n1",
                    target_node_id="n2",
                    output_mapping={"result": "input"},
                )
            ],
        )

        context = _make_context(sandbox=sandbox)
        result = await executor.execute_skill(skill, context, {})
        assert "final" in result


class TestDataPolicyEnforcement:
    @pytest.mark.asyncio
    async def test_truncate_policy(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        edge = Edge(
            source_node_id="a",
            target_node_id="b",
            output_mapping={},
            data_policy=DataPolicy.TRUNCATE,
            max_chars=10,
        )
        context = _make_context()
        result = executor._apply_data_policy("a" * 100, edge, context)
        assert len(result) <= 25  # 10 + truncation marker
        assert "TRUNCATED" in result

    @pytest.mark.asyncio
    async def test_pass_through_policy(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        edge = Edge(
            source_node_id="a",
            target_node_id="b",
            output_mapping={},
            data_policy=DataPolicy.PASS_THROUGH,
        )
        context = _make_context()
        value = {"key": "value"}
        result = executor._apply_data_policy(value, edge, context)
        assert result == value

    @pytest.mark.asyncio
    async def test_summarize_small_data_passes_through(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        edge = Edge(
            source_node_id="a",
            target_node_id="b",
            output_mapping={},
            data_policy=DataPolicy.SUMMARIZE,
            max_chars=10000,
        )
        context = _make_context()
        value = "small text"
        result = executor._apply_data_policy(value, edge, context)
        assert result == "small text"


class TestApprovalChecks:
    @pytest.mark.asyncio
    async def test_low_risk_no_approval_needed(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        task = PythonTask(
            id="t1",
            name="safe",
            description="Safe task",
            risk_level=RiskLevel.LOW,
            code="",
            test_code="",
            tags=[],
        )
        context = _make_context()
        # Should not raise
        executor._check_approval(task, context)

    @pytest.mark.asyncio
    async def test_high_risk_denied(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        task = PythonTask(
            id="t1",
            name="dangerous",
            description="Dangerous task",
            risk_level=RiskLevel.HIGH,
            code="",
            test_code="",
            tags=[],
        )

        class DenyGate(MockApprovalGate):
            def approve_task_execution(
                self, task_name: str, description: str, risk_level: RiskLevel
            ) -> bool:
                return False

        context = _make_context(approval_gate=DenyGate())
        with pytest.raises(ApprovalDeniedError):
            executor._check_approval(task, context)

    @pytest.mark.asyncio
    async def test_requires_approval_precondition(self) -> None:
        executor = DAGExecutor(task_repo=MagicMock(), toolkit_registry=MagicMock())
        task = PythonTask(
            id="t1",
            name="file_writer",
            description="Writes files",
            risk_level=RiskLevel.LOW,
            preconditions=[
                Precondition(type=PreconditionType.REQUIRES_APPROVAL, value="file_write")
            ],
            code="",
            test_code="",
            tags=[],
        )

        class DenyGate(MockApprovalGate):
            def approve_task_execution(
                self, task_name: str, description: str, risk_level: RiskLevel
            ) -> bool:
                return False

        context = _make_context(approval_gate=DenyGate())
        with pytest.raises(ApprovalDeniedError):
            executor._check_approval(task, context)
