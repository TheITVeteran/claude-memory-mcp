"""Entity extraction using spaCy NER + preference pattern detection.

Extracts named entities and preference signals from natural language
text. Used as a retrieval channel for entity-first search (Tier 2.1).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Entity types we care about from spaCy NER
_RELEVANT_NER_LABELS = frozenset({"PERSON", "ORG", "GPE", "LOC", "FAC", "NORP"})

# Preference patterns — capture the object of preference
_PREFERENCE_PATTERNS = [
    re.compile(r"(?:I|i) (?:like|love|enjoy|prefer)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
    re.compile(
        r"(?:my|My) (?:favorite|favourite|preferred)\s+\w+\s+is\s+(.+?)(?:\.|,|$)", re.IGNORECASE
    ),
]

# Lazy-loaded spaCy model
_UNAVAILABLE = object()  # Sentinel: spaCy model failed to load
_nlp: Any = None


def _get_nlp() -> Any:
    """Lazy-load spaCy model on first use."""
    global _nlp  # noqa: PLW0603
    if _nlp is None:
        try:
            import spacy  # noqa: PLC0415

            _nlp = spacy.load("en_core_web_sm")
            logger.info("Loaded spaCy model: en_core_web_sm")
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not found. "
                "Install with: python -m spacy download en_core_web_sm"
            )
            _nlp = _UNAVAILABLE  # Mark as unavailable
    return _nlp


def extract_entities(text: str | None) -> list[tuple[str, str]]:
    """Extract named entities and preference signals from text.

    Args:
        text: Natural language text to extract from. None/empty → [].

    Returns:
        Deduplicated list of (name, entity_type) tuples.
        entity_type is one of: PERSON, ORG, GPE, LOC, FAC, NORP, PREFERENCE.
    """
    if not text:
        return []

    seen: set[str] = set()
    entities: list[tuple[str, str]] = []

    # Phase 1: spaCy NER extraction
    nlp = _get_nlp()
    if nlp is not None and nlp is not _UNAVAILABLE:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in _RELEVANT_NER_LABELS:
                name = ent.text.strip()
                if name and name not in seen:
                    seen.add(name)
                    entities.append((name, ent.label_))

    # Phase 2: Preference pattern extraction
    for pattern in _PREFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            pref_text = match.group(1).strip()
            if pref_text and pref_text not in seen:
                seen.add(pref_text)
                entities.append((pref_text, "PREFERENCE"))

    return entities
