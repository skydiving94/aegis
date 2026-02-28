"""spaCy-based NER privacy scrubber with regex fallback."""

from __future__ import annotations

import re

from helpers.privacy.base_scrubber import AbstractPrivacyScrubber, ScrubResult

# Regex patterns for PII not always caught by NER
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_EIN_PATTERN = re.compile(r"\b\d{2}-\d{7}\b")

# Entity types to scrub (spaCy) — preserves MONEY, CARDINAL, DATE
_SCRUB_LABELS = {"PERSON", "ORG", "GPE", "NORP", "FAC", "LOC"}

# Maps entity labels to placeholder prefixes
_LABEL_PREFIX: dict[str, str] = {
    "PERSON": "NAME",
    "ORG": "ORG",
    "GPE": "LOCATION",
    "NORP": "GROUP",
    "FAC": "FACILITY",
    "LOC": "LOCATION",
    "SSN": "SSN",
    "PHONE": "PHONE",
    "EMAIL": "EMAIL",
    "EIN": "EIN",
}


class SpaCyNERScrubber(AbstractPrivacyScrubber):
    """Privacy scrubber using spaCy NER + regex fallback.

    Preserves dollar amounts (MONEY entities) and field labels.
    Replaces PERSON, ORG, GPE, SSN, phone, email with numbered placeholders.
    """

    def __init__(self, model: str = "en_core_web_trf") -> None:
        try:
            import spacy  # type: ignore[import-untyped]

            self._nlp = spacy.load(model)
        except (ImportError, OSError):
            # Fallback: regex-only mode if spaCy model not available
            self._nlp = None

    def scrub(self, text: str) -> ScrubResult:
        """Scrub PII from text using spaCy NER + regex patterns."""
        # Collect all entities to scrub: (start, end, label, original_text)
        entities: list[tuple[int, int, str, str]] = []

        # 1. spaCy NER entities
        if self._nlp is not None:
            doc = self._nlp(text)
            for ent in doc.ents:
                if ent.label_ in _SCRUB_LABELS:
                    entities.append((ent.start_char, ent.end_char, ent.label_, ent.text))

        # 2. Regex patterns (SSN, phone, email, EIN)
        for match in _SSN_PATTERN.finditer(text):
            entities.append((match.start(), match.end(), "SSN", match.group()))
        for match in _PHONE_PATTERN.finditer(text):
            entities.append((match.start(), match.end(), "PHONE", match.group()))
        for match in _EMAIL_PATTERN.finditer(text):
            entities.append((match.start(), match.end(), "EMAIL", match.group()))
        for match in _EIN_PATTERN.finditer(text):
            entities.append((match.start(), match.end(), "EIN", match.group()))

        # 3. Merge and deduplicate overlapping entities
        entities = self._merge_regex_and_ner(entities)

        # 4. Build scrubbed text and replacement map
        replacements: dict[str, str] = {}
        label_counters: dict[str, int] = {}
        scrubbed_parts: list[str] = []
        last_end = 0

        for start, end, label, original in entities:
            scrubbed_parts.append(text[last_end:start])
            prefix = _LABEL_PREFIX.get(label, label)
            label_counters[prefix] = label_counters.get(prefix, 0) + 1
            placeholder = f"[{prefix}_{label_counters[prefix]}]"
            scrubbed_parts.append(placeholder)
            replacements[placeholder] = original
            last_end = end

        scrubbed_parts.append(text[last_end:])

        return ScrubResult(
            scrubbed_text="".join(scrubbed_parts),
            replacements=replacements,
        )

    def unscrub(self, text: str, replacements: dict[str, str]) -> str:
        """Reverse placeholder substitution."""
        result = text
        for placeholder, original in replacements.items():
            result = result.replace(placeholder, original)
        return result

    @staticmethod
    def _merge_regex_and_ner(
        entities: list[tuple[int, int, str, str]],
    ) -> list[tuple[int, int, str, str]]:
        """Merge overlapping entities, preferring longer spans."""
        if not entities:
            return []

        # Sort by start position, then by span length (longest first)
        sorted_ents = sorted(entities, key=lambda e: (e[0], -(e[1] - e[0])))
        merged: list[tuple[int, int, str, str]] = [sorted_ents[0]]

        for ent in sorted_ents[1:]:
            last = merged[-1]
            if ent[0] < last[1]:
                # Overlap — keep the longer one (already first due to sorting)
                continue
            merged.append(ent)

        return merged
