"""JSON schema validation for tasks, skills, and toolkits."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import jsonschema


_SCHEMA_DIR = Path(__file__).parent


class SchemaValidator:
    """Validates data dicts against JSON schemas for tasks, skills, and toolkits."""

    def validate_task(self, data: dict[str, object]) -> list[str]:
        """Validate against task_schema.json. Returns list of error messages."""
        return self._validate("task_schema.json", data)

    def validate_skill(self, data: dict[str, object]) -> list[str]:
        """Validate against skill_schema.json."""
        return self._validate("skill_schema.json", data)

    def validate_toolkit(self, data: dict[str, object]) -> list[str]:
        """Validate against toolkit_schema.json."""
        return self._validate("toolkit_schema.json", data)

    def _validate(self, schema_name: str, data: dict[str, object]) -> list[str]:
        """Run jsonschema validation and collect all errors."""
        schema = self._load_schema(schema_name)
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(data)]

    @staticmethod
    @lru_cache(maxsize=8)
    def _load_schema(name: str) -> dict[str, object]:
        """Load and cache a JSON schema from disk."""
        schema_path = _SCHEMA_DIR / name
        with open(schema_path) as f:
            result: dict[str, object] = json.load(f)
            return result
