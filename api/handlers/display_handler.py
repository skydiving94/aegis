"""Handler for formatting and presenting agent execution results to the user."""

import logging
from typing import Any

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()

class DisplayHandler:
    """Formats and displays results from the agent execution."""

    def present_results(self, results: dict[str, Any]) -> None:
        """Format and display results via rich."""
        console.print("\n[bold green]✅ Results:[/bold green]")

        hidden_keys = {
            "user_input", "goal", "entities", "constraints", "domain",
            "past_objectives", "file_paths", "sub_objectives",
            "plan", "build_items", "skill_ids", "execution_plan",
            "intent_type", "clarifications", "user_preferences"
        }
        
        # Hide individual clarification questions from the results
        clarifications = results.get("clarifications", {})
        if isinstance(clarifications, dict):
            hidden_keys.update(clarifications.keys())

        # Filter out internal keys like user_input, goal, entities etc.
        display_results = {
            k: v for k, v in results.items()
            if k not in hidden_keys
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

    def show_recent_context(self, execution_history: list[dict[str, Any]], limit: int = 10) -> None:
        """Display the recent execution context (hidden inputs/outputs) to the user."""
        if not execution_history:
            console.print("[dim]No recent context available.[/dim]")
            return

        console.print(f"\n[bold cyan]📖 Recent Context (last {min(limit, len(execution_history))} runs)[/bold cyan]")
        
        history_to_show = execution_history[-limit:]
        
        for i, execution in enumerate(reversed(history_to_show), 1):
            results = execution.get("results", {})
            
            # Extract internal keys we normally hide
            context_keys = {"intent_type", "clarifications", "user_preferences"}
            clarifications = results.get("clarifications", {})
            if isinstance(clarifications, dict):
                context_keys.update(clarifications.keys())
                
            display_context = {
                k: v for k, v in results.items() 
                if k in context_keys
            }
            
            if not display_context:
                continue

            table = Table(show_header=True, header_style="bold magenta", title=f"Run -{i}")
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="white")

            for key, value in display_context.items():
                table.add_row(str(key), str(value)[:200])

            console.print(table)
