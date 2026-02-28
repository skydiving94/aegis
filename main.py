"""Entry point: parses CLI args, loads config, wires dependencies, starts REPL."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv  # type: ignore[import-untyped]
from rich.console import Console

from agent import Agent
from helpers.executor.dag_executor import DAGExecutor
from helpers.llm.gemini_client import GeminiClient
from helpers.privacy.cli_approval import CLIApprovalGate
from helpers.privacy.spacy_scrubber import SpaCyNERScrubber
from registry.skill_registry import SkillRegistry
from registry.toolkit_registry import ToolkitRegistry
from core.container.subprocess_runner import SubprocessRunner
from seeds.seed_loader import SeedLoader
from core.data.db.repository.skill_repository import SkillRepository
from core.data.db.repository.task_repository import TaskRepository
from core.data.db.repository.user_preferences import UserPreferenceRepository
from core.data.db.repository.toolkit_repository import ToolkitRepository

console = Console()
logger = logging.getLogger(__name__)


async def create_agent(config: dict[str, str]) -> Agent:
    """Dependency injection: construct all ABCs with concrete implementations."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from core.data.db.entities.base import Base
    from sqlalchemy import text

    # Database — PostgreSQL required
    db_url = config.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Set it in .env, e.g.: DATABASE_URL=postgresql+asyncpg://agent:password@localhost:5432/agent_db"
        )
    engine = create_async_engine(db_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS framework"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vector_store"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Repositories
    task_repo = TaskRepository(session_factory)
    skill_repo = SkillRepository(session_factory)
    toolkit_repo = ToolkitRepository(session_factory)
    pref_repo = UserPreferenceRepository(session_factory)

    # Registries
    skill_registry = SkillRegistry(skill_repo)
    toolkit_registry = ToolkitRegistry(toolkit_repo)

    # LLM client — build model_config from env vars
    model_config = {
        k: v for k, v in config.items() if k.startswith("LLM_MODEL_")
    }
    llm_client = GeminiClient(
        api_key=config.get("GEMINI_API_KEY", ""),
        model_config=model_config,
    )

    # Sandbox
    approval_gate = CLIApprovalGate()
    sandbox = SubprocessRunner(
        toolkit_registry=toolkit_registry,
        approved_paths=approval_gate.get_approved_paths(),
    )

    # Privacy
    scrubber = SpaCyNERScrubber()

    # Seeds
    seed_loader = SeedLoader()

    # Executor
    executor = DAGExecutor(task_repo=task_repo, toolkit_registry=toolkit_registry)

    return Agent(
        executor=executor,
        skill_registry=skill_registry,
        toolkit_registry=toolkit_registry,
        llm_client=llm_client,
        sandbox=sandbox,
        approval_gate=approval_gate,
        scrubber=scrubber,
        seed_loader=seed_loader,
        task_repo=task_repo,
        config=config,
        pref_repo=pref_repo,
    )


async def run_repl(agent: Agent) -> None:
    """Interactive REPL loop."""
    console.print("[bold cyan]🤖 Autonomous Agent v0.1.0[/bold cyan]")
    console.print("Type your request, or 'quit' to exit.\n")

    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        if not user_input.strip():
            continue

        if user_input.strip().lower() == "/context":
            agent.show_recent_context()
            continue

        try:
            await agent.run(user_input)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.exception("Agent error")


def main() -> None:
    """Parse CLI args, load config, initialize DB, run REPL."""
    parser = argparse.ArgumentParser(description="Autonomous Task-Solving Agent")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load environment
    load_dotenv(args.env)
    config = {k: v for k, v in os.environ.items()}

    # Create agent and run
    async def _start() -> None:
        agent = await create_agent(config)
        await run_repl(agent)

    asyncio.run(_start())


if __name__ == "__main__":
    main()
