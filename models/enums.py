"""Enumerations for the autonomous agent."""

from enum import Enum


class TaskType(str, Enum):
    """Discriminator for task polymorphism."""

    PYTHON = "python"
    LLM = "llm"


class IOType(str, Enum):
    """Supported I/O field types for task definitions."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DICT = "dict"
    LIST = "list"
    FILE_PATH = "file_path"
    ANY = "any"
    OBJECT = "object"


class ExecutionStatus(str, Enum):
    """Status of a task execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PIVOTED = "pivoted"  # PythonTask failed TDD, pivoted to LLMTask


class PreconditionType(str, Enum):
    """Types of deterministic preconditions for task matching."""

    INPUT_FORMAT = "input_format"
    OUTPUT_FORMAT = "output_format"
    LANGUAGE = "language"
    PLATFORM = "platform"
    REQUIRES_APPROVAL = "requires_approval"  # triggers HITL gate before execution
    CUSTOM = "custom"


class RiskLevel(str, Enum):
    """Risk assessment for HITL approval gating."""

    LOW = "low"  # no approval needed
    MEDIUM = "medium"  # logged, no approval
    HIGH = "high"  # requires user approval before execution
    CRITICAL = "critical"  # requires approval + confirmation of output


class DataPolicy(str, Enum):
    """Controls how data flows between nodes on an edge."""

    PASS_THROUGH = "pass_through"  # raw data flows as-is (default for PythonTask targets)
    SUMMARIZE = "summarize"  # LLM summarizes before passing downstream
    REFERENCE = "reference"  # passes metadata/pointer, not raw content
    TRUNCATE = "truncate"  # hard-truncate to max_chars
