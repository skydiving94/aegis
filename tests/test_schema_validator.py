"""Tests for JSON schema validation."""

import pytest

from helpers.schemas.validator import SchemaValidator


from resources.schemas import __file__ as schemas_init
from core.data.fs.repository.schema_repository import SchemaRepository

# Helper to provide a real schema repository pointing to the resources/schemas dir
@pytest.fixture
def schema_repo():
    return SchemaRepository()

@pytest.fixture
def validator(schema_repo) -> SchemaValidator:
    return SchemaValidator(schema_repo)


class TestTaskSchemaValidation:
    def test_valid_python_task(self, validator: SchemaValidator) -> None:
        data = {
            "name": "parse_csv",
            "description": "Parse a CSV file",
            "task_type": "python",
            "inputs": [{"name": "file_path", "io_type": "file_path"}],
            "outputs": [{"name": "data", "io_type": "dict"}],
            "code": "import csv",
            "test_code": "assert True",
        }
        errors = validator.validate_task(data)
        assert errors == []

    def test_valid_llm_task(self, validator: SchemaValidator) -> None:
        data = {
            "name": "summarize",
            "description": "Summarize text",
            "task_type": "llm",
            "inputs": [{"name": "text", "io_type": "string"}],
            "outputs": [{"name": "summary", "io_type": "string"}],
            "prompt_template": "Summarize: {{ text }}",
        }
        errors = validator.validate_task(data)
        assert errors == []

    def test_missing_required_field(self, validator: SchemaValidator) -> None:
        data = {"name": "incomplete"}
        errors = validator.validate_task(data)
        assert len(errors) > 0

    def test_invalid_io_type(self, validator: SchemaValidator) -> None:
        data = {
            "name": "bad",
            "description": "Bad",
            "task_type": "python",
            "inputs": [{"name": "x", "io_type": "invalid_type"}],
            "outputs": [],
            "code": "",
            "test_code": "",
        }
        errors = validator.validate_task(data)
        assert len(errors) > 0

    def test_risk_level_field(self, validator: SchemaValidator) -> None:
        data = {
            "name": "risky",
            "description": "Risky task",
            "task_type": "llm",
            "inputs": [],
            "outputs": [],
            "prompt_template": "do something dangerous",
            "risk_level": "high",
        }
        errors = validator.validate_task(data)
        assert errors == []

    def test_requires_approval_precondition(
        self, validator: SchemaValidator
    ) -> None:
        data = {
            "name": "approved",
            "description": "Task needing approval",
            "task_type": "llm",
            "inputs": [],
            "outputs": [],
            "prompt_template": "delete everything",
            "preconditions": [
                {"type": "requires_approval", "value": "destructive"}
            ],
        }
        errors = validator.validate_task(data)
        assert errors == []


class TestSkillSchemaValidation:
    def test_valid_skill(self, validator: SchemaValidator) -> None:
        data = {
            "name": "extract_w2",
            "description": "Extract W-2 data",
            "nodes": [{"node_id": "n1", "task_definition_id": "t1"}],
            "edges": [],
        }
        errors = validator.validate_skill(data)
        assert errors == []

    def test_edge_with_data_policy(self, validator: SchemaValidator) -> None:
        data = {
            "name": "skill",
            "description": "A skill",
            "nodes": [
                {"node_id": "n1", "task_definition_id": "t1"},
                {"node_id": "n2", "task_definition_id": "t2"},
            ],
            "edges": [
                {
                    "source_node_id": "n1",
                    "target_node_id": "n2",
                    "output_mapping": {"out": "in"},
                    "data_policy": "summarize",
                    "max_chars": 4000,
                }
            ],
        }
        errors = validator.validate_skill(data)
        assert errors == []


class TestToolkitSchemaValidation:
    def test_valid_toolkit(self, validator: SchemaValidator) -> None:
        data = {
            "name": "file_io",
            "description": "File I/O toolkit",
            "public_api": [
                {"name": "read_file", "description": "Read a file"}
            ],
        }
        errors = validator.validate_toolkit(data)
        assert errors == []

    def test_missing_public_api(self, validator: SchemaValidator) -> None:
        data = {"name": "bad", "description": "Missing api"}
        errors = validator.validate_toolkit(data)
        assert len(errors) > 0
