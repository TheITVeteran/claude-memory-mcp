from __future__ import annotations

"""Gold Stack tests for weighted_rrf_merge (Tier 1.4) + channel weights (Tier 1.5).

Tests follow the 3-evil/1-sad/1-happy naming convention.
"""


from typing import Any

from claude_memory.merge import ChannelResults, weighted_rrf_merge
from claude_memory.router import QueryIntent, QueryRouter

# ── Helpers ──────────────────────────────────────────────────────────


def _vector(*ids: str) -> list[dict[str, Any]]:
    """Build mock vector results."""
    return [{"_id": eid, "_score": 0.9 - i * 0.1} for i, eid in enumerate(ids)]


def _graph(*ids: str) -> list[dict[str, Any]]:
    """Build mock graph results."""
    return [{"id": eid, "name": f"Node-{eid}"} for eid in ids]


# ═══════════════════════════════════════════════════════════════
#  weighted_rrf_merge: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestWeightedRRFMerge:
    """Gold Stack tests for weighted_rrf_merge."""

    def test_happy_multi_channel_merge(self) -> None:
        """Happy: entities from multiple channels get combined RRF scores."""
        channels = [
            ChannelResults("vector", _vector("a", "b", "c"), weight=1.0, id_key="_id"),
            ChannelResults("fts", _graph("b", "d"), weight=0.8),
            ChannelResults("temporal", _graph("a", "e"), weight=0.5),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        ids = [m.entity_id for m in merged]
        # "a" and "b" appear in 2 channels each → should rank higher
        assert "a" in ids[:3]
        assert "b" in ids[:3]
        # All 5 unique IDs present
        assert len(ids) == 5

    def test_happy_weights_affect_ranking(self) -> None:
        """Higher weight channel pushes its results up."""
        # Entity "x" only in a high-weight channel
        # Entity "y" only in a low-weight channel
        channels = [
            ChannelResults("high", [{"id": "x"}], weight=5.0),
            ChannelResults("low", [{"id": "y"}], weight=0.1),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        assert merged[0].entity_id == "x"
        assert merged[0].rrf_score > merged[1].rrf_score

    def test_happy_retrieval_sources_tracked(self) -> None:
        """Each result tracks which channels contributed."""
        channels = [
            ChannelResults("vector", _vector("a", "b"), weight=1.0, id_key="_id"),
            ChannelResults("fts", _graph("a"), weight=0.8),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        a_result = next(m for m in merged if m.entity_id == "a")
        assert "vector" in a_result.retrieval_sources
        assert "fts" in a_result.retrieval_sources

        b_result = next(m for m in merged if m.entity_id == "b")
        assert "vector" in b_result.retrieval_sources
        assert "fts" not in b_result.retrieval_sources

    def test_sad1_empty_channels(self) -> None:
        """All channels empty → empty results."""
        channels = [
            ChannelResults("vector", [], weight=1.0, id_key="_id"),
            ChannelResults("fts", [], weight=0.8),
        ]

        merged = weighted_rrf_merge(channels, limit=10)
        assert merged == []

    def test_sad1_zero_weight_channel_ignored(self) -> None:
        """Channel with weight=0 contributes nothing."""
        channels = [
            ChannelResults("active", _graph("a"), weight=1.0),
            ChannelResults("dead", _graph("b", "c"), weight=0.0),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        ids = [m.entity_id for m in merged]
        assert "a" in ids
        assert "b" not in ids
        assert "c" not in ids

    def test_evil1_limit_respected(self) -> None:
        """Limit parameter caps results."""
        channels = [
            ChannelResults("vector", _vector("a", "b", "c", "d", "e"), weight=1.0, id_key="_id"),
        ]

        merged = weighted_rrf_merge(channels, limit=2)
        assert len(merged) == 2

    def test_evil1_missing_id_skipped(self) -> None:
        """Results without an ID are silently skipped."""
        channels = [
            ChannelResults("broken", [{"name": "no-id"}, {"id": "ok"}], weight=1.0),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        assert len(merged) == 1
        assert merged[0].entity_id == "ok"

    def test_evil1_negative_weight_skipped(self) -> None:
        """Negative weight channel is skipped (treated same as 0)."""
        channels = [
            ChannelResults("good", _graph("a"), weight=1.0),
            ChannelResults("evil", _graph("b"), weight=-1.0),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        ids = [m.entity_id for m in merged]
        assert "a" in ids
        assert "b" not in ids

    def test_evil1_vector_metadata_preserved(self) -> None:
        """Vector scores and ranks are preserved in merge output."""
        channels = [
            ChannelResults("vector", [{"_id": "a", "_score": 0.95}], weight=1.0, id_key="_id"),
        ]

        merged = weighted_rrf_merge(channels, limit=10)

        assert merged[0].vector_score == 0.95
        assert merged[0].vector_rank == 1


# ═══════════════════════════════════════════════════════════════
#  Channel weight profiles: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestChannelWeightProfiles:
    """Gold Stack tests for QueryRouter.get_channel_weights()."""

    def test_happy_semantic_profile(self) -> None:
        """SEMANTIC: vector gets highest weight, graph channels get base."""
        weights = QueryRouter.get_channel_weights(QueryIntent.SEMANTIC)

        assert weights["vector"] == 1.0
        assert weights["fts"] == 0.8
        # Graph channels at base weight
        assert weights["temporal"] < weights["vector"]
        assert weights["relational"] < weights["vector"]

    def test_happy_temporal_profile(self) -> None:
        """TEMPORAL: temporal channel gets boosted weight."""
        weights = QueryRouter.get_channel_weights(QueryIntent.TEMPORAL)

        assert weights["temporal"] > weights["vector"]
        assert weights["temporal"] == 1.5

    def test_happy_relational_profile(self) -> None:
        """RELATIONAL: relational channel gets boosted weight."""
        weights = QueryRouter.get_channel_weights(QueryIntent.RELATIONAL)

        assert weights["relational"] > weights["vector"]
        assert weights["relational"] == 1.5

    def test_sad1_all_weights_positive(self) -> None:
        """All channel weights are always positive (soft routing guarantee)."""
        for intent in QueryIntent:
            weights = QueryRouter.get_channel_weights(intent)
            for channel, weight in weights.items():
                assert weight > 0, f"{channel} has non-positive weight for {intent}"

    def test_evil1_unknown_channel_not_in_weights(self) -> None:
        """Only known channels appear in weights dict."""
        weights = QueryRouter.get_channel_weights(QueryIntent.SEMANTIC)

        known = {"vector", "fts", "entity", "temporal", "relational", "associative"}
        assert set(weights.keys()) == known

    def test_evil1_associative_profile(self) -> None:
        """ASSOCIATIVE: associative channel gets boosted weight."""
        weights = QueryRouter.get_channel_weights(QueryIntent.ASSOCIATIVE)

        assert weights["associative"] == 1.5
        # Vector slightly reduced but still positive
        assert 0 < weights["vector"] < 1.0

    def test_evil1_fts_always_high(self) -> None:
        """FTS always has high base weight regardless of intent."""
        for intent in QueryIntent:
            weights = QueryRouter.get_channel_weights(intent)
            assert weights["fts"] >= 0.8
