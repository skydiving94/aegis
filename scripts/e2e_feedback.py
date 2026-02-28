"""
E2E Script to test the feedback loop / refinement pipeline.
"""
import asyncio
import os
from dotenv import load_dotenv
from agent import Agent
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.data.db.repository.task_repository import TaskRepository
from core.data.db.repository.skill_repository import SkillRepository
from core.data.db.repository.toolkit_repository import ToolkitRepository
from core.data.db.repository.user_preferences import UserPreferenceRepository
from registry.skill_registry import SkillRegistry
from registry.toolkit_registry import ToolkitRegistry
from helpers.llm.gemini_client import GeminiClient
from core.container.subprocess_runner import SubprocessRunner
from helpers.privacy.cli_approval import CLIApprovalGate
from helpers.privacy.spacy_scrubber import SpaCyNERScrubber
from seeds.seed_loader import SeedLoader
from helpers.executor.dag_executor import DAGExecutor

load_dotenv('.env')

class AutoGate(CLIApprovalGate):
    def seek_clarification(self, q, c): return '(automated test)'
    def request_file_approval(self, op, path, r): return True
    def request_pip_install_approval(self, pkgs): return True
    def request_task_execution_approval(self, t): return True
    def confirm_output(self, task, out): return out

async def run():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    sf = async_sessionmaker(engine, expire_on_commit=False)
    
    agent = Agent(
        executor=DAGExecutor(TaskRepository(sf), ToolkitRegistry(ToolkitRepository(sf))),
        skill_registry=SkillRegistry(SkillRepository(sf)),
        toolkit_registry=ToolkitRegistry(ToolkitRepository(sf)),
        llm_client=GeminiClient(api_key=os.environ['GEMINI_API_KEY'], model_config={"model_name": "gemini-2.5-flash"}),
        sandbox=SubprocessRunner(toolkit_registry=ToolkitRegistry(ToolkitRepository(sf)), approved_paths=['/']),
        approval_gate=AutoGate(),
        scrubber=SpaCyNERScrubber(),
        seed_loader=SeedLoader(),
        task_repo=TaskRepository(sf),
        config={},
        pref_repo=UserPreferenceRepository(sf)
    )
    
    await agent.initialize()
    
    print('\n>>> FIRST QUERY (will fail looking up AAPL price)')
    results1 = await agent.run("What is AAPL's price today?", ['agent/seeds/tasks/analyze_objective.json'])
    
    print('\n>>> FEEDBACK QUERY (should trigger refinement loop)')
    results2 = await agent.run("The API request failed with a connection error. Please rewrite the python code to just return a simulated JSON dictionary with a fake stock price of 150.0 instead of calling the API.", ['agent/seeds/tasks/analyze_objective.json'])
    
    print('== FINAL RESULTS ==')
    for k, v in results2.items():
        if k not in ['entities', 'past_objectives', 'plan']:
            print(f'{k}: {v}')
            
    await engine.dispose()

asyncio.run(run())
