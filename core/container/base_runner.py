"""Abstract base for sandboxed code execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class SandboxResult(BaseModel):
    """Result of running code in a sandbox."""

    outputs: dict[str, Any] = {}
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    duration_ms: int = 0


class AbstractSandboxRunner(ABC):
    """ABC for sandboxed code execution."""

    @abstractmethod
    def run(
        self,
        code: str,
        inputs: dict[str, Any],
        toolkit_refs: list[str],
        timeout: int = 30,
    ) -> SandboxResult:
        """Execute code in an isolated environment.

        Args:
            code: Python source code to execute.
            inputs: Input data to inject into the code's namespace.
            toolkit_refs: Toolkit IDs whose module paths should be on PYTHONPATH.
            timeout: Maximum execution time in seconds.

        Returns:
            SandboxResult with outputs, stdout/stderr, and return code.
        """
        ...
