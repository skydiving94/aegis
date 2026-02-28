"""Internal toolkit: DB access for meta-skill task nodes.

This module is designed to be importable in a subprocess sandbox.
When imported, it connects to the database using DATABASE_URL from
the environment. All functions are synchronous (subprocess constraint).

Registered as an internal toolkit in ToolkitRegistry so meta-skills
can reference it via toolkit_refs, and SubprocessRunner adds its
parent directory to PYTHONPATH.
"""

from __future__ import annotations

import json
import os
from typing import Any


# ── Lazy DB connection ──────────────────────────────────────

_engine = None
_Session = None


def _get_session() -> Any:
    """Lazily create a sync SQLAlchemy session from DATABASE_URL."""
    global _engine, _Session
    if _Session is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL not set. Required for db_access toolkit."
            )
        # Convert async driver to sync for subprocess use
        sync_url = db_url.replace("+asyncpg", "+psycopg2")
        _engine = create_engine(sync_url, echo=False)
        _Session = sessionmaker(bind=_engine)
    return _Session()


# ── Public API ──────────────────────────────────────────────


def search_objectives(
    domain: str = "",
    tags: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search for previously solved objectives by domain and tags.

    Returns a list of dicts with keys: skill_id, description, tags.
    On cold-start (empty DB or no matches), returns [].
    """
    tags = tags or []
    try:
        session = _get_session()
        from sqlalchemy import text

        # Simple tag-based search in skills table
        results: list[dict[str, Any]] = []
        if tags:
            tag_pattern = "%" + "%".join(tags[:3]) + "%"
            rows = session.execute(
                text(
                    "SELECT id, name, description, tags FROM framework.skills "
                    "WHERE tags LIKE :pattern LIMIT :limit"
                ),
                {"pattern": tag_pattern, "limit": limit},
            ).fetchall()
        else:
            rows = session.execute(
                text("SELECT id, name, description, tags FROM framework.skills LIMIT :limit"),
                {"limit": limit},
            ).fetchall()

        for row in rows:
            tags_val = row[3] if row[3] else "[]"
            if isinstance(tags_val, str):
                try:
                    parsed_tags = json.loads(tags_val)
                except json.JSONDecodeError:
                    parsed_tags = []
            else:
                parsed_tags = tags_val
            results.append(
                {
                    "skill_id": row[0],
                    "description": row[2] or row[1],
                    "tags": parsed_tags,
                }
            )
        session.close()
        return results
    except Exception:
        return []


def search_skills_by_tags(
    tags: list[str], min_confidence: float = 0.0
) -> list[dict[str, Any]]:
    """Search for existing skills by tag overlap AND name/description keyword match.

    Combines tag overlap (50%) with keyword matching on name+description (50%).
    Returns list of dicts with keys: skill_id, name, description, confidence.
    """
    try:
        session = _get_session()
        from sqlalchemy import text

        rows = session.execute(
            text("SELECT id, name, description, tags FROM framework.skills WHERE is_meta = false")
        ).fetchall()
        session.close()

        results = []
        tag_set = set(t.lower().strip() for t in tags if t and t.strip())
        # Build keyword set from tags for name/description matching
        keywords = set()
        for t in tags:
            for word in t.lower().replace("_", " ").replace("-", " ").split():
                if len(word) > 2:
                    keywords.add(word)

        for row in rows:
            skill_id, skill_name, skill_desc, skill_tags_raw = row
            # Parse tags
            skill_tags = skill_tags_raw if isinstance(skill_tags_raw, list) else []
            if isinstance(skill_tags_raw, str):
                try:
                    skill_tags = json.loads(skill_tags_raw)
                except json.JSONDecodeError:
                    skill_tags = []
            skill_tag_set = set(t.lower().strip() for t in skill_tags if isinstance(t, str))

            # Tag overlap score (50%)
            if tag_set and skill_tag_set:
                tag_score = len(tag_set & skill_tag_set) / max(len(tag_set), 1)
            else:
                tag_score = 0.0

            # Keyword match on name+description (50%)
            searchable = (skill_name or "").lower() + " " + (skill_desc or "").lower()
            if keywords:
                matched_kw = sum(1 for kw in keywords if kw in searchable)
                kw_score = matched_kw / len(keywords)
            else:
                kw_score = 0.0

            confidence = round(0.5 * tag_score + 0.5 * kw_score, 2)
            if confidence >= min_confidence:
                results.append({
                    "skill_id": skill_id,
                    "name": skill_name,
                    "description": skill_desc or "",
                    "confidence": confidence,
                })
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results
    except Exception:
        return []


def _ensure_parsed(val: Any, default: Any = None) -> Any:
    """Helper to ensure JSON strings from LLM are parsed to lists/dicts."""
    if val is None:
        return default if default is not None else []
    if isinstance(val, str):
        import json
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return default if default is not None else []
    return val

def save_task(task_data: dict[str, Any]) -> str:
    """Save a task definition to the database. Returns task ID."""
    try:
        session = _get_session()
        from core.data.db.entities.task import Task as TaskORM

        task_id = task_data.get("id", "")
        model = TaskORM(
            id=task_id,
            name=task_data.get("name", ""),
            description=task_data.get("description", ""),
            task_type=task_data.get("task_type", "python"),
            version=task_data.get("version", 1),
            tags=_ensure_parsed(task_data.get("tags", [])),
            risk_level=task_data.get("risk_level", "low"),
            code=task_data.get("code", ""),
            test_code=task_data.get("test_code", ""),
            prompt_template=task_data.get("prompt_template", ""),
            system_instruction=task_data.get("system_instruction", ""),
            context_budget=task_data.get("context_budget", 32000),
            inputs=_ensure_parsed(task_data.get("inputs", [])),
            outputs=_ensure_parsed(task_data.get("outputs", [])),
            preconditions=_ensure_parsed(task_data.get("preconditions", [])),
            toolkit_refs=_ensure_parsed(task_data.get("toolkit_refs", [])),
        )
        session.merge(model)
        session.commit()
        session.close()
        return str(task_id)
    except Exception as e:
        raise RuntimeError(f"Failed to save task: {e}") from e


def save_skill(skill_data: dict[str, Any]) -> str:
    """Save a skill definition to the database. Returns skill ID."""
    try:
        session = _get_session()
        from core.data.db.entities.skill import Skill as SkillORM

        skill_id = skill_data.get("id", "")
        model = SkillORM(
            id=skill_id,
            name=skill_data.get("name", ""),
            description=skill_data.get("description", ""),
            version=skill_data.get("version", 1),
            tags=_ensure_parsed(skill_data.get("tags", [])),
            is_meta=skill_data.get("is_meta", False),
            nodes=_ensure_parsed(skill_data.get("nodes", [])),
            edges=_ensure_parsed(skill_data.get("edges", [])),
        )
        session.merge(model)
        session.commit()
        session.close()
        return str(skill_id)
    except Exception as e:
        raise RuntimeError(f"Failed to save skill: {e}") from e


def save_toolkit(toolkit_data: dict[str, Any]) -> str:
    """Save a toolkit definition to the database. Returns toolkit ID."""
    try:
        session = _get_session()
        from core.data.db.entities.toolkit import Toolkit as ToolkitORM

        toolkit_id = toolkit_data.get("id", "")
        model = ToolkitORM(
            id=toolkit_id,
            name=toolkit_data.get("name", ""),
            description=toolkit_data.get("description", ""),
            module_path=toolkit_data.get("module_path", ""),
            version=toolkit_data.get("version", 1),
            public_api=_ensure_parsed(toolkit_data.get("public_api", [])),
            dependencies=_ensure_parsed(toolkit_data.get("dependencies", [])),
            requires_approval=toolkit_data.get("requires_approval", False),
        )
        session.merge(model)
        session.commit()
        session.close()
        return str(toolkit_id)
    except Exception as e:
        raise RuntimeError(f"Failed to save toolkit: {e}") from e
