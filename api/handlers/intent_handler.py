"""Handler for parsing user intent and obtaining clarifications."""

import json
import logging
from typing import Any

from models.task import ExecutionContext
from seeds.seed_loader import SeedLoader
from helpers.executor.dag_executor import DAGExecutor

logger = logging.getLogger(__name__)


class IntentHandler:
    """Handles intent extraction, clarification, and decomposition."""

    def __init__(
        self,
        executor: DAGExecutor,
        seed_loader: SeedLoader,
        pref_repo: Any = None,
    ) -> None:
        self._executor = executor
        self._seed_loader = seed_loader
        self._pref_repo = pref_repo

    async def understand_intent(
        self, user_input: str, context: ExecutionContext
    ) -> dict[str, Any]:
        """Run understand_intent meta-skill to extract structured intent."""
        try:
            intent_skill = self._seed_loader.load_one("understand_intent")
            intent_result = await self._executor.execute_skill(
                intent_skill, context, {"user_input": user_input}
            )
            # Ensure we always have the core intent fields
            intent_result.setdefault("goal", user_input)
            intent_result.setdefault("entities", [])
            intent_result.setdefault("constraints", [])
            intent_result.setdefault("domain", "general")
            return intent_result
        except (FileNotFoundError, Exception) as e:
            logger.warning("understand_intent failed (%s), using raw input", e)
            return {
                "goal": user_input,
                "entities": [],
                "constraints": [],
                "domain": "general",
            }

    async def decompose(
        self,
        intent_result: dict[str, Any],
        file_paths: list[str],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Run decompose_objective meta-skill to break goal into sub-objectives."""
        try:
            decompose_skill = self._seed_loader.load_one("decompose_objective")
            plan_result = await self._executor.execute_skill(
                decompose_skill,
                context,
                {**intent_result, "file_paths": file_paths},
            )
            return plan_result
        except (FileNotFoundError, Exception) as e:
            logger.warning("decompose_objective failed (%s), returning stub plan", e)
            return {"sub_objectives": [], "build_items": [], "skill_ids": []}

    async def seek_clarifications(
        self, intent_result: dict[str, Any], context: ExecutionContext
    ) -> dict[str, str]:
        """Check if the request needs clarification and ask the user.

        Uses the LLM to determine if any info is missing to fulfill the request.
        Returns a dict of question -> answer pairs.
        """
        clarifications: dict[str, str] = {}
        try:
            prompt = (
                f"The user wants: {intent_result.get('goal', '')}\\n"
                f"Domain: {intent_result.get('domain', 'general')}\\n"
                f"Entities: {intent_result.get('entities', [])}\\n"
                f"Constraints: {intent_result.get('constraints', [])}\\n\\n"
                "Does this request require any external resources, API keys, "
                "credentials, or clarifications from the user that the agent "
                "cannot determine on its own? If yes, list up to 3 specific "
                "questions to ask. If no, return an empty list.\\n\\n"
                'Respond as JSON: {"needs_clarification": bool, "questions": [str]}'
            )
            response = context.llm_client.send(
                prompt=prompt,
                usage_type="intent",
                force_json=True,
            )
            parsed = json.loads(response.content) if isinstance(response.content, str) else response.content
            if parsed.get("needs_clarification") and parsed.get("questions"):
                for question in parsed["questions"]:
                    answer = context.approval_gate.seek_clarification(
                        question,
                        {"goal": intent_result.get("goal", ""), "domain": intent_result.get("domain", "")}
                    )
                    if answer:
                        clarifications[question] = answer
        except Exception as e:
            logger.debug("Clarification check skipped: %s", e)

        # Persist clarification answers as user preferences
        if clarifications and self._pref_repo:
            for question, answer in clarifications.items():
                pref_key = question[:100].lower().replace(" ", "_").replace("?", "")
                await self._pref_repo.set(
                    key=pref_key,
                    value=answer,
                    domain=intent_result.get("domain", "general"),
                    source="clarification",
                )

        return clarifications
