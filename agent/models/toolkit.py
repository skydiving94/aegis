"""Toolkit module model."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ToolkitModule(BaseModel):
    """A reusable Python module that tasks can depend on via toolkit_refs."""

    id: str
    name: str
    description: str
    module_path: str  # filesystem path to .py file
    public_api: list[dict[str, str]] = Field(default_factory=list)  # [{name, description, params, returns}]
    dependencies: list[str] = Field(default_factory=list)  # pip packages
    requires_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
