"""Internal toolkit: schema validation for meta-skill task nodes.

This module is designed to be importable in a subprocess sandbox.
All functions are synchronous and self-contained.

Registered as an internal toolkit in ToolkitRegistry so meta-skills
can reference it via toolkit_refs.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _load_schema(schema_name: str) -> dict[str, Any]:
    """Load a schema JSON file relative to the agent package."""
    # Try multiple paths to find the schemas directory
    possible_bases = [
        os.path.join(os.path.dirname(__file__), "..", "schemas"),
        os.path.join(os.environ.get("AGENT_ROOT", ""), "agent", "schemas"),
    ]
    for base in possible_bases:
        path = os.path.join(base, schema_name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise FileNotFoundError(f"Schema '{schema_name}' not found")


def validate_task_schema(data: dict[str, Any]) -> list[str]:
    """Validate task data against task_schema.json."""
    try:
        from jsonschema import validate, ValidationError
        schema = _load_schema("task_schema.json")
        validate(instance=data, schema=schema)
        return []
    except ValidationError as e:
        return [str(e.message)]
    except ImportError:
        return ["jsonschema not available"]
    except FileNotFoundError as e:
        return [str(e)]


def validate_skill_schema(data: dict[str, Any]) -> list[str]:
    """Validate skill data against skill_schema.json."""
    try:
        from jsonschema import validate, ValidationError
        schema = _load_schema("skill_schema.json")
        validate(instance=data, schema=schema)
        return []
    except ValidationError as e:
        return [str(e.message)]
    except ImportError:
        return ["jsonschema not available"]
    except FileNotFoundError as e:
        return [str(e)]


def validate_toolkit_schema(data: dict[str, Any]) -> list[str]:
    """Validate toolkit data against toolkit_schema.json."""
    try:
        from jsonschema import validate, ValidationError
        schema = _load_schema("toolkit_schema.json")
        validate(instance=data, schema=schema)
        return []
    except ValidationError as e:
        return [str(e.message)]
    except ImportError:
        return ["jsonschema not available"]
    except FileNotFoundError as e:
        return [str(e)]
