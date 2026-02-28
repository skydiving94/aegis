"""Enumerations for vector embeddings and document categorization."""

from enum import Enum


class EmbeddingCategory(str, Enum):
    """Categories of embeddable content for fast categorical search filtering."""

    TASK = "task"
    SKILL = "skill"
    USER_PREF = "user_pref"
    OBJECTIVE = "objective"
    DOCUMENT = "document"
