"""In-memory skill registry wrapping the skill repository."""

from __future__ import annotations

from models.skill import Skill
from core.data.db.repository.skill_repository import SkillRepository


class SkillRegistry:
    """Caching wrapper around SkillRepository for fast lookups."""

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo
        self._cache: dict[str, Skill] = {}

    async def register(self, skill: Skill) -> None:
        """Validate and persist a skill."""
        await self._repo.save(skill)
        self._cache[skill.id] = skill

    async def search(
        self, tags: list[str], min_confidence: float = 0.8
    ) -> list[dict[str, object]]:
        """Search skills by tag overlap, returning scored results."""
        skills = await self._repo.search_by_tags(tags)
        results: list[dict[str, object]] = []
        for s in skills:
            if not tags:
                continue
            overlap = len(set(tags) & set(s.tags))
            confidence = overlap / len(tags)
            if confidence >= min_confidence:
                results.append(
                    {"skill_id": s.id, "confidence": confidence, "name": s.name}
                )
        return sorted(results, key=lambda x: x["confidence"], reverse=True)  # type: ignore[return-value]

    async def get(self, skill_id: str) -> Skill:
        """Get a skill by ID (cache-first)."""
        if skill_id in self._cache:
            return self._cache[skill_id]
        skill = await self._repo.get_by_id(skill_id)
        if skill is None:
            raise KeyError(f"Skill '{skill_id}' not found")
        self._cache[skill_id] = skill
        return skill

    async def refresh_cache(self) -> None:
        """Reload all skills from DB into cache."""
        all_skills = await self._repo.list_all()
        self._cache = {s.id: s for s in all_skills}
