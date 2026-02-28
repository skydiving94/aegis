"""Handler for building skills and executing execution plans."""

import logging
from typing import Any

from models.task import ExecutionContext
from registry.toolkit_registry import ToolkitRegistry
from seeds.seed_loader import SeedLoader
from helpers.executor.dag_executor import DAGExecutor

logger = logging.getLogger(__name__)


class ExecutionHandler:
    """Handles skill building and DAG execution based on decomposition plans."""

    def __init__(
        self,
        executor: DAGExecutor,
        seed_loader: SeedLoader,
        toolkit_registry: ToolkitRegistry,
        task_repo: Any,
        scrubber: Any,
        pref_repo: Any = None,
    ) -> None:
        self._executor = executor
        self._seed_loader = seed_loader
        self._toolkit_registry = toolkit_registry
        self._task_repo = task_repo
        self._scrubber = scrubber
        self._pref_repo = pref_repo

    async def build_missing_skills(
        self,
        plan: dict[str, Any],
        file_paths: list[str],
        context: ExecutionContext,
    ) -> None:
        """For each build_new_skill item, run build_skill to create it."""
        build_items = plan.get("build_items", [])
        for item in build_items:
            try:
                # Scrub file contents for LLM
                scrubbed_files: dict[str, str] = {}
                for fp in file_paths:
                    try:
                        with open(fp) as f:
                            raw = f.read()
                        scrub_result = self._scrubber.scrub(raw)
                        scrubbed_files[fp] = scrub_result.scrubbed_text
                    except OSError:
                        logger.warning("Could not read file: %s", fp)

                # Gather context about available toolkits and existing tasks
                avail_tks = await self._toolkit_registry.list_available()
                avail_tks_dicts = [
                    {"name": tk.name, "description": tk.description}
                    for tk in avail_tks
                ]
                existing_tasks_list = []
                try:
                    for t in await self._task_repo.list_all():
                        task_type_val = getattr(t, "task_type", "python")
                        if hasattr(task_type_val, "value"):
                            task_type_val = task_type_val.value
                        existing_tasks_list.append({
                            "name": t.name,
                            "description": t.description,
                            "task_type": task_type_val,
                            "inputs": [
                                f.model_dump() if hasattr(f, "model_dump") else {"name": f.name, "io_type": f.io_type.value if hasattr(f.io_type, "value") else str(f.io_type), "description": f.description}
                                for f in t.inputs
                            ],
                            "outputs": [
                                f.model_dump() if hasattr(f, "model_dump") else {"name": f.name, "io_type": f.io_type.value if hasattr(f.io_type, "value") else str(f.io_type), "description": f.description}
                                for f in t.outputs
                            ]
                        })
                except Exception as e:
                    logger.warning("Could not load existing tasks for context: %s", e)

                user_prefs = {}
                if self._pref_repo:
                    try:
                        user_prefs = await self._pref_repo.get_all()
                    except Exception as e:
                        logger.warning("Could not load user preferences: %s", e)

                build_skill = self._seed_loader.load_one("build_skill")
                build_result = await self._executor.execute_skill(
                    build_skill,
                    context,
                    {
                        "objective_description": item.get("sub_objective", item.get("description", "")),
                        "objective_inputs": item.get("context", item).get("inputs", item.get("inputs", [])),
                        "objective_outputs": item.get("context", item).get("outputs", item.get("outputs", [])),
                        "scrubbed_files": scrubbed_files,
                        "available_toolkits": avail_tks_dicts,
                        "existing_tasks": existing_tasks_list,
                        "user_preferences": user_prefs,
                    },
                )

                # The 'register_skill' node provides 'skill_id'
                new_skill_id = build_result.get("skill_id")
                if new_skill_id:
                    if "skill_ids" not in plan:
                        plan["skill_ids"] = []
                    plan["skill_ids"].append(new_skill_id)
                    logger.info("Built and registered new skill: %s", new_skill_id)
                else:
                    logger.error("build_skill did not return a skill_id. Result: %s", build_result)

            except FileNotFoundError:
                logger.error("build_skill seed not found")
            except Exception as e:
                logger.error("Failed building skill for '%s': %s", item.get("sub_objective", "?"), e)

    async def execute_plan(
        self,
        plan: dict[str, Any],
        context: ExecutionContext,
        initial_payload: dict[str, Any] | None = None,
        skill_registry: Any = None,
    ) -> dict[str, Any]:
        """Run each skill via DAG executor, collect results."""
        results: dict[str, Any] = {}
        payload = initial_payload or {}
        
        skill_ids = plan.get("skill_ids", [])
        if not skill_ids:
            logger.warning("Plan contains no skill_ids to execute")
            return results

        if not skill_registry:
            raise ValueError("skill_registry required for execution")

        for skill_id in skill_ids:
            try:
                skill = await skill_registry.get(skill_id)
                skill_outputs = await self._executor.execute_skill(skill, context, payload)
                # Chain outputs to next skill's inputs
                payload.update(skill_outputs)
                results[f"skill_{skill_id}"] = skill_outputs
                logger.info("Successfully executed skill %s", skill_id)
            except Exception as e:
                logger.error("Failed to execute skill %s: %s", skill_id, e)
                results[f"skill_{skill_id}_error"] = str(e)
                # Halt execution on failure or continue? currently halt
                break

        return results
