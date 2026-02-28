"""Main agent orchestrator — composes all services and drives the agent loop."""

from __future__ import annotations

import json
import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from helpers.executor.dag_executor import DAGExecutor
from helpers.llm.base_client import AbstractLLMClient
from models.task import ExecutionContext
from core.data.db.repository.task_repository import TaskRepository
from helpers.privacy.base_approval import AbstractApprovalGate
from helpers.privacy.base_scrubber import AbstractPrivacyScrubber
from registry.skill_registry import SkillRegistry
from registry.toolkit_registry import ToolkitRegistry
from seeds.seed_loader import SeedLoader
from core.container.base_runner import AbstractSandboxRunner
from api.handlers.intent_handler import IntentHandler
from api.handlers.execution_handler import ExecutionHandler
from api.handlers.feedback_handler import FeedbackHandler
from api.handlers.display_handler import DisplayHandler
from api.handlers.setup_handler import SetupHandler

logger = logging.getLogger(__name__)
console = Console()


class Agent:
    """Top-level orchestrator for the autonomous agent.

    Composes all services and drives: understand intent → decompose →
    build/execute → present → persist.
    """

    def __init__(
        self,
        executor: DAGExecutor,
        skill_registry: SkillRegistry,
        toolkit_registry: ToolkitRegistry,
        llm_client: AbstractLLMClient,
        sandbox: AbstractSandboxRunner,
        approval_gate: AbstractApprovalGate,
        scrubber: AbstractPrivacyScrubber,
        seed_loader: SeedLoader,
        task_repo: TaskRepository,
        config: dict[str, Any] | None = None,
        pref_repo=None,
    ) -> None:
        self._executor = executor
        self._skill_registry = skill_registry
        self._toolkit_registry = toolkit_registry
        self._llm_client = llm_client
        self._sandbox = sandbox
        self._approval_gate = approval_gate
        self._scrubber = scrubber
        self._seed_loader = seed_loader
        self._task_repo = task_repo
        self._config = config or {}
        self._pref_repo = pref_repo

        # Initialize handlers
        self.intent_handler = IntentHandler(executor, seed_loader, pref_repo)
        self.execution_handler = ExecutionHandler(executor, seed_loader, toolkit_registry, task_repo, scrubber)
        self.feedback_handler = FeedbackHandler(executor, seed_loader, skill_registry, task_repo)
        self.display_handler = DisplayHandler()
        self.setup_handler = SetupHandler(seed_loader, task_repo, skill_registry, toolkit_registry)

        # State tracking mappings
        self._execution_history: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        """Initialize the agent environment via the setup handler."""
        await self.setup_handler.initialize()

    async def run(
        self, user_input: str, file_paths: list[str] | None = None
    ) -> dict[str, Any]:
        """Main entry: understand intent → clarify → decompose → build/execute → present.

        Args:
            user_input: The user's natural language request.
            file_paths: Optional file paths selected by the user.

        Returns:
            Final results dict from execution.
        """
        await self.initialize()
        file_paths = file_paths or []

        context = ExecutionContext(
            sandbox=self._sandbox,
            llm_client=self._llm_client,
            approval_gate=self._approval_gate,
            scrubber=self._scrubber,
            config=self._config,
        )

        # 1. Understand Intent
        with console.status("[bold cyan]Analyzing request...[/bold cyan]"):
            intent_result = await self.intent_handler.understand_intent(
                user_input, context
            )
        logger.info("Parsed intent: %s", intent_result)

        if intent_result.get("is_feedback"):
            return await self.feedback_handler.refine_skill(
                intent_result,
                context,
                self._execution_history,
                lambda plan, ctx, initial: self.execution_handler.execute_plan(plan, ctx, initial, self._skill_registry),
                self._persist_objective
            )

        # 2. Seek Clarifications
        clarifications_dict = await self.intent_handler.seek_clarifications(
            intent_result, context
        )
        intent_result["clarifications"] = clarifications_dict

        # Merge any config-like answers (e.g., API keys) into intent
        for q, a in clarifications_dict.items():
            intent_result[q] = a

        # 3. Decompose & Plan
        with console.status("[bold magenta]Planning execution...[/bold magenta]"):
            plan = await self.intent_handler.decompose(
                intent_result, file_paths or [], context
            )
        logger.info("Generated plan: %s", plan)

        # 4. Build Any Missing Skills
        if plan.get("build_items"):
            with console.status("[bold yellow]Building missing skills...[/bold yellow]"):
                await self.execution_handler.build_missing_skills(
                    plan, file_paths or [], context
                )

        # 5. Execute Plan
        initial_payload = {
            "user_input": user_input,
            "file_paths": file_paths or [],
            "goal": intent_result.get("goal"),
            **intent_result, # Include all intent details
        }
        # Load user preferences and inject
        if hasattr(self, '_pref_repo') and self._pref_repo:
            prefs = await self._pref_repo.get_all()
            if prefs:
                initial_payload["user_preferences"] = prefs

        results = await self.execution_handler.execute_plan(
            plan, context, initial_payload, self._skill_registry
        )

        # Step E: Present
        self.display_handler.present_results(results)

        # Step F: Persist
        await self._persist_objective(user_input, plan, results)

        # Save state for potential future refinement
        self._execution_history.append({
            "plan": plan,
            "initial_payload": initial_payload,
            "results": results
        })
        if len(self._execution_history) > 10:
            self._execution_history.pop(0)

        return results


    def show_recent_context(self, limit: int = 10) -> None:
        """Display the recent execution context using the DisplayHandler."""
        self.display_handler.show_recent_context(self._execution_history, limit)

    async def _persist_objective(
        self,
        user_input: str,
        plan: dict[str, Any],
        results: dict[str, Any],
    ) -> None:
        """Save objective to DB for future reuse."""
        logger.info(
            "Persisted objective: %s (skills: %s)",
            user_input[:50],
            plan.get("skill_ids", []),
        )
