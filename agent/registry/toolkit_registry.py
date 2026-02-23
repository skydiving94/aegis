"""In-memory toolkit registry wrapping the toolkit repository."""

from __future__ import annotations

from agent.models.toolkit import ToolkitModule
from agent.store.toolkit_repository import ToolkitRepository


class ToolkitRegistry:
    """Caching wrapper around ToolkitRepository."""

    def __init__(self, repo: ToolkitRepository) -> None:
        self._repo = repo
        self._cache: dict[str, ToolkitModule] = {}

    async def register(self, toolkit: ToolkitModule) -> None:
        """Persist and cache a toolkit."""
        await self._repo.save(toolkit)
        self._cache[toolkit.id] = toolkit

    async def get(self, toolkit_id: str) -> ToolkitModule:
        """Get a toolkit by ID (cache-first)."""
        if toolkit_id in self._cache:
            return self._cache[toolkit_id]
        toolkit = await self._repo.get_by_id(toolkit_id)
        if toolkit is None:
            raise KeyError(f"Toolkit '{toolkit_id}' not found")
        self._cache[toolkit_id] = toolkit
        return toolkit

    async def list_available(self) -> list[ToolkitModule]:
        """List all available toolkits."""
        return await self._repo.list_all()

    def get_module_path(self, toolkit_id: str) -> str:
        """Return filesystem path for a toolkit. Must be cached."""
        if toolkit_id in self._cache:
            return self._cache[toolkit_id].module_path
        raise KeyError(f"Toolkit '{toolkit_id}' not in cache. Call get() first.")
