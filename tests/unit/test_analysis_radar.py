"""Tests for find_semantic_opportunities (Semantic Radar Layer 4).

Covers: empty graph, fully connected, deduplication, project filtering,
disconnected cluster detection, and limit enforcement.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.schema import FindSemanticOpportunitiesParams
from claude_memory.tools import MemoryService

# ─── Test Constants ─────────────────────────────────────────────────

ENTITY_A = "entity-a"
ENTITY_B = "entity-b"
ENTITY_C = "entity-c"
ENTITY_D = "entity-d"


# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def service(mock_vector_store: Any) -> Generator[MemoryService, None, None]:
    with (
        patch("claude_memory.repository.FalkorDB"),
        patch("claude_memory.embedding.EmbeddingService") as mock_embedder_cls,
    ):
        svc = MemoryService(
            embedding_service=mock_embedder_cls.return_value,
            vector_store=mock_vector_store,
        )
        svc.repo.client = MagicMock()
        svc.repo.client.select_graph.return_value = MagicMock()
        yield svc


# ─── Evil Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evil1_empty_graph(service: MemoryService) -> None:
    """Evil: no entities in graph → empty results."""
    with patch.object(service.repo, "get_all_node_ids", return_value=[]):
        result = await service.find_semantic_opportunities(FindSemanticOpportunitiesParams())

    assert result["opportunities"] == []
    assert result["stats"]["entities_scanned"] == 0


@pytest.mark.asyncio
async def test_evil2_fully_connected_graph(service: MemoryService) -> None:
    """Evil: all pairs below min_graph_distance → no opportunities."""
    similar = [
        {"_id": ENTITY_B, "_score": 0.9, "payload": {"name": "B", "node_type": "Concept"}},
    ]

    with patch.object(service.repo, "get_all_node_ids", return_value=[ENTITY_A]):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=1):
                result = await service.find_semantic_opportunities(
                    FindSemanticOpportunitiesParams(min_graph_distance=3)
                )

    assert result["opportunities"] == []
    assert result["stats"]["already_connected"] == 1


@pytest.mark.asyncio
async def test_evil3_deduplication(service: MemoryService) -> None:
    """Evil: pair (A,B) found from both directions → only one kept (higher score)."""
    # When scanning A, find B as similar
    # When scanning B, find A as similar (with different score)
    call_count = 0

    async def mock_find_similar(entity_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        if entity_id == ENTITY_A:
            return [
                {"_id": ENTITY_B, "_score": 0.8, "payload": {"name": "B", "node_type": "Concept"}}
            ]
        return [{"_id": ENTITY_A, "_score": 0.9, "payload": {"name": "A", "node_type": "Concept"}}]

    with patch.object(service.repo, "get_all_node_ids", return_value=[ENTITY_A, ENTITY_B]):
        with patch.object(
            service.vector_store, "find_similar_by_id", side_effect=mock_find_similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=None):
                result = await service.find_semantic_opportunities(
                    FindSemanticOpportunitiesParams()
                )

    # Should be deduplicated to 1 pair
    assert len(result["opportunities"]) == 1
    # Should keep the higher score (0.9 * ln(51) > 0.8 * ln(51))
    opp = result["opportunities"][0]
    assert opp["cosine_similarity"] == 0.9


# ─── Sad Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sad1_project_id_filters(service: MemoryService) -> None:
    """Sad: project_id filter causes relevant Cypher to be used."""
    mock_res = MagicMock()
    mock_res.result_set = [[ENTITY_A]]

    with patch.object(service.repo, "execute_cypher", return_value=mock_res) as mock_cypher:
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=[]
        ):
            result = await service.find_semantic_opportunities(
                FindSemanticOpportunitiesParams(project_id="my-project")
            )

    # Verify execute_cypher was called with project filter
    call_args = mock_cypher.call_args
    assert "project_id" in call_args[0][0]
    assert call_args[0][1] == {"pid": "my-project"}
    assert result["stats"]["entities_scanned"] == 1


# ─── Happy Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_disconnected_clusters_found(service: MemoryService) -> None:
    """Happy: two isolated groups with similar entities → bridges found."""

    # Entity A finds C as similar (different cluster)
    async def mock_find_similar(entity_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        if entity_id == ENTITY_A:
            return [
                {"_id": ENTITY_C, "_score": 0.85, "payload": {"name": "C", "node_type": "Concept"}}
            ]
        if entity_id == ENTITY_B:
            return [
                {"_id": ENTITY_D, "_score": 0.75, "payload": {"name": "D", "node_type": "Concept"}}
            ]
        return []

    with patch.object(service.repo, "get_all_node_ids", return_value=[ENTITY_A, ENTITY_B]):
        with patch.object(
            service.vector_store, "find_similar_by_id", side_effect=mock_find_similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=None):
                result = await service.find_semantic_opportunities(
                    FindSemanticOpportunitiesParams()
                )

    assert len(result["opportunities"]) == 2
    assert result["stats"]["bridges_found"] == 2
    # Sorted by radar_score descending
    scores = [o["radar_score"] for o in result["opportunities"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_happy_limit_respected(service: MemoryService) -> None:
    """Happy: more opportunities than limit → only limit returned."""
    # Create many similar results for entity A
    many_similar = [
        {
            "_id": f"target-{i}",
            "_score": 0.9 - i * 0.01,
            "payload": {"name": f"T{i}", "node_type": "Concept"},
        }
        for i in range(10)
    ]

    with patch.object(service.repo, "get_all_node_ids", return_value=[ENTITY_A]):
        with patch.object(
            service.vector_store,
            "find_similar_by_id",
            new_callable=AsyncMock,
            return_value=many_similar,
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=None):
                result = await service.find_semantic_opportunities(
                    FindSemanticOpportunitiesParams(limit=3)
                )

    assert len(result["opportunities"]) == 3
    assert result["stats"]["bridges_found"] == 3
