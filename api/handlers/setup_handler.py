"""Handler for agent initialization and startup logic."""

import logging
import os
from collections.abc import Awaitable

from core.data.db.repository.task_repository import TaskRepository
from registry.skill_registry import SkillRegistry
from registry.toolkit_registry import ToolkitRegistry
from seeds.seed_loader import SeedLoader

logger = logging.getLogger(__name__)


class SetupHandler:
    """Handles initialization of seed data and toolkits."""

    def __init__(
        self,
        seed_loader: SeedLoader,
        task_repo: TaskRepository,
        skill_registry: SkillRegistry,
        toolkit_registry: ToolkitRegistry,
    ) -> None:
        self._seed_loader = seed_loader
        self._task_repo = task_repo
        self._skill_registry = skill_registry
        self._toolkit_registry = toolkit_registry
        self._initialized = False

    async def initialize(self) -> None:
        """Register internal toolkits, seed tasks, and seed skills."""
        if self._initialized:
            return

        # Step 1: Register internal toolkits
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

        # Step 4: Eagerly load all toolkits
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
        from models.toolkit import ToolkitModule

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        internal_dir = os.path.join(repo_root, "internal_toolkits")

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
