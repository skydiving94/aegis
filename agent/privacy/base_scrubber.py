"""Abstract base for privacy scrubbing."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ScrubResult(BaseModel):
    """Result of scrubbing text for PII."""

    scrubbed_text: str
    replacements: dict[str, str] = Field(default_factory=dict)  # placeholder -> original


class AbstractPrivacyScrubber(ABC):
    """ABC for PII scrubbing implementations."""

    @abstractmethod
    def scrub(self, text: str) -> ScrubResult:
        """Scrub PII from text, replacing with placeholders.

        Args:
            text: Raw text potentially containing PII.

        Returns:
            ScrubResult with scrubbed text and a mapping of placeholders to originals.
        """
        ...

    @abstractmethod
    def unscrub(self, text: str, replacements: dict[str, str]) -> str:
        """Reverse placeholder substitution to restore original values.

        Args:
            text: Text containing placeholders.
            replacements: Mapping of placeholder -> original value.

        Returns:
            Text with placeholders replaced by original values.
        """
        ...
