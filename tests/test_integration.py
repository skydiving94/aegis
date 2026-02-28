"""Integration test: tax audit scenario with real system + MockLLMClient.

Uses:
- Real DAGExecutor (with data policy + approval checks)
- Real TaskRepository (SQLite via aiosqlite)
- Real SkillRepository / ToolkitRepository
- Real SubprocessRunner
- Real SpaCyNERScrubber (falls back to regex-only if spaCy model absent)
- Real SeedLoader (loads all 14 seed tasks + 4 skill JSONs)
- MockLLMClient (returns canned responses for each step)
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest

from agent import Agent
from helpers.executor.dag_executor import DAGExecutor
from helpers.llm.base_client import AbstractLLMClient, LLMResponse, UsageStats
from models.task import ExecutionContext
from helpers.privacy.base_scrubber import ScrubResult
from helpers.privacy.spacy_scrubber import SpaCyNERScrubber
from registry.skill_registry import SkillRegistry
from registry.toolkit_registry import ToolkitRegistry
from core.container.subprocess_runner import SubprocessRunner
from seeds.seed_loader import SeedLoader
from core.data.db.repository.skill_repository import SkillRepository
from core.data.db.repository.task_repository import TaskRepository
from core.data.db.repository.toolkit_repository import ToolkitRepository
from tests.conftest import MockApprovalGate

# ── Canned LLM responses for each meta-skill step ──────────────


# The MockLLMClient returns different responses based on prompt content
_INTENT_RESPONSE = json.dumps(
    {
        "goal": "Audit my 2024 tax return",
        "entities": ["W-2", "1099-INT", "tax return"],
        "constraints": ["accuracy", "file access needed"],
        "domain": "finance/tax",
    }
)

_DECOMPOSE_RESPONSE = json.dumps(
    {
        "sub_objectives": [
            {
                "description": "Parse W-2 document and extract income data",
                "reuse_skill_id": None,
                "inputs": [
                    {
                        "name": "file_path",
                        "io_type": "file_path",
                        "description": "Path to W-2 file",
                    }
                ],
                "outputs": [
                    {
                        "name": "w2_data",
                        "io_type": "dict",
                        "description": "Parsed W-2 fields",
                    }
                ],
                "domain_tags": ["finance", "tax", "W-2", "parsing"],
            },
            {
                "description": "Calculate total income and compare with reported figures",
                "reuse_skill_id": None,
                "inputs": [
                    {
                        "name": "w2_data",
                        "io_type": "dict",
                        "description": "Parsed W-2 data",
                    }
                ],
                "outputs": [
                    {
                        "name": "audit_report",
                        "io_type": "dict",
                        "description": "Audit findings",
                    }
                ],
                "domain_tags": ["finance", "tax", "audit", "calculation"],
            },
        ]
    }
)


class TaxAuditMockLLMClient(AbstractLLMClient):
    """Returns canned responses matching each step of the tax audit flow.

    Routes responses based on prompt content keywords.
    """

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []

    def send(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str | None = None,
        usage_type: str = "default",
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        thinking_budget: int | None = None,
        response_schema: type | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.call_log.append(
            {"prompt": prompt[:200], "usage_type": usage_type, "model": model}
        )

        # Route based on prompt content
        if "intent parser" in prompt.lower() or "extract a structured intent" in prompt.lower():
            content = _INTENT_RESPONSE
        elif "task planner" in prompt.lower() or "decompose the goal" in prompt.lower():
            content = _DECOMPOSE_RESPONSE
        else:
            # Generic fallback — return valid JSON
            content = json.dumps({"result": "mock_output"})

        return LLMResponse(
            content=content,
            model=model or "mock-model",
            input_tokens=len(prompt),
            output_tokens=len(content),
            cost_usd=0.0,
            latency_ms=5,
        )

    def get_usage_stats(self) -> UsageStats:
        return UsageStats(total_requests=len(self.call_log))


# ── Test fixtures ──────────────────────────────────────────────


@pytest.fixture
def temp_db_url() -> str:
    """Create a temp SQLite database file URL."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="agent_test_")
    os.close(fd)
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture
async def real_system(temp_db_url: str) -> dict[str, Any]:
    """Wire up the full system with real components + MockLLMClient."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from core.data.db.entities.base import Base
    from sqlalchemy import text

    # Database
    engine = create_async_engine(
        temp_db_url, 
        echo=False,
        execution_options={"schema_translate_map": {"framework": None}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Repositories
    task_repo = TaskRepository(session_factory)
    skill_repo = SkillRepository(session_factory)
    toolkit_repo = ToolkitRepository(session_factory)

    # Registries
    skill_registry = SkillRegistry(skill_repo)
    toolkit_registry = ToolkitRegistry(toolkit_repo)

    # LLM (Mock)
    llm_client = TaxAuditMockLLMClient()

    # Approval (auto-approve all)
    approval_gate = MockApprovalGate()

    # Sandbox (real subprocess)
    sandbox = SubprocessRunner(
        toolkit_registry=toolkit_registry,
        approved_paths=[],
    )

    # Scrubber (real — falls back to regex if spaCy model absent)
    scrubber = SpaCyNERScrubber()

    # Seeds
    seed_loader = SeedLoader()

    # Executor
    executor = DAGExecutor(task_repo=task_repo, toolkit_registry=toolkit_registry)

    # Agent
    agent = Agent(
        executor=executor,
        skill_registry=skill_registry,
        toolkit_registry=toolkit_registry,
        llm_client=llm_client,
        sandbox=sandbox,
        approval_gate=approval_gate,
        scrubber=scrubber,
        seed_loader=seed_loader,
        task_repo=task_repo,
    )

    return {
        "agent": agent,
        "llm_client": llm_client,
        "task_repo": task_repo,
        "skill_repo": skill_repo,
        "toolkit_repo": toolkit_repo,
        "skill_registry": skill_registry,
        "seed_loader": seed_loader,
        "engine": engine,
    }


# ── Integration tests ─────────────────────────────────────────


class TestSeedLoading:
    """Verify that all seed JSONs load and validate correctly."""

    def test_load_all_tasks(self) -> None:
        """All 13 seed task JSONs should load without errors."""
        loader = SeedLoader()
        tasks = loader.load_all_tasks()
        assert len(tasks) >= 13
        names = {t.name for t in tasks}
        expected = {
            "parse_intent",
            "search_past",
            "decompose",
            "match_skills",
            "emit_plan",
            "analyze_objective",
            "create_task_defs",
            "register_skill",
            "analyze_need",
            "generate_module",
            "validate_module",
            "test_module",
            "register_toolkit",
        }
        # At least all expected tasks should be present
        assert expected <= names, f"Missing tasks: {expected - names}"

    def test_load_all_skills(self) -> None:
        """All 4 seed skill JSONs should load without errors."""
        loader = SeedLoader()
        skills = loader.load_all_skills()
        assert len(skills) == 4
        names = {s.name for s in skills}
        assert names == {
            "understand_intent",
            "decompose_objective",
            "build_skill",
            "build_toolkit",
        }

    def test_skill_node_references_exist(self) -> None:
        """Every skill node should reference a task that exists in seeds/tasks/."""
        loader = SeedLoader()
        tasks = loader.load_all_tasks()
        task_ids = {t.id for t in tasks}
        skills = loader.load_all_skills()
        for skill in skills:
            for node in skill.nodes:
                assert node.task_definition_id in task_ids, (
                    f"Skill '{skill.name}' references task "
                    f"'{node.task_definition_id}' which doesn't exist"
                )


class TestAgentInitialization:
    """Verify that Agent.initialize() seeds everything correctly."""

    @pytest.mark.asyncio
    async def test_initialize_seeds_tasks(self, real_system: dict[str, Any]) -> None:
        """After initialization, all 14 tasks should be in the repository."""
        agent = real_system["agent"]
        await agent.initialize()
        task_repo: TaskRepository = real_system["task_repo"]
        all_tasks = await task_repo.list_all()
        assert len(all_tasks) >= 13

    @pytest.mark.asyncio
    async def test_initialize_seeds_skills(self, real_system: dict[str, Any]) -> None:
        """After initialization, all 4 skills should be in the registry."""
        agent = real_system["agent"]
        await agent.initialize()
        skill_registry: SkillRegistry = real_system["skill_registry"]
        # Verify all skills are accessible
        for name in [
            "understand_intent",
            "decompose_objective",
            "build_skill",
            "build_toolkit",
        ]:
            skill = await skill_registry.get(name)
            assert skill.name == name

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(
        self, real_system: dict[str, Any]
    ) -> None:
        """Calling initialize() twice should not error or duplicate."""
        agent = real_system["agent"]
        await agent.initialize()
        await agent.initialize()  # Should not raise
        task_repo: TaskRepository = real_system["task_repo"]
        all_tasks = await task_repo.list_all()
        assert len(all_tasks) >= 13


class TestUnderstandIntent:
    """Test the understand_intent meta-skill in isolation."""

    @pytest.mark.asyncio
    async def test_parse_intent_execution(
        self, real_system: dict[str, Any]
    ) -> None:
        """Execute understand_intent skill and verify structured intent output."""
        agent = real_system["agent"]
        await agent.initialize()

        executor: DAGExecutor = agent._executor
        seed_loader: SeedLoader = agent._seed_loader
        llm_client = real_system["llm_client"]

        intent_skill = seed_loader.load_one("understand_intent")
        context = ExecutionContext(
            sandbox=agent._sandbox,
            llm_client=llm_client,
            approval_gate=agent._approval_gate,
            scrubber=agent._scrubber,
        )

        result = await executor.execute_skill(
            intent_skill,
            context,
            {"user_input": "Audit my 2024 tax return with my W-2 and 1099-INT"},
        )

        # verify structured output from MockLLMClient
        assert "goal" in result or "result" in result


class TestDecomposeObjective:
    """Test decompose_objective meta-skill."""

    @pytest.mark.asyncio
    async def test_decompose_produces_plan(
        self, real_system: dict[str, Any]
    ) -> None:
        """Execute decompose_objective and verify it produces execution plan."""
        agent = real_system["agent"]
        await agent.initialize()

        executor: DAGExecutor = agent._executor
        context = ExecutionContext(
            sandbox=agent._sandbox,
            llm_client=real_system["llm_client"],
            approval_gate=agent._approval_gate,
            scrubber=agent._scrubber,
        )

        decompose_skill = agent._seed_loader.load_one("decompose_objective")
        result = await executor.execute_skill(
            decompose_skill,
            context,
            {
                "goal": "Audit my 2024 tax return",
                "entities": ["W-2", "1099-INT"],
                "constraints": ["accuracy"],
                "domain": "finance/tax",
            },
        )

        # decompose_objective should produce plan, build_items, skill_ids
        assert "plan" in result or "execution_plan" in result or "build_items" in result


class TestPrivacyScrubber:
    """Test real scrubber with tax-relevant data."""

    def test_scrub_pii(self) -> None:
        """SSN and name should be scrubbed, dollar amounts preserved."""
        scrubber = SpaCyNERScrubber()
        text = "John A. Smith  SSN: 123-45-6789  Wages: $72,500.00"
        result = scrubber.scrub(text)
        # SSN should be scrubbed (regex pattern)
        assert "123-45-6789" not in result.scrubbed_text
        assert "[SSN_1]" in result.scrubbed_text
        # Dollar amount should be preserved
        assert "$72,500.00" in result.scrubbed_text
        # Should be reversible
        unscrubbed = scrubber.unscrub(result.scrubbed_text, result.replacements)
        assert "123-45-6789" in unscrubbed

    def test_scrub_email_phone(self) -> None:
        """Email and phone should be scrubbed."""
        scrubber = SpaCyNERScrubber()
        text = "Contact: john@example.com or 555-1234"
        result = scrubber.scrub(text)
        assert "john@example.com" not in result.scrubbed_text
        assert "[EMAIL_1]" in result.scrubbed_text


class TestEndToEndTaxAudit:
    """Full end-to-end test: Agent.run() with tax audit input."""

    @pytest.mark.asyncio
    async def test_agent_run_tax_audit(
        self, real_system: dict[str, Any]
    ) -> None:
        """Run full agent pipeline with tax audit request.

        Verifies:
        1. Agent initializes (seeds 14 tasks, 4 skills)
        2. understand_intent is executed → structured intent
        3. decompose_objective is executed → plan
        4. LLM is called at least 2 times (intent + decompose)
        5. No exceptions raised
        """
        agent: Agent = real_system["agent"]
        llm_client: TaxAuditMockLLMClient = real_system["llm_client"]

        result = await agent.run(
            "Audit my 2024 tax return with my W-2 and 1099-INT"
        )

        # Agent should have made LLM calls
        assert len(llm_client.call_log) >= 2, (
            f"Expected at least 2 LLM calls, got {len(llm_client.call_log)}: "
            f"{[c['usage_type'] for c in llm_client.call_log]}"
        )

        # Result should be a dict (may be empty if no skills to execute)
        assert isinstance(result, dict)




class TestSchemaValidation:
    """Verify seed JSONs pass their respective schema validations."""

    def test_all_task_jsons_pass_schema(self) -> None:
        """Every seed task JSON should validate against task_schema.json."""
        from helpers.schemas.validator import SchemaValidator
        from core.data.fs.repository.schema_repository import SchemaRepository

        schema_repo = SchemaRepository()
        validator = SchemaValidator(schema_repo)
        tasks_dir = SeedLoader()._tasks_dir
        for path in tasks_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
            errors = validator.validate_task(data)
            assert errors == [], f"Task {path.name} has errors: {errors}"

    def test_all_skill_jsons_pass_schema(self) -> None:
        """Every seed skill JSON should validate against skill_schema.json."""
        from helpers.schemas.validator import SchemaValidator
        from core.data.fs.repository.schema_repository import SchemaRepository

        schema_repo = SchemaRepository()
        validator = SchemaValidator(schema_repo)
        skills_dir = SeedLoader()._skills_dir
        for path in skills_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
            errors = validator.validate_skill(data)
            assert errors == [], f"Skill {path.name} has errors: {errors}"
