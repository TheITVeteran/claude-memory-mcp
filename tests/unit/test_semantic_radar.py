"""Tests for semantic_radar + shortest_path_length (Semantic Radar Layer 2).

Covers: shortest_path_length forward/reverse/no-path, semantic_radar scoring,
filtering, relationship type inference.
"""

import math
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.schema import SemanticRadarParams
from claude_memory.tools import MemoryService

# ─── Test Constants ─────────────────────────────────────────────────

ENTITY_ID = "entity-001"
ENTITY_ID_2 = "entity-002"
ENTITY_ID_3 = "entity-003"
ENTITY_ID_4 = "entity-004"


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


# ─── shortest_path_length Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_evil1_forward_succeeds(service: MemoryService) -> None:
    """Evil: forward direction returns length — use it directly."""
    graph = service.repo.client.select_graph.return_value
    graph.query.return_value.result_set = [[3]]

    result = await service.repo.shortest_path_length(ENTITY_ID, ENTITY_ID_2)

    assert result == 3
    # Only one call (forward succeeded)
    assert graph.query.call_count == 1
    assert "shortestPath" in graph.query.call_args[0][0]


@pytest.mark.asyncio
async def test_evil2_forward_fails_reverse_succeeds(service: MemoryService) -> None:
    """Evil: forward throws exception, reverse returns length."""
    graph = service.repo.client.select_graph.return_value

    # First call (forward) raises, second call (reverse) returns 5
    graph.query.side_effect = [Exception("no directed path"), MagicMock(result_set=[[5]])]

    result = await service.repo.shortest_path_length(ENTITY_ID, ENTITY_ID_2)

    assert result == 5
    assert graph.query.call_count == 2


@pytest.mark.asyncio
async def test_evil3_both_directions_fail(service: MemoryService) -> None:
    """Evil: both forward and reverse return no result — returns None."""
    graph = service.repo.client.select_graph.return_value

    # Both calls return empty result sets
    empty_result = MagicMock(result_set=[])
    graph.query.return_value = empty_result

    result = await service.repo.shortest_path_length(ENTITY_ID, ENTITY_ID_2)

    assert result is None


# ─── semantic_radar Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_evil1_no_similar_neighbors(service: MemoryService) -> None:
    """Evil: find_similar_by_id returns empty — no suggestions."""
    with patch.object(
        service.repo,
        "get_node",
        return_value={
            "id": ENTITY_ID,
            "name": "Test",
            "node_type": "Concept",
            "project_id": "proj-1",
        },
    ):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=[]
        ):
            result = await service.semantic_radar(SemanticRadarParams(entity_id=ENTITY_ID))

    assert result["suggestions"] == []
    assert result["stats"]["candidates_scanned"] == 0


@pytest.mark.asyncio
async def test_evil2_all_directly_connected(service: MemoryService) -> None:
    """Evil: all candidates at graph_distance <= 1 — all filtered out."""
    similar = [
        {
            "_id": ENTITY_ID_2,
            "_score": 0.9,
            "payload": {"name": "A", "node_type": "Concept", "project_id": "proj-1"},
        },
        {
            "_id": ENTITY_ID_3,
            "_score": 0.85,
            "payload": {"name": "B", "node_type": "Concept", "project_id": "proj-1"},
        },
    ]
    with patch.object(
        service.repo,
        "get_node",
        return_value={
            "id": ENTITY_ID,
            "name": "Test",
            "node_type": "Concept",
            "project_id": "proj-1",
        },
    ):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=1):
                result = await service.semantic_radar(SemanticRadarParams(entity_id=ENTITY_ID))

    assert result["suggestions"] == []
    assert result["stats"]["already_connected"] == 2


@pytest.mark.asyncio
async def test_evil3_radar_score_disconnected_entities(service: MemoryService) -> None:
    """Evil: disconnected entity uses MAX_DISTANCE_FACTOR for radar score."""
    similar = [
        {
            "_id": ENTITY_ID_2,
            "_score": 0.8,
            "payload": {"name": "A", "node_type": "Concept", "project_id": "proj-1"},
        },
    ]
    with patch.object(
        service.repo,
        "get_node",
        return_value={
            "id": ENTITY_ID,
            "name": "Test",
            "node_type": "Concept",
            "project_id": "proj-1",
        },
    ):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=None):
                result = await service.semantic_radar(SemanticRadarParams(entity_id=ENTITY_ID))

    assert len(result["suggestions"]) == 1
    suggestion = result["suggestions"][0]
    # radar_score = cosine_sim * math.log(1 + 5.0 * 10) = 0.8 * ln(51) ≈ 3.1454
    import math as _m

    assert suggestion["radar_score"] == round(0.8 * _m.log(51), 4)
    assert suggestion["graph_distance"] is None
    assert result["stats"]["disconnected"] == 1


@pytest.mark.asyncio
async def test_sad1_entity_not_in_graph(service: MemoryService) -> None:
    """Sad: entity doesn't exist in graph — returns error."""
    with patch.object(service.repo, "get_node", return_value=None):
        result = await service.semantic_radar(SemanticRadarParams(entity_id="nonexistent-id"))

    assert "error" in result
    assert result["suggestions"] == []


@pytest.mark.asyncio
async def test_happy_suggestions_sorted_by_radar_score(service: MemoryService) -> None:
    """Happy: candidates at different distances — sorted by radar_score descending."""
    similar = [
        {
            "_id": ENTITY_ID_2,
            "_score": 0.7,
            "payload": {"name": "Close", "node_type": "Concept", "project_id": "proj-1"},
        },
        {
            "_id": ENTITY_ID_3,
            "_score": 0.9,
            "payload": {"name": "Disconnected", "node_type": "Concept", "project_id": "proj-1"},
        },
        {
            "_id": ENTITY_ID_4,
            "_score": 0.8,
            "payload": {"name": "Far", "node_type": "Concept", "project_id": "proj-1"},
        },
    ]

    def mock_path_length(from_id: str, to_id: str) -> int | None:
        distances = {ENTITY_ID_2: 3, ENTITY_ID_3: None, ENTITY_ID_4: 8}
        return distances.get(to_id)

    with patch.object(
        service.repo,
        "get_node",
        return_value={
            "id": ENTITY_ID,
            "name": "Test",
            "node_type": "Concept",
            "project_id": "proj-1",
        },
    ):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=similar
        ):
            with patch.object(service.repo, "shortest_path_length", side_effect=mock_path_length):
                result = await service.semantic_radar(SemanticRadarParams(entity_id=ENTITY_ID))

    suggestions = result["suggestions"]
    assert len(suggestions) == 3

    # Verify descending radar_score order
    scores = [s["radar_score"] for s in suggestions]
    assert scores == sorted(scores, reverse=True)

    # Verify expected scores:
    # Disconnected: 0.9 * ln(51) ≈ 0.9 * 3.932 = 3.5383 (highest)
    # Far: 0.8 * ln(9) ≈ 0.8 * 2.197 = 1.7578
    # Close: 0.7 * ln(4) ≈ 0.7 * 1.386 = 0.9704
    assert suggestions[0]["candidate_name"] == "Disconnected"
    assert suggestions[0]["radar_score"] == round(0.9 * math.log(51), 4)
    assert suggestions[1]["candidate_name"] == "Far"
    assert suggestions[1]["radar_score"] == round(0.8 * math.log(1 + 8), 4)
    assert suggestions[2]["candidate_name"] == "Close"
    assert suggestions[2]["radar_score"] == round(0.7 * math.log(1 + 3), 4)


@pytest.mark.asyncio
async def test_happy_relationship_type_inference(service: MemoryService) -> None:
    """Happy: relationship types inferred from node_type pairs."""
    similar = [
        {
            "_id": ENTITY_ID_2,
            "_score": 0.8,
            "payload": {"name": "A", "node_type": "Concept", "project_id": "proj-1"},
        },
        {
            "_id": ENTITY_ID_3,
            "_score": 0.8,
            "payload": {"name": "B", "node_type": "Tool", "project_id": "proj-2"},
        },
        {
            "_id": ENTITY_ID_4,
            "_score": 0.8,
            "payload": {"name": "C", "node_type": "Project", "project_id": "proj-1"},
        },
    ]
    with patch.object(
        service.repo,
        "get_node",
        return_value={
            "id": ENTITY_ID,
            "name": "Test",
            "node_type": "Concept",
            "project_id": "proj-1",
        },
    ):
        with patch.object(
            service.vector_store, "find_similar_by_id", new_callable=AsyncMock, return_value=similar
        ):
            with patch.object(service.repo, "shortest_path_length", return_value=None):
                result = await service.semantic_radar(SemanticRadarParams(entity_id=ENTITY_ID))

    suggestions = result["suggestions"]
    rel_map = {s["candidate_id"]: s["suggested_relationship"] for s in suggestions}

    # Concept + Concept, same project → ANALOGOUS_TO
    assert rel_map[ENTITY_ID_2] == "ANALOGOUS_TO"
    # Cross-project → BRIDGES_TO (takes priority)
    assert rel_map[ENTITY_ID_3] == "BRIDGES_TO"
    # Concept + Project, same project → RELATED_TO (fallback)
    assert rel_map[ENTITY_ID_4] == "RELATED_TO"


@pytest.mark.asyncio
async def test_happy_enriched_relationship_mappings(service: MemoryService) -> None:
    """Happy: enriched mappings for Dragon Brain node types."""
    from claude_memory.search_advanced import SearchAdvancedMixin

    infer = SearchAdvancedMixin._infer_relationship_type

    # Breakthrough + Breakthrough → ANALOGOUS_TO
    assert infer("Breakthrough", "Breakthrough", "p1", "p1") == "ANALOGOUS_TO"
    # Concept + Analogy → ANALOGOUS_TO
    assert infer("Concept", "Analogy", "p1", "p1") == "ANALOGOUS_TO"
    assert infer("Analogy", "Concept", "p1", "p1") == "ANALOGOUS_TO"
    # Tool + Procedure → ENABLES
    assert infer("Tool", "Procedure", "p1", "p1") == "ENABLES"
    assert infer("Procedure", "Tool", "p1", "p1") == "ENABLES"
    # Decision + anything → DECIDED_IN
    assert infer("Decision", "Entity", "p1", "p1") == "DECIDED_IN"
    # Session + anything → MENTIONED_IN
    assert infer("Session", "Concept", "p1", "p1") == "MENTIONED_IN"
    # Person + anything → CREATED_BY
    assert infer("Person", "Tool", "p1", "p1") == "CREATED_BY"
    # Cross-project still takes priority
    assert infer("Person", "Tool", "p1", "p2") == "BRIDGES_TO"
    # Unknown types → RELATED_TO
    assert infer("Entity", "Issue", "p1", "p1") == "RELATED_TO"
