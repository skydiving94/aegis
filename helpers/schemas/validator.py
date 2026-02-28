"""JSON schema validation for tasks, skills, and toolkits."""

from __future__ import annotations

from typing import Any
import jsonschema

from core.data.fs.repository.schema_repository import SchemaRepository


class SchemaValidator:
    """Validates data dicts against JSON schemas for tasks, skills, and toolkits.
    
    This class leverages a SchemaRepository to load schemas instead of interacting
    with the filesystem directly.
    """

    def __init__(self, schema_repo: SchemaRepository) -> None:
        """Initialize with a schema repository instance."""
        self._schema_repo = schema_repo

    def validate_task(self, data: dict[str, Any]) -> list[str]:
        """Validate against task_schema.json. 
        
        Returns a list of error messages.
        
        Examples:
            >>> validator = SchemaValidator(SchemaRepository())
            >>> errors = validator.validate_task({"invalid": "data"})
            >>> len(errors) > 0
            True
        """
        return self._validate("task_schema.json", data)

    def validate_skill(self, data: dict[str, Any]) -> list[str]:
        """Validate against skill_schema.json."""
        return self._validate("skill_schema.json", data)

    def validate_toolkit(self, data: dict[str, Any]) -> list[str]:
        """Validate against toolkit_schema.json."""
        return self._validate("toolkit_schema.json", data)

    def _validate(self, schema_name: str, data: dict[str, Any]) -> list[str]:
        """Run jsonschema validation and collect all errors."""
        schema = self._schema_repo.load(schema_name)
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(data)]
