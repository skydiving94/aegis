"""Shared test fixtures."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from helpers.llm.base_client import AbstractLLMClient, LLMResponse, UsageStats
from models.enums import RiskLevel
from models.task import ExecutionContext, TaskResult
from helpers.privacy.base_approval import AbstractApprovalGate
from helpers.privacy.base_scrubber import AbstractPrivacyScrubber, ScrubResult
from core.container.base_runner import AbstractSandboxRunner, SandboxResult


class MockLLMClient(AbstractLLMClient):
    """Mock LLM client that returns canned responses."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or ["{}"]
        self._call_count = 0

    def send(self, prompt: str, **kwargs: Any) -> LLMResponse:
        response = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        return LLMResponse(
            content=response,
            model="mock-model",
            input_tokens=len(prompt),
            output_tokens=len(response),
        )

    def get_usage_stats(self) -> UsageStats:
        return UsageStats()


class MockSandboxRunner(AbstractSandboxRunner):
    """Mock sandbox that returns predefined outputs."""

    def __init__(self, outputs: dict[str, Any] | None = None) -> None:
        self._outputs = outputs or {}

    def run(
        self,
        code: str,
        inputs: dict[str, Any],
        toolkit_refs: list[str],
        timeout: int = 30,
    ) -> SandboxResult:
        return SandboxResult(
            outputs=self._outputs,
            stdout="",
            stderr="",
            return_code=0,
            duration_ms=10,
        )


class MockApprovalGate(AbstractApprovalGate):
    """Mock approval gate that always approves."""

    def approve_file_read(self, path: str) -> bool:
        return True

    def approve_file_write(self, path: str) -> bool:
        return True

    def approve_pip_install(self, package: str) -> bool:
        return True

    def approve_task_execution(
        self, task_name: str, description: str, risk_level: RiskLevel
    ) -> bool:
        return True

    def approve_task_output(self, task_name: str, result: TaskResult) -> bool:
        return True

    def seek_clarification(self, question: str, context: dict[str, str]) -> str | None:
        return None

    def get_approved_paths(self) -> list[str]:
        return []


class MockScrubber(AbstractPrivacyScrubber):
    """Mock scrubber that returns text unchanged."""

    def scrub(self, text: str) -> ScrubResult:
        return ScrubResult(scrubbed_text=text, replacements={})

    def unscrub(self, text: str, replacements: dict[str, str]) -> str:
        return text


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()


@pytest.fixture
def mock_sandbox() -> MockSandboxRunner:
    return MockSandboxRunner()


@pytest.fixture
def mock_approval() -> MockApprovalGate:
    return MockApprovalGate()


@pytest.fixture
def mock_scrubber() -> MockScrubber:
    return MockScrubber()


@pytest.fixture
def execution_context(
    mock_sandbox: MockSandboxRunner,
    mock_llm: MockLLMClient,
    mock_approval: MockApprovalGate,
    mock_scrubber: MockScrubber,
) -> ExecutionContext:
    return ExecutionContext(
        sandbox=mock_sandbox,
        llm_client=mock_llm,
        approval_gate=mock_approval,
        scrubber=mock_scrubber,
    )
