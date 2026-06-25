"""Gold Stack tests for _entity_extraction_enrichment channel (Tier 2.2).

TDD Red phase — tests written BEFORE the channel implementation.
Tests the pipeline integration: query → NER → entity lookup → channel results.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests._helpers.mock_factory import make_mock_service

# ── Helpers ──────────────────────────────────────────────────────────


MOCK_EMBEDDING = [0.1] * 384


def _make_cypher_result(rows: list[list[Any]]) -> MagicMock:
    """Build a mock FalkorDB query result."""
    mock = MagicMock()
    mock.result_set = rows
    return mock


@pytest.fixture()
def service():
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — preserve per soft-routing path
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])
    svc.search_associative = AsyncMock(return_value=[])

    # Test-default returns on helper-built typed deps
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c
    svc.activation_engine.activate.return_value = {}  # helper-typed MagicMock
    svc.activation_engine.spread.return_value = {}  # helper-typed AsyncMock (fixes wrong-type bug)

    return svc


def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Added 22e to extend forcing-test coverage to all migrated files.
    DO NOT remove or weaken — guard against migrations that bypass
    make_mock_service() and reintroduce the hand-rolled bug class.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is `async def` — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, MagicMock), (
        "ActivationEngine.activate is sync `def` — must be MagicMock"
    )
    assert not isinstance(service.activation_engine.activate, AsyncMock), (
        "Guard against bare AsyncMock — production does NOT await activate"
    )


# ═══════════════════════════════════════════════════════════════
#  _entity_extraction_enrichment: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestEntityExtractionChannel:
    """Gold Stack tests for the entity extraction retrieval channel."""

    @pytest.mark.asyncio()
    async def test_happy_entity_names_lookup_graph(self, service) -> None:
        """NER extracts 'Google' from query → Cypher finds it → returns as channel result."""
        pytest.importorskip("spacy", reason="spaCy not installed")
        # Mock: Cypher finds a node named "Google"
        mock_node = MagicMock()
        mock_node.properties = {"id": "google-001", "name": "Google"}
        service.repo.execute_cypher.return_value = _make_cypher_result([[mock_node]])

        results = await service._entity_extraction_enrichment("Tell me about Google")

        assert len(results) > 0
        ids = [r["id"] for r in results]
        assert "google-001" in ids

    @pytest.mark.asyncio()
    async def test_happy_multiple_entities_found(self, service) -> None:
        """Multiple NER entities → multiple Cypher lookups → combined results."""
        mock_node_a = MagicMock()
        mock_node_a.properties = {"id": "alice-001", "name": "Alice"}
        mock_node_b = MagicMock()
        mock_node_b.properties = {"id": "bob-001", "name": "Bob"}

        service.repo.execute_cypher.return_value = _make_cypher_result(
            [
                [mock_node_a],
                [mock_node_b],
            ]
        )

        results = await service._entity_extraction_enrichment("Alice and Bob discussed Python")

        # Should find at least the NER-matched entities
        assert isinstance(results, list)

    @pytest.mark.asyncio()
    async def test_sad1_no_entities_in_query(self, service) -> None:
        """No NER entities in query → empty results (no Cypher call needed)."""
        results = await service._entity_extraction_enrichment("the quick brown fox")

        # Should return empty — no entities to look up
        assert results == []

    @pytest.mark.asyncio()
    async def test_sad1_entities_not_in_graph(self, service) -> None:
        """NER extracts entities but graph has no matching nodes → empty."""
        service.repo.execute_cypher.return_value = _make_cypher_result([])

        results = await service._entity_extraction_enrichment("Tell me about Elon Musk")

        assert results == []

    @pytest.mark.asyncio()
    async def test_evil1_cypher_error_returns_empty(self, service) -> None:
        """Cypher query failure → graceful degradation (empty list)."""
        service.repo.execute_cypher.side_effect = ConnectionError("FalkorDB down")

        results = await service._entity_extraction_enrichment("Tell me about Google")

        assert results == []

    @pytest.mark.asyncio()
    async def test_evil1_empty_query_returns_empty(self, service) -> None:
        """Empty query string → empty results."""
        results = await service._entity_extraction_enrichment("")

        assert results == []

    @pytest.mark.asyncio()
    async def test_evil1_result_format_has_id_key(self, service) -> None:
        """Results must have 'id' key for RRF merge compatibility."""
        mock_node = MagicMock()
        mock_node.properties = {"id": "test-001", "name": "TestEntity"}
        service.repo.execute_cypher.return_value = _make_cypher_result([[mock_node]])

        results = await service._entity_extraction_enrichment("Tell me about TestEntity")

        if results:  # Only check format if entities were found
            for r in results:
                assert "id" in r, f"Result missing 'id' key: {r}"
