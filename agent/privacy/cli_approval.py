"""CLI-based approval gate using rich prompts."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm

from agent.models.enums import RiskLevel
from agent.models.task import TaskResult
from agent.privacy.base_approval import AbstractApprovalGate

console = Console()


class CLIApprovalGate(AbstractApprovalGate):
    """Human-in-the-loop approval via CLI prompts.

    Caches file path approvals for the current session.
    Checks dependency registry before prompting for pip installs.
    """

    def __init__(self, dependency_registry: dict[str, bool] | None = None) -> None:
        self._approved_read: set[str] = set()
        self._approved_write: set[str] = set()
        self._dependency_registry = dependency_registry or {}

    def approve_file_read(self, path: str) -> bool:
        """Prompt user to approve reading a file."""
        if path in self._approved_read:
            return True
        approved = Confirm.ask(
            f"[yellow]Allow reading file:[/yellow] {path}?", default=True
        )
        if approved:
            self._approved_read.add(path)
        return approved

    def approve_file_write(self, path: str) -> bool:
        """Prompt user to approve writing a file."""
        if path in self._approved_write:
            return True
        approved = Confirm.ask(
            f"[red]Allow writing file (may overwrite):[/red] {path}?", default=False
        )
        if approved:
            self._approved_write.add(path)
        return approved

    def approve_pip_install(self, package: str) -> bool:
        """Check registry first; if not found, prompt user."""
        if self._dependency_registry.get(package):
            return True
        approved = Confirm.ask(
            f"[yellow]Allow pip install:[/yellow] {package}?", default=False
        )
        if approved:
            self._dependency_registry[package] = True
        return approved

    def approve_task_execution(
        self, task_name: str, description: str, risk_level: RiskLevel
    ) -> bool:
        """Prompt user for HIGH/CRITICAL task execution approval."""
        color = "red" if risk_level == RiskLevel.CRITICAL else "yellow"
        console.print(f"\n[{color}]⚠ Task requires approval[/{color}]")
        console.print(f"  Task: [bold]{task_name}[/bold]")
        console.print(f"  Description: {description}")
        console.print(f"  Risk Level: [{color}]{risk_level.value.upper()}[/{color}]")
        return Confirm.ask("  Approve execution?", default=False)

    def approve_task_output(self, task_name: str, result: TaskResult) -> bool:
        """For CRITICAL tasks, show output before propagation."""
        console.print(f"\n[red]⚠ CRITICAL task output requires review[/red]")
        console.print(f"  Task: [bold]{task_name}[/bold]")
        console.print(f"  Status: {result.status.value}")
        # Show truncated output preview
        output_preview = str(result.outputs)[:500]
        console.print(f"  Output preview: {output_preview}")
        if len(str(result.outputs)) > 500:
            console.print("  [dim](...truncated)[/dim]")
        return Confirm.ask("  Approve propagating this output?", default=False)

    def seek_clarification(
        self, question: str, context: dict | None = None
    ) -> str:
        """Ask the user a clarifying question via CLI."""
        console.print(f"\n[bold cyan]❓ Agent needs clarification:[/bold cyan]")
        if context:
            for k, v in context.items():
                console.print(f"  [dim]{k}:[/dim] {v}")
        answer = console.input(f"  [bold]{question}[/bold]\n  > ")
        return answer.strip()

    def get_approved_paths(self) -> list[str]:
        """Return all paths approved this session (read + write)."""
        return sorted(self._approved_read | self._approved_write)
