"""Gold Stack tests for entity_extraction module (Tier 2.1).

3-evil/1-sad/1-happy — tests written BEFORE implementation (TDD Red phase).

The entity_extraction module should:
- Extract named entities (PERSON, ORG, GPE/LOC) using spaCy
- Detect preference patterns ("I like...", "I prefer...", "my favorite...")
- Return list[tuple[str, str]] of (name, entity_type)
- Gracefully handle empty/None input
- Deduplicate extracted entities
"""

from __future__ import annotations

from claude_memory.entity_extraction import extract_entities

# ═══════════════════════════════════════════════════════════════
#  extract_entities: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestExtractEntities:
    """Gold Stack tests for extract_entities()."""

    # ── Happy path ───────────────────────────────────────────

    def test_happy_extracts_person_and_org(self) -> None:
        """Extracts PERSON and ORG entities from natural language."""
        text = "John Smith works at Google and lives in London."
        entities = extract_entities(text)

        names = [name for name, _ in entities]
        types = [etype for _, etype in entities]

        assert "John Smith" in names
        assert "Google" in names
        # At least one PERSON and one ORG
        assert "PERSON" in types
        assert "ORG" in types

    def test_happy_extracts_location(self) -> None:
        """Extracts GPE/LOC entities."""
        text = "I traveled to Paris and Tokyo last summer."
        entities = extract_entities(text)

        names = [name for name, _ in entities]
        # At least one location should be found
        assert any(name in ("Paris", "Tokyo") for name in names)

    def test_happy_extracts_preferences(self) -> None:
        """Detects preference patterns like 'I like', 'my favorite'."""
        text = "I like Python and my favorite editor is VS Code."
        entities = extract_entities(text)

        types = [etype for _, etype in entities]

        # Should detect at least one preference
        assert "PREFERENCE" in types

    def test_happy_returns_tuples(self) -> None:
        """Return type is list of (name, type) tuples."""
        text = "Alice met Bob at Microsoft."
        entities = extract_entities(text)

        assert isinstance(entities, list)
        for item in entities:
            assert isinstance(item, tuple)
            assert len(item) == 2
            name, etype = item
            assert isinstance(name, str)
            assert isinstance(etype, str)

    # ── Sad path ─────────────────────────────────────────────

    def test_sad1_empty_string_returns_empty(self) -> None:
        """Empty string → empty list."""
        assert extract_entities("") == []

    def test_sad1_none_returns_empty(self) -> None:
        """None input → empty list (graceful, no crash)."""
        assert extract_entities(None) == []  # type: ignore[arg-type]

    def test_sad1_no_entities_returns_empty(self) -> None:
        """Text with no entities → empty list."""
        result = extract_entities("the quick brown fox jumps over the lazy dog")
        # May or may not be empty depending on model, but should not crash
        assert isinstance(result, list)

    # ── Evil path ────────────────────────────────────────────

    def test_evil1_deduplicates_entities(self) -> None:
        """Same entity mentioned multiple times → deduplicated."""
        text = "Alice talked to Bob. Then Alice and Bob went to lunch."
        entities = extract_entities(text)

        names = [name for name, _ in entities]
        # Count how many times "Alice" appears
        alice_count = names.count("Alice")
        assert alice_count <= 1, f"Alice appears {alice_count} times — should be deduped"

    def test_evil1_very_long_text_doesnt_crash(self) -> None:
        """Very long text doesn't OOM or timeout."""
        text = "John works at Google. " * 500
        entities = extract_entities(text)

        # Should succeed without blowing up
        assert isinstance(entities, list)
        # Should still detect entities
        assert len(entities) > 0

    def test_evil1_special_characters_handled(self) -> None:
        """Text with special chars, unicode, newlines doesn't crash."""
        text = "María García works at Société Générale\nin São Paulo.\n\t🚀"
        entities = extract_entities(text)

        # Should not crash — result may vary by model
        assert isinstance(entities, list)
