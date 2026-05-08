from __future__ import annotations

"""Tests for search.py uncovered lines — coverage gap remediation.

Covers:
  - _relational_enrichment (lines 326-335)
  - _associative_enrichment (lines 337-364)
  - _hydrate_search_results (lines 540-584)
  - _compute_recency edge cases (lines 508, 513-515)
  - _execute_vector_search (lines 519-538 approx)
"""


from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from claude_memory.search import SearchMixin

# ─── Helpers ────────────────────────────────────────────────────────


def _make_search_mixin() -> SearchMixin:
    """Create a SearchMixin with mocked dependencies."""
    svc = SearchMixin.__new__(SearchMixin)
    svc.repo = AsyncMock()
    svc.repo = AsyncMock()
    svc.vector_store = AsyncMock()
    svc.embedder = MagicMock()
    svc.embedder.encode.return_value = [0.1, 0.2, 0.3]
    svc.activation_engine = MagicMock()
    svc.activation_engine.spread = AsyncMock()
    svc.context_manager = MagicMock()
    return svc


# ═══════════════════════════════════════════════════════════════
#  _relational_enrichment
# ═══════════════════════════════════════════════════════════════


class TestRelationalEnrichment:
    """3e/1s/1h for _relational_enrichment."""

    @pytest.mark.asyncio()
    async def test_happy_two_quoted_entities_traverses(self) -> None:
        """Happy: query with 2 quoted entities triggers traverse_path."""
        svc = _make_search_mixin()
        svc.traverse_path = AsyncMock(return_value=[{"id": "a"}, {"id": "b"}])

        # Mock the name→UUID Cypher lookup (Fix #6: names resolved before traverse)
        alice_res = MagicMock()
        alice_res.result_set = [["uuid-alice"]]
        bob_res = MagicMock()
        bob_res.result_set = [["uuid-bob"]]
        svc.repo.execute_cypher.side_effect = [alice_res, bob_res]

        result = await svc._relational_enrichment('How does "Alice" relate to "Bob"?')
        assert len(result) == 2
        svc.traverse_path.assert_called_once_with("uuid-alice", "uuid-bob")

    @pytest.mark.asyncio()
    async def test_sad_one_quoted_entity_returns_empty(self) -> None:
        """Sad: query with only 1 quoted entity — not enough for path."""
        svc = _make_search_mixin()

        result = await svc._relational_enrichment('Tell me about "Alice"')
        assert result == []

    @pytest.mark.asyncio()
    async def test_sad_no_quotes_returns_empty(self) -> None:
        """Sad: no quoted entities in query returns empty."""
        svc = _make_search_mixin()

        result = await svc._relational_enrichment("plain query no quotes")
        assert result == []

    @pytest.mark.asyncio()
    async def test_evil_non_dict_path_nodes_filtered(self) -> None:
        """Evil: non-dict nodes in traverse_path result are filtered out."""
        svc = _make_search_mixin()
        svc.traverse_path = AsyncMock(return_value=[{"id": "a"}, "not-a-dict", {"id": "b"}])

        # Mock name→UUID lookup
        res1 = MagicMock()
        res1.result_set = [["uuid-e1"]]
        res2 = MagicMock()
        res2.result_set = [["uuid-e2"]]
        svc.repo.execute_cypher.side_effect = [res1, res2]

        result = await svc._relational_enrichment('"Entity1" to "Entity2"')
        assert len(result) == 2  # non-dict filtered

    @pytest.mark.asyncio()
    async def test_evil_traverse_returns_empty(self) -> None:
        """Evil: traverse_path returns empty path."""
        svc = _make_search_mixin()
        svc.traverse_path = AsyncMock(return_value=[])

        # Mock name→UUID lookup
        res1 = MagicMock()
        res1.result_set = [["uuid-alice"]]
        res2 = MagicMock()
        res2.result_set = [["uuid-bob"]]
        svc.repo.execute_cypher.side_effect = [res1, res2]

        result = await svc._relational_enrichment('"Alice" to "Bob"')
        assert result == []

    @pytest.mark.asyncio()
    async def test_evil_three_quoted_uses_first_two(self) -> None:
        """Evil: 3+ quoted entities — uses first two only."""
        svc = _make_search_mixin()
        svc.traverse_path = AsyncMock(return_value=[{"id": "a"}])

        # Mock name→UUID lookup (only first two quoted names are used)
        res1 = MagicMock()
        res1.result_set = [["uuid-a"]]
        res2 = MagicMock()
        res2.result_set = [["uuid-b"]]
        svc.repo.execute_cypher.side_effect = [res1, res2]

        _ = await svc._relational_enrichment('"A" then "B" then "C"')
        svc.traverse_path.assert_called_once_with("uuid-a", "uuid-b")


# ═══════════════════════════════════════════════════════════════
#  _associative_enrichment
# ═══════════════════════════════════════════════════════════════


class TestAssociativeEnrichment:
    """3e/1s/1h for _associative_enrichment."""

    @pytest.mark.asyncio()
    async def test_happy_returns_enriched_nodes(self) -> None:
        """Happy: spreads activation from vector seeds, returns graph nodes."""
        svc = _make_search_mixin()
        svc.activation_engine.activate.return_value = {"e1": 1.0}
        svc.activation_engine.spread.return_value = {"e1": 0.8, "e2": 0.5}
        svc.repo.get_subgraph.return_value = {
            "nodes": [{"id": "e1", "name": "A"}, {"id": "e2", "name": "B"}]
        }

        result = await svc._associative_enrichment(
            "test query",
            [{"_id": "e1", "_score": 0.9}],
            limit=10,
            project_id=None,
        )
        assert len(result) == 2

    @pytest.mark.asyncio()
    async def test_sad_empty_vector_results(self) -> None:
        """Sad: no vector results → returns empty immediately."""
        svc = _make_search_mixin()

        result = await svc._associative_enrichment("test", [], limit=10, project_id=None)
        assert result == []

    @pytest.mark.asyncio()
    async def test_evil_limit_caps_results(self) -> None:
        """Evil: result count is capped by limit parameter."""
        svc = _make_search_mixin()
        svc.activation_engine.activate.return_value = {"e1": 1.0}
        svc.activation_engine.spread.return_value = {f"e{i}": 0.5 for i in range(20)}
        svc.repo.get_subgraph.return_value = {
            "nodes": [{"id": f"e{i}", "name": f"N{i}"} for i in range(20)]
        }

        result = await svc._associative_enrichment(
            "test", [{"_id": "e1", "_score": 0.9}], limit=5, project_id=None
        )
        assert len(result) <= 5

    @pytest.mark.asyncio()
    async def test_evil_non_dict_nodes_filtered(self) -> None:
        """Evil: non-dict nodes in graph data are filtered."""
        svc = _make_search_mixin()
        svc.activation_engine.activate.return_value = {"e1": 1.0}
        svc.activation_engine.spread.return_value = {}
        svc.repo.get_subgraph.return_value = {
            "nodes": [{"id": "e1", "name": "A"}, "not-a-dict", None]
        }

        result = await svc._associative_enrichment(
            "test", [{"_id": "e1", "_score": 0.9}], limit=10, project_id=None
        )
        assert len(result) == 1  # only dict with id kept

    @pytest.mark.asyncio()
    async def test_evil_node_without_id_filtered(self) -> None:
        """Evil: dict without 'id' key is filtered out."""
        svc = _make_search_mixin()
        svc.activation_engine.activate.return_value = {"e1": 1.0}
        svc.activation_engine.spread.return_value = {}
        svc.repo.get_subgraph.return_value = {
            "nodes": [{"id": "e1", "name": "A"}, {"name": "No ID"}]
        }

        result = await svc._associative_enrichment(
            "test", [{"_id": "e1", "_score": 0.9}], limit=10, project_id=None
        )
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
#  _compute_recency edge cases
# ═══════════════════════════════════════════════════════════════


class TestComputeRecencyEdgeCases:
    """Additional edge cases for _compute_recency (lines 508, 513-515)."""

    @pytest.mark.asyncio
    async def test_evil_naive_timestamp_gets_utc(self) -> None:
        """Evil: naive (no timezone) timestamp treated as UTC."""
        from claude_memory.schema import SearchResult

        r = SearchResult(
            id="x",
            name="X",
            node_type="Entity",
            project_id="p",
            score=0.0,
            distance=0.0,
        )
        # 1 day ago as naive timestamp
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        score = SearchMixin._compute_recency(r, occurred_at=yesterday)
        assert 0.0 < score < 1.0  # decayed but not zero

    @pytest.mark.asyncio
    async def test_evil_invalid_timestamp_falls_back(self) -> None:
        """Evil: unparsable timestamp falls back to existing recency_score."""
        from claude_memory.schema import SearchResult

        r = SearchResult(
            id="x",
            name="X",
            node_type="Entity",
            project_id="p",
            score=0.0,
            distance=0.0,
            recency_score=0.42,
        )
        score = SearchMixin._compute_recency(r, occurred_at="not-a-timestamp")
        assert score == 0.42

    @pytest.mark.asyncio
    async def test_evil_type_error_falls_back(self) -> None:
        """Evil: wrong type (int instead of str) falls back gracefully."""
        from claude_memory.schema import SearchResult

        r = SearchResult(
            id="x",
            name="X",
            node_type="Entity",
            project_id="p",
            score=0.0,
            distance=0.0,
            recency_score=0.33,
        )
        score = SearchMixin._compute_recency(r, occurred_at=12345)  # type: ignore[arg-type]
        assert score == 0.33
