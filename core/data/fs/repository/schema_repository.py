"""Repository for loading JSON schemas from disk."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.data.fs.repository.base_fs_repository import AbstractFileRepository

_RESOURCES_DIR = Path(__file__).parent.parent.parent.parent.parent / "resources"

class SchemaRepository(AbstractFileRepository):
    """Repository implementation for loading JSON schemas from resources/schemas."""
    
    @lru_cache(maxsize=8)
    def load(self, name: str) -> dict[str, Any]:
        """Load and cache a JSON schema from disk.
        
        Examples:
            >>> repo = SchemaRepository()
            >>> schema = repo.load("task_schema.json")
            >>> isinstance(schema, dict)
            True
        """
        schema_path = _RESOURCES_DIR / "schemas" / name
        with open(schema_path, "r", encoding="utf-8") as f:
            result: dict[str, Any] = json.load(f)
            return result

    def save(self, path: str, data: Any) -> None:
        """Save operates statically for schemas, typically unsupported or rare."""
        raise NotImplementedError("Saving schemas is not supported via this repository.")
