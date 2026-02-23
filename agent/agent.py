"""Main agent orchestrator — composes all services and drives the agent loop."""

from __future__ import annotations

import json
import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from agent.executor.dag_executor import DAGExecutor
from agent.llm.base_client import AbstractLLMClient
from agent.models.task import ExecutionContext
from agent.store.task_repository import TaskRepository
from agent.privacy.base_approval import AbstractApprovalGate
from agent.privacy.base_scrubber import AbstractPrivacyScrubber
from agent.registry.skill_registry import SkillRegistry
from agent.registry.toolkit_registry import ToolkitRegistry
from agent.seeds.seed_loader import SeedLoader
from agent.sandbox.base_runner import AbstractSandboxRunner

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
        self._initialized = False
        self._last_execution: dict[str, Any] | None = None

    async def initialize(self) -> None:
        """Register internal toolkits, seed tasks, and seed skills.

        Must be called before run(). Idempotent — skips if already done.
        """
        if self._initialized:
            return

        # Step 1: Register internal toolkits so SubprocessRunner can
        # resolve them to PYTHONPATH entries via get_module_path().
        await self._register_internal_toolkits()

        # Step 2: Load and persist seed task definitions
        seed_tasks = self._seed_loader.load_all_tasks()
        for task in seed_tasks:
            await self._task_repo.save(task)
            logger.info("Seeded task: %s", task.name)

        # Step 3: Load and persist seed skill definitions
        seed_skills = self._seed_loader.load_all_skills()
        for skill in seed_skills:
            await self._skill_registry.register(skill)
            logger.info("Seeded skill: %s", skill.name)

        # Step 4: Eagerly load all toolkits into the registry cache
        # so that SubprocessRunner._build_env() (which is synchronous)
        # doesn't encounter KeyErrors when resolving paths.
        all_tks = await self._toolkit_registry.list_available()
        for tk in all_tks:
            await self._toolkit_registry.get(tk.id)

        self._initialized = True
        logger.info(
            "Initialization complete: %d tasks, %d skills, %d toolkits cached",
            len(seed_tasks),
            len(seed_skills),
            len(all_tks)
        )

    async def _register_internal_toolkits(self) -> None:
        """Register db_access and schema_validator as internal toolkits."""
        import os
        from agent.models.toolkit import ToolkitModule

        internal_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "internal_toolkits"
        )

        toolkits = [
            ToolkitModule(
                id="db_access",
                name="db_access",
                description="Database access for meta-skill task nodes. "
                "Provides search_objectives, search_skills_by_tags, "
                "save_task, save_skill, save_toolkit.",
                module_path=os.path.join(internal_dir, "db_access.py"),
                public_api=[
                    {"name": "search_objectives", "description": "Search past objectives"},
                    {"name": "search_skills_by_tags", "description": "Search skills by tag overlap"},
                    {"name": "save_task", "description": "Save task definition"},
                    {"name": "save_skill", "description": "Save skill definition"},
                    {"name": "save_toolkit", "description": "Save toolkit definition"},
                ],
            ),
            ToolkitModule(
                id="schema_validator",
                name="schema_validator",
                description="Schema validation for meta-skill task nodes. "
                "Provides validate_task_schema, validate_skill_schema, "
                "validate_toolkit_schema.",
                module_path=os.path.join(internal_dir, "schema_validator.py"),
                public_api=[
                    {"name": "validate_task_schema", "description": "Validate task JSON"},
                    {"name": "validate_skill_schema", "description": "Validate skill JSON"},
                    {"name": "validate_toolkit_schema", "description": "Validate toolkit JSON"},
                ],
            ),
        ]

        for tk in toolkits:
            await self._toolkit_registry.register(tk)
            logger.info("Registered internal toolkit: %s → %s", tk.id, tk.module_path)

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

        # Step A: Understand intent
        console.print("[bold cyan]🔍 Understanding intent...[/bold cyan]")
        intent_result = await self._understand_intent(user_input, context)

        # Step A.5: Seek clarification if needed
        clarifications = await self._seek_clarifications(intent_result, context)
        if clarifications:
            intent_result["clarifications"] = clarifications
            # Merge any config-like answers (e.g., API keys) into intent
            for q, a in clarifications.items():
                intent_result[q] = a

        # Branch based on intent type
        intent_type = intent_result.get("intent_type", "NEW_GOAL")
        if intent_type == "FEEDBACK" and self._last_execution:
            console.print("[bold magenta]🔧 Refining previous skill based on feedback...[/bold magenta]")
            return await self._refine_skill(intent_result, context)

        # Step B: Decompose into plan
        console.print("[bold cyan]📋 Decomposing into plan...[/bold cyan]")
        plan = await self._decompose(intent_result, file_paths, context)

        # Step C: Build missing skills
        if plan.get("build_items"):
            console.print("[bold yellow]🔨 Building missing skills...[/bold yellow]")
            await self._build_missing(plan, file_paths, context)

        # Step D: Execute all skills
        console.print("[bold green]▶ Executing skills...[/bold green]")
        # Seed execution with the parsed intent + user preferences
        initial_payload = {
            "user_input": user_input,
            **intent_result,
        }
        # Load user preferences and inject
        if hasattr(self, '_pref_repo') and self._pref_repo:
            prefs = await self._pref_repo.get_all()
            if prefs:
                initial_payload["user_preferences"] = prefs
        results = await self._execute_plan(plan, context, initial_payload)

        # Step E: Present
        self._present_results(results)

        # Step F: Persist
        await self._persist_objective(user_input, plan, results)

        # Save state for potential future refinement
        self._last_execution = {
            "plan": plan,
            "initial_payload": initial_payload,
            "results": results
        }

        return results

    async def _refine_skill(self, intent_result: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        """Refine a previously executed skill based on user feedback."""
        if not self._last_execution:
            logger.warning("No previous execution state to refine.")
            return {}
            
        plan = self._last_execution.get("plan", {})
        skill_ids = plan.get("skill_ids", [])
        if not skill_ids:
            logger.warning("No skill IDs in last execution to refine.")
            return self._last_execution.get("results", {})
            
        target_skill_id = skill_ids[-1]  # Refine the last executed skill (typically the main one)
        
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
                "edges": [
                    {
                        "source_task_name": await self._task_repo.get_by_id(e.source_task_id).then(lambda t: t.name) if getattr(e, "source_task_id", None) else None,
                        "target_task_name": await self._task_repo.get_by_id(e.target_task_id).then(lambda t: t.name) if getattr(e, "target_task_id", None) else None,
                        "output_mapping": e.output_mapping
                    }
                    for e in skill.edges
                ]
            }
            # Simplified edge fetching to avoid async lambdas in list comps
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
            "last_execution_results": self._last_execution.get("results", {})
        }
        
        refine_result = await self._executor.execute_skill(refine_skill, context, refine_payload)
        
        # 3. Register the new skill
        new_skill_id = refine_result.get("skill_id")
        if not new_skill_id:
            logger.error("refine_skill did not return a new skill_id!")
            return self._last_execution.get("results", {})
            
        console.print(f"[bold green]✨ Refined skill built: {new_skill_id}[/bold green]")
        
        # 4. Execute the new skill using the initial payload from the last run
        initial_payload = self._last_execution.get("initial_payload", {})
        # Note: we might want to preserve the new feedback for the skill if it uses 'user_input'
        if "user_input" in intent_result:
            initial_payload["user_input"] = intent_result["user_input"]
            initial_payload["goal"] = intent_result["goal"]
            
        console.print("[bold green]▶ Executing refined skill...[/bold green]")
        plan = {"skill_ids": [new_skill_id]}
        results = await self._execute_plan(plan, context, initial_payload)
        
        self._present_results(results)
        await self._persist_objective(intent_result.get("user_input", "Feedback"), plan, results)
        
        self._last_execution = {
            "plan": plan,
            "initial_payload": initial_payload,
            "results": results
        }
        
        return results


    async def _seek_clarifications(
        self,
        intent_result: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, str]:
        """Check if the request needs clarification and ask the user.

        Uses the LLM to determine if any info is missing to fulfill the request.
        Returns a dict of question -> answer pairs.
        """
        clarifications: dict[str, str] = {}
        try:
            prompt = (
                f"The user wants: {intent_result.get('goal', '')}\n"
                f"Domain: {intent_result.get('domain', 'general')}\n"
                f"Entities: {intent_result.get('entities', [])}\n"
                f"Constraints: {intent_result.get('constraints', [])}\n\n"
                "Does this request require any external resources, API keys, "
                "credentials, or clarifications from the user that the agent "
                "cannot determine on its own? If yes, list up to 3 specific "
                "questions to ask. If no, return an empty list.\n\n"
                "Respond as JSON: {\"needs_clarification\": bool, \"questions\": [str]}"
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
                # Create a key from the question
                pref_key = question[:100].lower().replace(" ", "_").replace("?", "")
                await self._pref_repo.set(
                    key=pref_key,
                    value=answer,
                    domain=intent_result.get("domain", "general"),
                    source="clarification",
                )

        return clarifications

    async def _understand_intent(
        self,
        user_input: str,
        context: ExecutionContext,
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

    async def _decompose(
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

    async def _build_missing(
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

    async def _execute_plan(
        self,
        plan: dict[str, Any],
        context: ExecutionContext,
        initial_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run each skill via DAG executor, collect results."""
        results: dict[str, Any] = dict(initial_payload or {})
        skill_ids = plan.get("skill_ids", [])

        for skill_id in skill_ids:
            try:
                skill = await self._skill_registry.get(skill_id)
                skill_result = await self._executor.execute_skill(
                    skill, context, results
                )
                logger.info("Skill '%s' result keys: %s", skill_id, list(skill_result.keys()))
                results.update(skill_result)
            except (KeyError, ValueError) as e:
                logger.error("Failed to execute skill '%s': %s", skill_id, e)
            except Exception as e:
                logger.error("Unexpected error executing skill '%s': %s", skill_id, e)

        return results

    def _present_results(self, results: dict[str, Any]) -> None:
        """Format and display results via rich."""
        console.print("\n[bold green]✅ Results:[/bold green]")
        # Filter out internal keys like user_input, goal, entities etc.
        display_results = {
            k: v for k, v in results.items()
            if k not in ("user_input", "goal", "entities", "constraints", "domain",
                         "past_objectives", "file_paths", "sub_objectives",
                         "plan", "build_items", "skill_ids", "execution_plan")
        }
        if not display_results:
            console.print("[dim]No results produced.[/dim]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        for key, value in display_results.items():
            table.add_row(str(key), str(value)[:200])

        console.print(table)

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
