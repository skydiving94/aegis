"""Task definitions: AbstractTask, PythonTask, LLMTask, TaskResult, ExecutionContext."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal

from jinja2 import Template
from pydantic import BaseModel, Field

from models.enums import ExecutionStatus, RiskLevel, TaskType
from models.io_types import Precondition, TypedIOField
from helpers.llm.base_client import AbstractLLMClient
from helpers.privacy.base_approval import AbstractApprovalGate
from helpers.privacy.base_scrubber import AbstractPrivacyScrubber
from core.container.base_runner import AbstractSandboxRunner

logger = logging.getLogger(__name__)


class ExecutionContext(BaseModel):
    """Container for runtime dependencies injected into task execution."""

    model_config = {"arbitrary_types_allowed": True}

    sandbox: AbstractSandboxRunner
    llm_client: AbstractLLMClient
    approval_gate: AbstractApprovalGate
    scrubber: AbstractPrivacyScrubber
    config: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Result of a single task execution."""

    outputs: dict[str, Any] = Field(default_factory=dict)
    logs: str = ""
    status: ExecutionStatus = ExecutionStatus.SUCCESS


class AbstractTask(ABC, BaseModel):
    """Base class for all task definitions.

    Subclasses must implement execute() for their specific execution strategy.
    """

    id: str
    name: str
    description: str
    task_type: TaskType
    inputs: list[TypedIOField] = Field(default_factory=list)
    outputs: list[TypedIOField] = Field(default_factory=list)
    preconditions: list[Precondition] = Field(default_factory=list)
    toolkit_refs: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    max_retries: int = 10
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"arbitrary_types_allowed": True}

    @abstractmethod
    def execute(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> TaskResult:
        """Execute the task.

        Args:
            context: Runtime context (sandbox, llm_client, approval_gate, etc.)
            payload: Input data mapped from upstream node outputs.

        Returns:
            TaskResult with output data and execution logs.
        """
        ...


class PythonTask(AbstractTask):
    """A task that executes Python code in a sandboxed subprocess."""

    task_type: Literal[TaskType.PYTHON] = TaskType.PYTHON
    code: str = ""
    test_code: str = ""

    def execute(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> TaskResult:
        """Run self.code in sandbox with payload injection."""
        result = context.sandbox.run(
            code=self.code,
            inputs=payload,
            toolkit_refs=self.toolkit_refs,
            timeout=context.config.get("timeout", 30),
        )
        if result.return_code != 0:
            return TaskResult(
                outputs={},
                logs=f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
                status=ExecutionStatus.FAILED,
            )
        # Print stderr (task creation logs, debug info) so user can see them
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                if line.strip():
                    print(line)
        return TaskResult(
            outputs=result.outputs,
            logs=result.stdout,
            status=ExecutionStatus.SUCCESS,
        )


class LLMTask(AbstractTask):
    """A task that renders a prompt template and sends it to an LLM."""

    task_type: Literal[TaskType.LLM] = TaskType.LLM
    prompt_template: str = ""
    system_instruction: str = ""
    context_budget: int = 32000  # max chars for rendered prompt payload

    def execute(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> TaskResult:
        """Render Jinja2 template, truncate to context_budget, send to LLM."""
        from jinja2 import Environment, DebugUndefined

        env = Environment(undefined=DebugUndefined)
        # Add tojson filter since it's not available by default
        env.filters['tojson'] = lambda v: json.dumps(v, default=str, ensure_ascii=False)
        template = env.from_string(self.prompt_template)
        rendered = template.render(**payload)

        # Enforce context budget — truncate if rendered prompt exceeds limit
        if len(rendered) > self.context_budget:
            rendered = rendered[: self.context_budget] + "\n[...TRUNCATED]"

        response = context.llm_client.send(
            prompt=rendered,
            system_instruction=self.system_instruction,
            usage_type=context.config.get("usage_type", "task_execution"),
            force_json=True,
        )

        logger.debug("LLMTask '%s' raw response: %s", self.name, response.content[:500])

        # Parse the LLM response as JSON
        try:
            parsed_outputs = json.loads(response.content)
            if not isinstance(parsed_outputs, dict):
                parsed_outputs = {"result": parsed_outputs}
        except json.JSONDecodeError:
            # Fallback for unexpected raw text
            parsed_outputs = {"text": response.content}

        # If we have defined output fields, filter to only those.
        # If no outputs are defined, pass through ALL parsed fields.
        if self.outputs:
            final_outputs: dict[str, Any] = {}
            for out in self.outputs:
                if out.name in parsed_outputs:
                    final_outputs[out.name] = parsed_outputs[out.name]
            # If none of the defined outputs matched, fall back to full parsed
            if not final_outputs:
                logger.warning(
                    "LLMTask '%s': none of the defined output fields %s found in response keys %s. Passing through all.",
                    self.name,
                    [o.name for o in self.outputs],
                    list(parsed_outputs.keys()),
                )
                final_outputs = parsed_outputs
        else:
            # No outputs defined — pass through everything
            final_outputs = parsed_outputs

        return TaskResult(
            outputs=final_outputs,
            logs=f"LLM Token Usage: {response.input_tokens} in, "
            f"{response.output_tokens} out. Cost: ${response.cost_usd:.4f}",
            status=ExecutionStatus.SUCCESS,
        )
