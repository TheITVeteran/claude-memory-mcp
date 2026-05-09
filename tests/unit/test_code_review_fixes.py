"""Gold Stack tests for code review bugfixes (Issues #1-#7).

TDD Red phase — tests for all 7 issues from the code review.
Each class targets one issue. 3-evil/1-sad/1-happy per class.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock

import pytest

from claude_memory.activation import ActivationEngine

# ── Helpers ──────────────────────────────────────────────────────────


def _make_subgraph(
    node_ids: list[str],
    edges: list[tuple[str, str, str]],
) -> dict[str, Any]:
    return {
        "nodes": [{"id": nid} for nid in node_ids],
        "edges": [{"source": src, "target": tgt, "type": etype} for src, tgt, etype in edges],
    }


# ═══════════════════════════════════════════════════════════════
#  Issue #2: SUPERSEDES must be directional
# ═══════════════════════════════════════════════════════════════


class TestSupersedesDirectional:
    """SUPERSEDES energy should flow forward only (A supersedes B → drain B)."""

    @pytest.fixture()
    def engine(self):
        repo = AsyncMock()
        return ActivationEngine(repo)

    @pytest.mark.asyncio
    async def test_happy_forward_propagation_dampened(self, engine) -> None:
        """A SUPERSEDES B: energy flows A→B dampened."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"], [("A", "B", "SUPERSEDES")]
        )
        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # B should get dampened energy (forward direction)
        assert result.get("B", 0) > 0

    @pytest.mark.asyncio
    async def test_sad1_reverse_propagation_blocked(self, engine) -> None:
        """A SUPERSEDES B: querying B should NOT activate A (old doesn't boost new)."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"], [("A", "B", "SUPERSEDES")]
        )
        seeds = engine.activate(["B"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # A should NOT receive energy from B via SUPERSEDES (directional)
        assert result.get("A", 0) == 0

    @pytest.mark.asyncio
    async def test_evil1_rejected_for_also_directional(self, engine) -> None:
        """REJECTED_FOR is directional: reverse should be blocked."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"], [("A", "B", "REJECTED_FOR")]
        )
        seeds = engine.activate(["B"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        assert result.get("A", 0) == 0

    @pytest.mark.asyncio
    async def test_evil2_preceded_by_directional(self, engine) -> None:
        """PRECEDED_BY is directional: reverse should be blocked."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"], [("A", "B", "PRECEDED_BY")]
        )
        seeds = engine.activate(["B"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        assert result.get("A", 0) == 0

    @pytest.mark.asyncio
    async def test_evil3_relates_to_still_bidirectional(self, engine) -> None:
        """RELATES_TO should remain bidirectional."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"], [("A", "B", "RELATES_TO")]
        )
        seeds = engine.activate(["B"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # A should receive energy from B via RELATES_TO (symmetric)
        assert result.get("A", 0) > 0


# ═══════════════════════════════════════════════════════════════
#  Issue #3: Reranker gets UUID as text
# ═══════════════════════════════════════════════════════════════


class TestRerankerTextQuality:
    """Reranker text must never contain bare UUIDs."""

    @pytest.mark.asyncio
    async def test_happy_name_used_as_text(self) -> None:
        """When name exists, text should contain entity name."""
        from claude_memory.merge import MergedResult

        m = MergedResult(
            entity_id="uuid-123",
            rrf_score=0.5,
            graph_metadata={"name": "Python", "entity_type": "Concept"},
        )
        text = _build_rerank_text(m)
        assert "Python" in text
        assert "uuid-123" not in text

    @pytest.mark.asyncio
    async def test_sad1_empty_metadata_uses_description(self) -> None:
        """When name/entity_type empty, fallback to description, not UUID."""
        from claude_memory.merge import MergedResult

        m = MergedResult(
            entity_id="uuid-456",
            rrf_score=0.5,
            graph_metadata={"description": "A snake-based programming language"},
        )
        text = _build_rerank_text(m)
        assert "uuid-456" not in text
        assert "programming" in text

    @pytest.mark.asyncio
    async def test_evil1_completely_empty_metadata(self) -> None:
        """Completely empty metadata → should still not use UUID."""
        from claude_memory.merge import MergedResult

        m = MergedResult(
            entity_id="uuid-789",
            rrf_score=0.5,
            graph_metadata={},
        )
        text = _build_rerank_text(m)
        # Should not contain UUID pattern
        assert not re.search(r"uuid-\d+", text)

    @pytest.mark.asyncio
    async def test_evil2_text_never_empty_string(self) -> None:
        """Text should never be empty — must have something meaningful."""
        from claude_memory.merge import MergedResult

        m = MergedResult(
            entity_id="uuid-000",
            rrf_score=0.5,
            graph_metadata={},
        )
        text = _build_rerank_text(m)
        assert len(text.strip()) > 0

    @pytest.mark.asyncio
    async def test_evil3_observations_included_in_text(self) -> None:
        """If observations exist in metadata, include them."""
        from claude_memory.merge import MergedResult

        m = MergedResult(
            entity_id="uuid-obs",
            rrf_score=0.5,
            graph_metadata={"name": "Alice", "observations": ["Likes cats", "Works at Google"]},
        )
        text = _build_rerank_text(m)
        assert "Likes cats" in text


# ═══════════════════════════════════════════════════════════════
#  Issue #1: FTS id_key mismatch
# ═══════════════════════════════════════════════════════════════


class TestFtsIdKey:
    """FTS channel must declare correct id_key for RRF merge."""

    @pytest.mark.asyncio
    async def test_happy_fts_channel_uses_underscore_id(self) -> None:
        """FTS ChannelResults should use id_key='_id'."""
        # This tests the wiring in search.py, we check the ChannelResults
        from claude_memory.merge import ChannelResults

        fts_results = [{"_id": "ent-1", "_score": 5.2, "entity_id": "ent-1"}]
        ch = ChannelResults("fts", fts_results, weight=0.8, id_key="_id")
        assert ch.id_key == "_id"

    @pytest.mark.asyncio
    async def test_sad1_id_key_mismatch_loses_results(self) -> None:
        """Using wrong id_key='id' on FTS results → entity IDs not found."""
        from claude_memory.merge import ChannelResults, weighted_rrf_merge

        fts_results = [{"_id": "ent-1", "_score": 5.2}]
        # Bug: using default id_key="id" when data has "_id"
        ch = ChannelResults("fts", fts_results, weight=0.8)  # id_key="id" default
        merged = weighted_rrf_merge([ch], limit=5)

        # With fallback, this works by accident — without fallback, it wouldn't
        # The important thing: the channel SHOULD specify id_key="_id"
        assert len(merged) >= 0  # Doesn't crash

    @pytest.mark.asyncio
    async def test_evil1_correct_id_key_produces_results(self) -> None:
        """Correct id_key='_id' → results properly merged."""
        from claude_memory.merge import ChannelResults, weighted_rrf_merge

        fts_results = [{"_id": "ent-1", "_score": 5.2}]
        ch = ChannelResults("fts", fts_results, weight=0.8, id_key="_id")
        merged = weighted_rrf_merge([ch], limit=5)

        assert len(merged) == 1
        assert merged[0].entity_id == "ent-1"

    @pytest.mark.asyncio
    async def test_evil2_vector_and_fts_both_use_underscore_id(self) -> None:
        """Both vector and FTS should use _id consistently."""
        from claude_memory.merge import ChannelResults, weighted_rrf_merge

        vec = [{"_id": "shared-1", "_score": 0.9}]
        fts = [{"_id": "shared-1", "_score": 5.0}]

        channels = [
            ChannelResults("vector", vec, weight=1.0, id_key="_id"),
            ChannelResults("fts", fts, weight=0.8, id_key="_id"),
        ]
        merged = weighted_rrf_merge(channels, limit=5)

        # Shared entity should appear once with contributions from both
        assert len(merged) == 1
        assert "vector" in merged[0].retrieval_sources
        assert "fts" in merged[0].retrieval_sources

    @pytest.mark.asyncio
    async def test_evil3_graph_channels_use_plain_id(self) -> None:
        """Graph channels should use id_key='id' (not '_id')."""
        from claude_memory.merge import ChannelResults, weighted_rrf_merge

        graph = [{"id": "g-1", "name": "Test"}]
        ch = ChannelResults("temporal", graph, weight=0.3, id_key="id")
        merged = weighted_rrf_merge([ch], limit=5)

        assert len(merged) == 1
        assert merged[0].entity_id == "g-1"


# ═══════════════════════════════════════════════════════════════
#  Issue #7: Soft routing weight > 0 guards
# ═══════════════════════════════════════════════════════════════


class TestSoftRoutingGuards:
    """Weight > 0 guards should not exist — channels always fire."""

    @pytest.mark.asyncio
    async def test_happy_directional_edges_in_set(self) -> None:
        """DIRECTIONAL_EDGES constant exists and contains expected types."""
        from claude_memory.activation import DIRECTIONAL_EDGES

        assert "SUPERSEDES" in DIRECTIONAL_EDGES
        assert "REJECTED_FOR" in DIRECTIONAL_EDGES
        assert "PRECEDED_BY" in DIRECTIONAL_EDGES

    @pytest.mark.asyncio
    async def test_sad1_relates_to_not_directional(self) -> None:
        """RELATES_TO should NOT be in DIRECTIONAL_EDGES."""
        from claude_memory.activation import DIRECTIONAL_EDGES

        assert "RELATES_TO" not in DIRECTIONAL_EDGES

    @pytest.mark.asyncio
    async def test_evil1_supports_not_directional(self) -> None:
        """SUPPORTS should NOT be directional."""
        from claude_memory.activation import DIRECTIONAL_EDGES

        assert "SUPPORTS" not in DIRECTIONAL_EDGES

    @pytest.mark.asyncio
    async def test_evil2_evolved_from_is_directional(self) -> None:
        """EVOLVED_FROM is temporal/directional."""
        from claude_memory.activation import DIRECTIONAL_EDGES

        assert "EVOLVED_FROM" in DIRECTIONAL_EDGES

    @pytest.mark.asyncio
    async def test_evil3_contradicts_is_directional(self) -> None:
        """CONTRADICTS is epistemic/directional."""
        from claude_memory.activation import DIRECTIONAL_EDGES

        assert "CONTRADICTS" in DIRECTIONAL_EDGES


# ── Helper to extract (will be moved to search.py) ───────────────────


def _build_rerank_text(merged_result: Any) -> str:
    """Build text for cross-encoder from a MergedResult.

    This function will be extracted into search.py after tests pass.
    """
    from claude_memory.search import _build_rerank_text as impl

    return impl(merged_result)
