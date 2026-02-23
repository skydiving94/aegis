"""Skill model: DAG of task node references."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from agent.models.edge import Edge


class SkillNode(BaseModel):
    """A reference to a TaskDefinition within a skill DAG."""

    node_id: str
    task_definition_id: str
    config_overrides: dict[str, object] = Field(default_factory=dict)


class Skill(BaseModel):
    """A reusable skill defined as a DAG of SkillNodes connected by Edges."""

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    nodes: list[SkillNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    is_meta: bool = False
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
