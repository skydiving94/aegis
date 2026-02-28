"""Handler for refining skills based on user feedback."""

import logging
from typing import Any

from rich.console import Console

from models.task import ExecutionContext
from seeds.seed_loader import SeedLoader
from helpers.executor.dag_executor import DAGExecutor

logger = logging.getLogger(__name__)
console = Console()


class FeedbackHandler:
    """Handles refining a previously executed skill based on user feedback."""

    def __init__(
        self,
        executor: DAGExecutor,
        seed_loader: SeedLoader,
        skill_registry: Any,
        task_repo: Any,
    ) -> None:
        self._executor = executor
        self._seed_loader = seed_loader
        self._skill_registry = skill_registry
        self._task_repo = task_repo

    async def refine_skill(
        self,
        intent_result: dict[str, Any],
        context: ExecutionContext,
        last_execution_history: list[dict[str, Any]],
        execute_plan_callback: Any,
        persist_callback: Any,
    ) -> dict[str, Any]:
        """Refine a previously executed skill based on user feedback."""
        if not last_execution_history:
            logger.warning("No previous execution state to refine.")
            return {}
            
        last_execution = last_execution_history[-1]
        plan = last_execution.get("plan", {})
        skill_ids = plan.get("skill_ids", [])
        if not skill_ids:
            logger.warning("No skill IDs in last execution to refine.")
            return last_execution.get("results", {})
            
        target_skill_id = skill_ids[-1]  # Refine the last executed skill
        
        # 1. Fetch the exact JSON definition of the last skill
        last_skill_definition = {}
        try:
            skill = await self._skill_registry.get(target_skill_id)
            tasks = []
            for t_id in skill.tasks:
                task_obj = await self._task_repo.get_by_id(t_id)
                if task_obj:
                    t_dict = {
                        "name": task_obj.name,
                        "description": task_obj.description,
                        "task_type": getattr(task_obj.task_type, "value", str(task_obj.task_type)),
                        "inputs": [{"name": f.name, "io_type": getattr(f.io_type, "value", str(f.io_type)), "description": f.description} for f in task_obj.inputs],
                        "outputs": [{"name": f.name, "io_type": getattr(f.io_type, "value", str(f.io_type)), "description": f.description} for f in task_obj.outputs],
                    }
                    if hasattr(task_obj, "code") and task_obj.code:
                        t_dict["code"] = task_obj.code
                    tasks.append(t_dict)
                    
            last_skill_definition = {
                "skill_name": skill.name,
                "skill_description": skill.description,
                "tags": skill.tags,
                "task_definitions": tasks,
            }
            last_edges = []
            for e in skill.edges:
                src = await self._task_repo.get_by_id(e.source_task_id)
                tgt = await self._task_repo.get_by_id(e.target_task_id)
                if src and tgt:
                    last_edges.append({
                        "source_task_name": src.name,
                        "target_task_name": tgt.name,
                        "output_mapping": e.output_mapping
                    })
            last_skill_definition["edges"] = last_edges
        except Exception as e:
            logger.error("Failed to extract previous skill definition: %s", e)
            
        # 2. Run the refine_skill meta task
        refine_skill = self._seed_loader.load_one("refine_skill")
        feedback = intent_result.get("goal", "Please fix this skill.")
        
        console.print("[bold yellow]🧠 Analyzing errors and rewriting skill code...[/bold yellow]")
        refine_payload = {
            "feedback": feedback,
            "last_skill_id": target_skill_id,
            "last_skill_definition": last_skill_definition,
            "last_execution_results": last_execution.get("results", {})
        }
        
        refine_result = await self._executor.execute_skill(refine_skill, context, refine_payload)
        
        # 3. Register the new skill
        new_skill_id = refine_result.get("skill_id")
        if not new_skill_id:
            logger.error("refine_skill did not return a new skill_id!")
            return last_execution.get("results", {})
            
        console.print(f"[bold green]✨ Refined skill built: {new_skill_id}[/bold green]")
        
        # 4. Execute the new skill using the initial payload
        initial_payload = last_execution.get("initial_payload", {})
        if "user_input" in intent_result:
            initial_payload["user_input"] = intent_result["user_input"]
            initial_payload["goal"] = intent_result["goal"]
            
        console.print("[bold green]▶ Executing refined skill...[/bold green]")
        plan = {"skill_ids": [new_skill_id]}
        results = await execute_plan_callback(plan, context, initial_payload)
        
        await persist_callback(intent_result.get("user_input", "Feedback"), plan, results)
        
        last_execution_history.append({
            "plan": plan,
            "initial_payload": initial_payload,
            "results": results
        })
        if len(last_execution_history) > 10:
            last_execution_history.pop(0)
        
        return results
