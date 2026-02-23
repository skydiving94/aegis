"""Subprocess-based sandboxed code runner."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from typing import Any

from agent.sandbox.base_runner import AbstractSandboxRunner, SandboxResult


class SubprocessRunner(AbstractSandboxRunner):
    """Runs Python code in an isolated subprocess.

    Limitation: process-level isolation only. No filesystem restrictions
    beyond pre-approved paths. v2 should use Docker for true isolation.
    """

    def __init__(
        self,
        toolkit_registry: Any,  # ToolkitRegistry — avoid circular import
        approved_paths: list[str] | None = None,
    ) -> None:
        self._toolkit_registry = toolkit_registry
        self._approved_paths = approved_paths or []

    def run(
        self,
        code: str,
        inputs: dict[str, Any],
        toolkit_refs: list[str],
        timeout: int = 30,
    ) -> SandboxResult:
        """Execute code in a subprocess with toolkit PYTHONPATH injection."""
        start = time.monotonic()
        tmpdir = self._setup_tempdir(code, inputs)
        env = self._build_env(toolkit_refs)

        try:
            result = subprocess.run(
                ["python", os.path.join(tmpdir, "task_impl.py")],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=tmpdir,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            outputs = self._parse_output(result.stdout)

            return SandboxResult(
                outputs=outputs,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            return SandboxResult(
                outputs={},
                stdout="",
                stderr=f"Task timed out after {timeout}s",
                return_code=-1,
                duration_ms=duration_ms,
            )

    def _setup_tempdir(self, code: str, inputs: dict[str, Any]) -> str:
        """Create temp directory with task code and serialized inputs."""
        tmpdir = tempfile.mkdtemp(prefix="agent_sandbox_")

        # Write the wrapper that loads inputs, runs the task code, and prints JSON output
        wrapper = f'''
import json
import sys

# Load inputs
with open("inputs.json", "r") as f:
    inputs = json.load(f)

# Make inputs available as global variables
globals().update(inputs)

# --- Task code begins ---
{code}
# --- Task code ends ---

# Auto-invoke execute() if defined but outputs not set
if "outputs" not in globals() and "execute" in globals() and callable(execute):
    outputs = execute(inputs)

# Collect outputs — the task should define an `outputs` dict
if "outputs" in dir() or "outputs" in globals():
    print("__AGENT_OUTPUT__" + json.dumps(outputs))
'''
        with open(os.path.join(tmpdir, "task_impl.py"), "w") as f:
            f.write(wrapper)

        with open(os.path.join(tmpdir, "inputs.json"), "w") as f:
            json.dump(inputs, f)

        return tmpdir

    def _build_env(self, toolkit_refs: list[str]) -> dict[str, str]:
        """Construct environment with PYTHONPATH including only depended toolkits."""
        env = os.environ.copy()
        paths: list[str] = []

        for ref in toolkit_refs:
            try:
                module_path = self._toolkit_registry.get_module_path(ref)
                parent_dir = os.path.dirname(module_path)
                if parent_dir not in paths:
                    paths.append(parent_dir)
            except (KeyError, AttributeError) as e:
                print(f"[DEBUG] _build_env toolkit exception for {ref}: {e}")
                pass  # toolkit not found — will fail at import time in sandbox

        # Inject project root so 'agent.store...' is importable by internal toolkits
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if project_root not in paths:
            paths.append(project_root)

        if paths:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = os.pathsep.join(paths) + (
                os.pathsep + existing if existing else ""
            )

        return env

    def _parse_output(self, stdout: str) -> dict[str, Any]:
        """Parse the __AGENT_OUTPUT__ marker from stdout."""
        marker = "__AGENT_OUTPUT__"
        for line in stdout.splitlines():
            if line.startswith(marker):
                try:
                    result: dict[str, Any] = json.loads(line[len(marker) :])
                    return result
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse sandbox output JSON: %s", e)
                    return {}
        print(f"[DEBUG NO MARKER] raw stdout was: {stdout}")
        return {}
