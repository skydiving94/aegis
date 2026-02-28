import asyncio
import os
import sys
from dotenv import load_dotenv

from main import create_agent
from helpers.privacy.base_approval import AbstractApprovalGate


class AutoApprovalGate(AbstractApprovalGate):
    """Automatically approves all tasks for non-interactive E2E testing."""
    def approve_file_read(self, path: str) -> bool: return True
    def approve_file_write(self, path: str) -> bool: return True
    def approve_pip_install(self, package: str) -> bool: return True
    def approve_task_output(self, task_name: str, result) -> bool: return True
    def get_approved_paths(self) -> list[str]: return []
    
    def approve_task_execution(self, task_name: str, description: str, risk_level) -> bool:
        print(f"\n[AUTO-APPROVED] Task: {task_name} (Risk: {risk_level})")
        return True

    def seek_clarification(self, question: str, context: dict | None = None) -> str:
        """In E2E mode, return a generic answer for any clarification."""
        print(f"\n[AUTO-CLARIFICATION] Q: {question}")
        return "(no additional info available in automated testing)"


async def run_e2e():
    # Load env — DATABASE_URL must be set (PostgreSQL required)
    load_dotenv(".env")
    
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL not set. Run: docker-compose up -d && source .env")
        sys.exit(1)
    
    config = {k: v for k, v in os.environ.items()}
    
    # Create the agent using main setup
    agent = await create_agent(config)
    
    # Override approval gate to bypass interactivity
    agent._approval_gate = AutoApprovalGate()
    
    print("=" * 60)
    print("🤖 Agent E2E Auto-Run (PostgreSQL)")
    print("=" * 60)
    
    questions = [
        "How is the weather in 27519?",
        "What is AAPL's price today?",
    ]
    
    all_passed = True
    for q in questions:
        print(f"\n\n>>> EXECUTING QUERY: '{q}'\n" + "-"*40)
        try:
            result = await agent.run(q)
            display = {
                k: v for k, v in result.items()
                if k not in ("user_input", "goal", "entities", "constraints", "domain",
                             "past_objectives", "file_paths", "sub_objectives",
                             "plan", "build_items", "skill_ids", "execution_plan",
                             "user_preferences")
            }
            if display:
                print(f"\n✅ SUCCESS for '{q}':")
                for k, v in display.items():
                    print(f"  {k}: {str(v)[:300]}")
            else:
                print(f"\n⚠️  EMPTY RESULT for '{q}'")
                all_passed = False
        except Exception as e:
            print(f"\n❌ FAILED for '{q}':\n{e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_e2e())
