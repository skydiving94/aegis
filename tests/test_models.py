"""Tests for domain models."""

from datetime import datetime, timezone

from models.enums import (
    DataPolicy,
    ExecutionStatus,
    IOType,
    PreconditionType,
    RiskLevel,
    TaskType,
)
from models.io_types import Precondition, TypedIOField
from models.edge import Edge
from models.skill import Skill, SkillNode
from models.task import (
    ExecutionContext,
    LLMTask,
    PythonTask,
    TaskResult,
)
from models.toolkit import ToolkitModule


class TestEnums:
    def test_task_type_values(self) -> None:
        assert TaskType.PYTHON.value == "python"
        assert TaskType.LLM.value == "llm"

    def test_risk_level_ordering(self) -> None:
        levels = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert len(levels) == 4

    def test_data_policy_values(self) -> None:
        assert DataPolicy.PASS_THROUGH.value == "pass_through"
        assert DataPolicy.SUMMARIZE.value == "summarize"

    def test_precondition_requires_approval(self) -> None:
        assert PreconditionType.REQUIRES_APPROVAL.value == "requires_approval"


class TestTypedIOField:
    def test_basic_field(self) -> None:
        field = TypedIOField(name="x", io_type=IOType.STRING, description="test")
        assert field.name == "x"
        assert field.io_type == IOType.STRING
        assert field.max_chars is None

    def test_field_with_max_chars(self) -> None:
        field = TypedIOField(name="y", io_type=IOType.DICT, max_chars=1000)
        assert field.max_chars == 1000


class TestPrecondition:
    def test_precondition(self) -> None:
        p = Precondition(
            type=PreconditionType.INPUT_FORMAT,
            value="csv",
            description="CSV input",
        )
        assert p.type == PreconditionType.INPUT_FORMAT
        assert p.value == "csv"


class TestEdge:
    def test_basic_edge(self) -> None:
        e = Edge(
            source_node_id="a",
            target_node_id="b",
            output_mapping={"out": "in"},
        )
        assert e.data_policy == DataPolicy.PASS_THROUGH
        assert e.max_chars is None

    def test_edge_with_policy(self) -> None:
        e = Edge(
            source_node_id="a",
            target_node_id="b",
            output_mapping={"out": "in"},
            data_policy=DataPolicy.SUMMARIZE,
            max_chars=2000,
        )
        assert e.data_policy == DataPolicy.SUMMARIZE
        assert e.max_chars == 2000


class TestPythonTask:
    def test_creation(self) -> None:
        t = PythonTask(
            id="t1",
            name="test_task",
            description="A test",
            code="x = 1",
            test_code="assert x == 1",
            tags=["test"],
        )
        assert t.task_type == TaskType.PYTHON
        assert t.risk_level == RiskLevel.LOW
        assert t.max_retries == 10

    def test_execute_success(
        self, execution_context: ExecutionContext
    ) -> None:
        t = PythonTask(
            id="t1",
            name="test_task",
            description="A test",
            code="outputs = {'result': 42}",
            test_code="",
            tags=[],
        )
        # Mock sandbox returns our outputs
        execution_context.sandbox._outputs = {"result": 42}  # type: ignore[attr-defined]
        result = t.execute(execution_context, {})
        assert result.status == ExecutionStatus.SUCCESS
        assert result.outputs == {"result": 42}


class TestLLMTask:
    def test_creation(self) -> None:
        t = LLMTask(
            id="t2",
            name="llm_task",
            description="An LLM task",
            prompt_template="Hello {{ name }}",
            tags=["test"],
        )
        assert t.task_type == TaskType.LLM
        assert t.context_budget == 32000

    def test_execute(self, execution_context: ExecutionContext) -> None:
        t = LLMTask(
            id="t2",
            name="llm_task",
            description="Test",
            prompt_template="Translate: {{ text }}",
            tags=[],
        )
        result = t.execute(execution_context, {"text": "hello"})
        assert result.status == ExecutionStatus.SUCCESS


class TestSkill:
    def test_creation(self) -> None:
        s = Skill(
            id="s1",
            name="test_skill",
            description="A skill",
            nodes=[SkillNode(node_id="n1", task_definition_id="t1")],
            edges=[],
            tags=["test"],
        )
        assert len(s.nodes) == 1
        assert s.is_meta is False

    def test_serialization(self) -> None:
        s = Skill(
            id="s1",
            name="test",
            description="d",
            nodes=[SkillNode(node_id="n1", task_definition_id="t1")],
            edges=[
                Edge(
                    source_node_id="n1",
                    target_node_id="n2",
                    output_mapping={"a": "b"},
                    data_policy=DataPolicy.TRUNCATE,
                )
            ],
        )
        data = s.model_dump()
        restored = Skill(**data)
        assert restored.edges[0].data_policy == DataPolicy.TRUNCATE


class TestToolkit:
    def test_creation(self) -> None:
        t = ToolkitModule(
            id="tk1",
            name="file_io",
            description="File I/O toolkit",
            module_path="/path/to/file_io.py",
            public_api=[{"name": "read_file", "description": "Read a file"}],
        )
        assert t.requires_approval is False
        assert len(t.public_api) == 1
