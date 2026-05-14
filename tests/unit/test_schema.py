"""PR-1: Cypher Label Injection Guard — schema validation tests.

Tests the field_validator on CreateMemoryTypeParams.name that prevents
graph schema corruption from malformed memory type names.

Gold Stack 3-evil/1-sad/1-happy per function.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from claude_memory.schema import CreateMemoryTypeParams

# ═══════════════════════════════════════════════════════════════════
# CreateMemoryTypeParams.name — Cypher Label Injection Guard
# ═══════════════════════════════════════════════════════════════════


class TestCreateMemoryTypeNameValidator:
    """Validates the Cypher-safe label regex [A-Z][A-Za-z0-9_]{0,63}."""

    # --- Evil 1: Cypher syntax injection ---

    def test_evil1_cypher_close_brace_rejected(self) -> None:
        """Evil: '}' in name would break Cypher MERGE syntax."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity { x: 1}", description="injection attempt")

    def test_evil1_cypher_colon_rejected(self) -> None:
        """Evil: ':' in name would inject a second label."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity:Hacked", description="label injection")

    def test_evil1_cypher_open_brace_rejected(self) -> None:
        """Evil: '{' in name would corrupt property block."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity{name:$x}", description="injection")

    def test_evil1_single_quote_rejected(self) -> None:
        """Evil: single quote would break Cypher string context."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity'DROP", description="injection")

    def test_evil1_double_quote_rejected(self) -> None:
        """Evil: double quote would break Cypher string context."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name='Entity"DROP', description="injection")

    def test_evil1_backtick_rejected(self) -> None:
        """Evil: backtick is used for escaped identifiers in Cypher."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity`DROP`", description="injection")

    def test_evil1_newline_rejected(self) -> None:
        """Evil: newline would break the Cypher query structure."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Entity\nDROP", description="injection")

    # --- Evil 2: Invalid format ---

    def test_evil2_empty_string_rejected(self) -> None:
        """Evil: empty string is not a valid Cypher label."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="", description="empty")

    def test_evil2_lowercase_start_rejected(self) -> None:
        """Evil: labels must start with uppercase per convention."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="entity", description="lowercase start")

    def test_evil2_spaces_rejected(self) -> None:
        """Evil: spaces are not valid in Cypher labels."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="Memory Type", description="has space")

    def test_evil2_starts_with_number_rejected(self) -> None:
        """Evil: Cypher labels cannot start with a digit."""
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name="2Fast", description="number start")

    # --- Evil 3: Boundary / overflow ---

    def test_evil3_65_chars_rejected(self) -> None:
        """Evil: exceeds 64-char max (1 uppercase + 63 alnum = 64 ok, 65 fails)."""
        name_65 = "A" * 65
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name=name_65, description="too long")

    def test_evil3_100_chars_rejected(self) -> None:
        """Evil: well over the 64-char max."""
        name_100 = "A" * 100
        with pytest.raises(ValueError, match="Memory type name must start with"):
            CreateMemoryTypeParams(name=name_100, description="way too long")

    # --- Sad 1: Edge cases that are technically valid but surprising ---

    def test_sad1_single_char_accepted(self) -> None:
        """Sad: single uppercase letter is technically valid — borderline usable."""
        params = CreateMemoryTypeParams(name="A", description="minimal")
        assert params.name == "A"

    def test_sad1_all_underscores_after_uppercase(self) -> None:
        """Sad: 'A___' is technically valid — ugly but safe."""
        params = CreateMemoryTypeParams(name="A___", description="underscory")
        assert params.name == "A___"

    # --- Happy: All 13 existing node_types from the live graph ---

    _EXISTING_NODE_TYPES: ClassVar[list[str]] = [
        "Entity",
        "Bottle",
        "Concept",
        "Session",
        "Breakthrough",
        "Tool",
        "Decision",
        "Analogy",
        "Issue",
        "Project",
        "Procedure",
        "Person",
        "Observation",
    ]

    @pytest.mark.parametrize("node_type", _EXISTING_NODE_TYPES)
    def test_happy_existing_node_types_all_valid(self, node_type: str) -> None:
        """Happy: every existing node_type in the live graph passes validation."""
        params = CreateMemoryTypeParams(name=node_type, description=f"existing {node_type}")
        assert params.name == node_type

    def test_happy_underscore_name_accepted(self) -> None:
        """Happy: typical new type name with underscore."""
        params = CreateMemoryTypeParams(name="Concept_v2", description="versioned concept")
        assert params.name == "Concept_v2"

    def test_happy_max_64_chars_accepted(self) -> None:
        """Happy: exactly 64 chars (1 uppercase + 63 alnum) is the boundary."""
        name_64 = "A" + "b" * 63
        params = CreateMemoryTypeParams(name=name_64, description="max length")
        assert params.name == name_64

    def test_happy_mixed_case_alphanumeric(self) -> None:
        """Happy: 'MemoryType' — typical PascalCase name."""
        params = CreateMemoryTypeParams(name="MemoryType", description="standard")
        assert params.name == "MemoryType"


# ═══════════════════════════════════════════════════════════════════
# repository.py create_node — Belt-and-braces assert
# ═══════════════════════════════════════════════════════════════════


class TestCreateNodeLabelAssert:
    """Verify the defensive assert in repository.py:create_node.

    This catches code paths that bypass the Pydantic schema boundary
    and call create_node directly with a malformed label.
    """

    def test_evil1_direct_call_injection_asserts(self) -> None:
        """Evil: direct call bypassing schema with Cypher injection in label."""
        from claude_memory.repository import MemoryRepository

        with patch.object(MemoryRepository, "__init__", lambda self, **kw: None):
            repo = MemoryRepository()
            with pytest.raises(AssertionError, match="Invalid Cypher label"):
                repo.create_node("Entity { x: 1}", {"name": "test", "project_id": "p1"})

    def test_evil2_lowercase_label_asserts(self) -> None:
        """Evil: lowercase label bypassing schema."""
        from claude_memory.repository import MemoryRepository

        with patch.object(MemoryRepository, "__init__", lambda self, **kw: None):
            repo = MemoryRepository()
            with pytest.raises(AssertionError, match="Invalid Cypher label"):
                repo.create_node("entity", {"name": "test", "project_id": "p1"})

    def test_evil3_empty_label_asserts(self) -> None:
        """Evil: empty string label bypassing schema."""
        from claude_memory.repository import MemoryRepository

        with patch.object(MemoryRepository, "__init__", lambda self, **kw: None):
            repo = MemoryRepository()
            with pytest.raises(AssertionError, match="Invalid Cypher label"):
                repo.create_node("", {"name": "test", "project_id": "p1"})

    def test_happy_valid_label_passes_assert(self) -> None:
        """Happy: valid label passes the assert and proceeds to graph query."""
        from claude_memory.repository import MemoryRepository

        with patch.object(MemoryRepository, "__init__", lambda self, **kw: None):
            repo = MemoryRepository()
            # Mock select_graph to avoid actual DB call
            mock_graph = MagicMock()
            mock_node = MagicMock()
            mock_node.properties = {"name": "test", "id": "abc"}
            mock_graph.query.return_value.result_set = [[mock_node]]
            repo.select_graph = MagicMock(return_value=mock_graph)

            result = repo.create_node("Concept", {"name": "test", "project_id": "p1"})
            assert result == {"name": "test", "id": "abc"}
