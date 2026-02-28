"""Typed I/O field and precondition models."""

from pydantic import BaseModel

from models.enums import IOType, PreconditionType


class TypedIOField(BaseModel):
    """Describes a single named input or output with its type."""

    name: str
    io_type: IOType
    description: str = ""
    max_chars: int | None = None  # optional cap for TRUNCATE policy


class Precondition(BaseModel):
    """A deterministic, typed precondition for task matching."""

    type: PreconditionType
    value: str
    description: str = ""
