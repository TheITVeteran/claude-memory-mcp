"""Coverage gap tests for MemoryService (tools.py).

Targets all uncovered lines: create_relationship (with/without project lock),
update_entity, delete_entity (soft/hard with vector delete failures),
delete_relationship, add_observation (entity not found), end_session (not found),
record_breakthrough (with/without session), traverse_path (with path nodes,
without nodes attribute), point_in_time_query, search (with results),
analyze_graph (pagerank success/error, louvain success/error),
get_stale_entities, consolidate_memories (with/without edge creation errors),
create_memory_type.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.exceptions import SearchError
from claude_memory.schema import (
    AnalyzeGraphParams,
    CreateMemoryTypeParams,
    GetHologramParams,
    PointInTimeQueryParams,
    SearchMemoryParams,
    TraversePathParams,
)
from tests._helpers.mock_factory import make_mock_service

# ─── Test Constants ─────────────────────────────────────────────────

PROJECT_ID = "project-alpha"
ENTITY_ID = "entity-001"
ENTITY_ID_2 = "entity-002"
ENTITY_ID_3 = "entity-003"
ENTITY_NAME = "Python"
ENTITY_TYPE = "Language"
RELATIONSHIP_TYPE = "RELATED_TO"
RELATIONSHIP_ID = "rel-001"
CONFIDENCE_DEFAULT = 1.0

OBSERVATION_CONTENT = "Observed a critical pattern"
EVIDENCE_LIST = ["source-a", "source-b"]
CERTAINTY_CONFIRMED = "confirmed"
DELETE_REASON = "deprecated"

SESSION_ID = "session-001"
SESSION_FOCUS = "architecture"
SESSION_SUMMARY = "Reviewed patterns"
SESSION_OUTCOMES = ["fixed-race-condition"]

BREAKTHROUGH_NAME = "eureka"
BREAKTHROUGH_MOMENT = "2024-06-15T14:30:00Z"
BREAKTHROUGH_ANALOGY = "water-flow"
BREAKTHROUGH_CONCEPT = "async-patterns"

SEARCH_QUERY = "async patterns"
SEARCH_LIMIT = 5
TIME_AS_OF = "2024-01-01T00:00:00Z"
STALE_DAYS = 30

MOCK_EMBEDDING = [0.1, 0.2, 0.3]
MOCK_NODE_PROPS = {"id": ENTITY_ID, "name": ENTITY_NAME, "project_id": PROJECT_ID}

CONSOLIDATION_SUMMARY = "Merged related concepts"
CONSOLIDATION_TRUNCATED_LEN = 20

PAGERANK_SCORE = 0.85
COMMUNITY_ID = 1
COMMUNITY_SIZE = 5
COMMUNITY_MEMBERS = ["A", "B", "C"]


# ─── Module Import ──────────────────────────────────────────────────

with patch("claude_memory.repository.FalkorDB"):
    with patch("claude_memory.lock_manager.redis.Redis"):
        with patch("claude_memory.vector_store.AsyncQdrantClient"):
            from claude_memory.schema import (
                BreakthroughParams,
                EntityDeleteParams,
                EntityUpdateParams,
                ObservationParams,
                RelationshipCreateParams,
                RelationshipDeleteParams,
                SearchMemoryParams,
                SessionEndParams,
            )
            from claude_memory.tools import MemoryService


# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def service() -> MemoryService:
    """Creates a MemoryService with all dependencies mocked type-correctly via mock_factory.

    Per process/issues/22c_BUILD_SPEC.md — uses make_mock_service() to eliminate
    hand-rolled MagicMock-vs-AsyncMock decisions. Helper introspects each
    dependency class to AsyncMock async methods and MagicMock sync methods
    automatically.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — helper does not mock methods on
    # the service itself, only deps. Preserve these per the soft-routing path.
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])

    # Prevent _fire_salience_update from creating orphan asyncio.create_task()
    # coroutines. The real method calls asyncio.create_task(repo.increment_salience(...))
    # which, with an AsyncMock repo, produces unawaited coroutines at GC time.
    # This is a MemoryService instance method, not a dep — helper does not mock it.
    svc._fire_salience_update = MagicMock()

    # Test-default returns/side_effects on helper-built typed deps
    svc.repo.get_subgraph.return_value = {"nodes": [], "edges": []}
    svc.repo.get_observations_for_entity.return_value = []
    svc.fts_store.search.return_value = []
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c

    # Per-test default return values on activation_engine. Per 22b's
    # AG-reported discovery (AsyncMock chain semantics): without explicit
    # return values, awaited results are bare AsyncMocks whose attribute access
    # (e.g. spread_map.keys()) returns coroutines → TypeError + RuntimeWarning.
    svc.activation_engine.activate.return_value = {}  # helper-typed MagicMock (sync)
    svc.activation_engine.spread.return_value = {}  # helper-typed AsyncMock (async)

    # Lock context manager mock — lock_manager.lock() returns a context manager
    # used with `with`. Helper builds lock_manager via inspect; configure .lock
    # to return the context manager mock.
    mock_lock = AsyncMock()
    mock_lock.__enter__ = MagicMock(return_value=mock_lock)
    mock_lock.__exit__ = MagicMock(return_value=False)
    svc.lock_manager.lock.return_value = mock_lock

    return svc


def _make_cypher_result(rows: list[list[Any]]) -> MagicMock:
    """Creates a mock Cypher query result."""
    result = MagicMock()
    result.result_set = rows
    return result


# ─── Topographical Forcing (architect-injected) ─────────────────────


def test_meta_fixture_topology_required(service: MemoryService) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Updated 22c after 22a established the mock_factory helper and 22b
    validated the pattern. DO NOT remove or weaken — guard against migrations
    that bypass make_mock_service() and reintroduce the hand-rolled bug class.

    Per process/issues/22c_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    # Pure-async deps → AsyncMock
    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )

    # ActivationEngine is mixed (async spread + sync activate) — helper
    # introspects per-method via inspect.iscoroutinefunction()
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is `async def` (activation.py:98) — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, MagicMock), (
        "ActivationEngine.activate is sync `def` (activation.py:76) — must be MagicMock"
    )
    assert not isinstance(service.activation_engine.activate, AsyncMock), (
        "Guard against bare AsyncMock — production does NOT await activate"
    )

    # Sync deps → MagicMock
    assert isinstance(service.fts_store, MagicMock), (
        "service.fts_store has only sync methods — must be MagicMock"
    )
    assert isinstance(service.lock_manager, MagicMock), (
        "service.lock_manager.lock() returns a context manager (sync API) — must be MagicMock"
    )


# ─── create_relationship Tests ──────────────────────────────────────


async def test_happy_create_relationship_with_project_lock(service: MemoryService) -> None:
    """When source node has project_id, use project lock."""
    service.repo.get_node.return_value = {"id": ENTITY_ID, "project_id": PROJECT_ID}
    service.repo.create_edge.return_value = {"id": RELATIONSHIP_ID}

    params = RelationshipCreateParams(
        from_entity=ENTITY_ID,
        to_entity=ENTITY_ID_2,
        relationship_type=RELATIONSHIP_TYPE,
    )
    result = await service.create_relationship(params)
    assert result["id"] == RELATIONSHIP_ID
    service.lock_manager.lock.assert_called_once_with(PROJECT_ID)


async def test_happy_create_relationship_without_project(service: MemoryService) -> None:
    """When source node has no project_id, proceed without lock."""
    service.repo.get_node.return_value = {"id": ENTITY_ID}
    service.repo.create_edge.return_value = {"id": RELATIONSHIP_ID}

    params = RelationshipCreateParams(
        from_entity=ENTITY_ID,
        to_entity=ENTITY_ID_2,
        relationship_type=RELATIONSHIP_TYPE,
    )
    result = await service.create_relationship(params)
    assert result["id"] == RELATIONSHIP_ID


async def test_sad1_create_relationship_source_not_found(service: MemoryService) -> None:
    """When source node doesn't exist."""
    service.repo.get_node.return_value = None
    service.repo.create_edge.return_value = {"id": RELATIONSHIP_ID}

    params = RelationshipCreateParams(
        from_entity=ENTITY_ID,
        to_entity=ENTITY_ID_2,
        relationship_type=RELATIONSHIP_TYPE,
    )
    result = await service.create_relationship(params)
    assert result["id"] == RELATIONSHIP_ID


async def test_sad2_create_relationship_with_existing_id_in_props(service: MemoryService) -> None:
    """Branch 157→16: 'id' already in properties, UUID generation skipped."""
    service.repo.get_node.return_value = None
    pre_set_id = "custom-rel-id-999"
    service.repo.create_edge.return_value = {"id": pre_set_id}

    params = RelationshipCreateParams(
        from_entity=ENTITY_ID,
        to_entity=ENTITY_ID_2,
        relationship_type=RELATIONSHIP_TYPE,
        properties={"id": pre_set_id},
    )
    result = await service.create_relationship(params)
    assert result["id"] == pre_set_id
    # Verify the id we passed was preserved (not overwritten by uuid)
    call_args = service.repo.create_edge.call_args
    assert call_args[0][3]["id"] == pre_set_id


async def test_evil1_create_relationship_edge_creation_fails(service: MemoryService) -> None:
    """When edge creation returns empty result."""
    service.repo.get_node.return_value = None
    service.repo.create_edge.return_value = {}

    params = RelationshipCreateParams(
        from_entity=ENTITY_ID,
        to_entity=ENTITY_ID_2,
        relationship_type=RELATIONSHIP_TYPE,
    )
    result = await service.create_relationship(params)
    assert "error" in result


# ─── update_entity Tests ───────────────────────────────────────────


async def test_happy_update_entity_with_project_lock(service: MemoryService) -> None:
    service.repo.get_node.return_value = MOCK_NODE_PROPS
    service.repo.update_node.return_value = {**MOCK_NODE_PROPS, "version": "2.0"}

    params = EntityUpdateParams(entity_id=ENTITY_ID, properties={"version": "2.0"}, reason="update")
    result = await service.update_entity(params)
    service.lock_manager.lock.assert_called_once_with(PROJECT_ID)
    assert result["version"] == "2.0"


async def test_evil2_update_entity_not_found(service: MemoryService) -> None:
    service.repo.get_node.return_value = None

    params = EntityUpdateParams(entity_id=ENTITY_ID, properties={"version": "2.0"}, reason="update")
    result = await service.update_entity(params)
    assert result == {"error": "Entity not found"}


# ─── delete_entity Tests ───────────────────────────────────────────


async def test_happy_delete_entity_soft(service: MemoryService) -> None:
    service.repo.get_node.return_value = MOCK_NODE_PROPS

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=True)
    result = await service.delete_entity(params)
    assert result["status"] == "archived"
    service.repo.update_node.assert_called_once()
    service.vector_store.delete.assert_awaited_once_with(ENTITY_ID)


async def test_evil3_delete_entity_soft_vector_delete_fails(service: MemoryService) -> None:
    """Soft delete now re-raises vector failures to prevent split-brain."""
    service.repo.get_node.return_value = MOCK_NODE_PROPS
    service.vector_store.delete.side_effect = ConnectionError("qdrant down")

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=True)
    with pytest.raises(SearchError, match="qdrant down"):
        await service.delete_entity(params)


async def test_happy_delete_entity_hard(service: MemoryService) -> None:
    service.repo.get_node.return_value = MOCK_NODE_PROPS

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=False)
    result = await service.delete_entity(params)
    assert result["status"] == "deleted"
    service.repo.delete_node.assert_called_once_with(ENTITY_ID)


async def test_evil4_delete_entity_hard_vector_delete_fails(service: MemoryService) -> None:
    """Hard delete now re-raises vector failures to prevent split-brain."""
    service.repo.get_node.return_value = MOCK_NODE_PROPS
    service.vector_store.delete.side_effect = ConnectionError("qdrant down")

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=False)
    with pytest.raises(SearchError, match="qdrant down"):
        await service.delete_entity(params)


async def test_evil5_delete_entity_not_found(service: MemoryService) -> None:
    service.repo.get_node.return_value = None

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=True)
    result = await service.delete_entity(params)
    assert result == {"error": "Entity not found"}


async def test_sad3_delete_entity_no_project(service: MemoryService) -> None:
    """Entity without project_id should still delete without lock."""
    service.repo.get_node.return_value = {"id": ENTITY_ID, "name": ENTITY_NAME}

    params = EntityDeleteParams(entity_id=ENTITY_ID, reason=DELETE_REASON, soft_delete=True)
    result = await service.delete_entity(params)
    assert result["status"] == "archived"


# ─── delete_relationship Tests ─────────────────────────────────────


async def test_happy_delete_relationship(service: MemoryService) -> None:
    params = RelationshipDeleteParams(relationship_id=RELATIONSHIP_ID, reason=DELETE_REASON)
    result = await service.delete_relationship(params)
    assert result == {"status": "deleted", "id": RELATIONSHIP_ID}
    service.repo.delete_edge.assert_called_once_with(RELATIONSHIP_ID)


# ─── add_observation Tests ─────────────────────────────────────────


async def test_happy_add_observation_success(service: MemoryService) -> None:
    mock_obs_node = MagicMock()
    mock_obs_node.properties = {"id": "obs-001", "content": OBSERVATION_CONTENT}
    service.repo.execute_cypher.return_value = _make_cypher_result([[mock_obs_node]])
    service.repo.get_node.return_value = {
        "name": "Test",
        "node_type": "Entity",
        "project_id": "test",
    }
    service.repo.get_observations_for_entity.return_value = []

    params = ObservationParams(
        entity_id=ENTITY_ID,
        content=OBSERVATION_CONTENT,
        certainty=CERTAINTY_CONFIRMED,
        evidence=EVIDENCE_LIST,
    )
    result = await service.add_observation(params)
    assert result["content"] == OBSERVATION_CONTENT


async def test_evil6_add_observation_entity_not_found(service: MemoryService) -> None:
    service.repo.execute_cypher.return_value = _make_cypher_result([])

    params = ObservationParams(
        entity_id=ENTITY_ID,
        content=OBSERVATION_CONTENT,
        certainty=CERTAINTY_CONFIRMED,
    )
    result = await service.add_observation(params)
    assert result == {"error": "Entity not found"}


# ─── end_session Tests ─────────────────────────────────────────────


async def test_evil7_end_session_not_found(service: MemoryService) -> None:
    service.repo.execute_cypher.return_value = _make_cypher_result([])

    params = SessionEndParams(
        session_id=SESSION_ID, summary=SESSION_SUMMARY, outcomes=SESSION_OUTCOMES
    )
    result = await service.end_session(params)
    assert result == {"error": "Session not found"}


# ─── record_breakthrough Tests ─────────────────────────────────────


async def test_happy_record_breakthrough_with_session(service: MemoryService) -> None:
    service.repo.create_node.return_value = {"id": "b-001", "name": BREAKTHROUGH_NAME}

    params = BreakthroughParams(
        name=BREAKTHROUGH_NAME,
        moment=BREAKTHROUGH_MOMENT,
        session_id=SESSION_ID,
        analogy_used=BREAKTHROUGH_ANALOGY,
        concepts_unlocked=[BREAKTHROUGH_CONCEPT],
    )
    result = await service.record_breakthrough(params)
    assert result["name"] == BREAKTHROUGH_NAME
    # Verify edge was created linking session to breakthrough
    service.repo.create_edge.assert_called_once()


async def test_happy_record_breakthrough_without_session(service: MemoryService) -> None:
    """When session_id is empty, no edge should be created."""
    service.repo.create_node.return_value = {"id": "b-001", "name": BREAKTHROUGH_NAME}

    params = BreakthroughParams(
        name=BREAKTHROUGH_NAME,
        moment=BREAKTHROUGH_MOMENT,
        session_id="",
    )
    result = await service.record_breakthrough(params)
    assert result["name"] == BREAKTHROUGH_NAME
    service.repo.create_edge.assert_not_called()


# ─── traverse_path Tests ──────────────────────────────────────────


async def test_happy_traverse_path_with_nodes(service: MemoryService) -> None:
    """When path has .nodes attribute, extract properties."""
    mock_node_a = MagicMock()
    mock_node_a.properties = {"id": ENTITY_ID, "name": "NodeA", "embedding": MOCK_EMBEDDING}
    mock_node_b = MagicMock()
    mock_node_b.properties = {"id": ENTITY_ID_2, "name": "NodeB"}

    mock_path = MagicMock()
    mock_path.nodes = [mock_node_a, mock_node_b]

    service.repo.execute_cypher.return_value = _make_cypher_result([[mock_path]])

    # Unmock traverse_path for this test
    service.traverse_path = MemoryService.traverse_path.__get__(service)

    result = await service.traverse_path(TraversePathParams(from_id=ENTITY_ID, to_id=ENTITY_ID_2))
    assert len(result) == 2
    # Verify embedding was stripped
    assert "embedding" not in result[0]


async def test_sad4_traverse_path_no_path_found(service: MemoryService) -> None:
    service.repo.execute_cypher.return_value = _make_cypher_result([])
    service.traverse_path = MemoryService.traverse_path.__get__(service)

    result = await service.traverse_path(TraversePathParams(from_id=ENTITY_ID, to_id=ENTITY_ID_2))
    assert result == []


async def test_sad5_traverse_path_no_nodes_attr(service: MemoryService) -> None:
    """When path object doesn't have .nodes attribute."""
    mock_path = MagicMock(spec=[])  # No attributes
    service.repo.execute_cypher.return_value = _make_cypher_result([[mock_path]])
    service.traverse_path = MemoryService.traverse_path.__get__(service)

    result = await service.traverse_path(TraversePathParams(from_id=ENTITY_ID, to_id=ENTITY_ID_2))
    assert result == []


# ─── search Tests ──────────────────────────────────────────────────


async def test_sad6_search_empty_query(service: MemoryService) -> None:
    _res = await service.search(SearchMemoryParams(query="", limit=SEARCH_LIMIT))
    result = _res.get("results", []) if isinstance(_res, dict) else _res
    assert result == []


async def test_sad7_search_no_vector_results(service: MemoryService) -> None:
    service.vector_store.search.return_value = []
    service.repo.get_subgraph.return_value = {"nodes": [], "edges": []}

    _res = await service.search(SearchMemoryParams(query=SEARCH_QUERY, limit=SEARCH_LIMIT))

    result = _res.get("results", []) if isinstance(_res, dict) else _res
    assert result == []


async def test_happy_search_with_results(service: MemoryService) -> None:
    service.vector_store.search.return_value = [
        {"_id": ENTITY_ID, "_score": PAGERANK_SCORE},
    ]
    service.repo.get_subgraph.return_value = {
        "nodes": [
            {
                "id": ENTITY_ID,
                "name": ENTITY_NAME,
                "node_type": ENTITY_TYPE,
                "project_id": PROJECT_ID,
                "description": "A programming language",
            }
        ],
        "edges": [],
    }

    _res = await service.search(SearchMemoryParams(query=SEARCH_QUERY, limit=SEARCH_LIMIT))

    result = _res.get("results", []) if isinstance(_res, dict) else _res
    assert len(result) == 1
    assert result[0].id == ENTITY_ID
    assert result[0].name == ENTITY_NAME
    assert result[0].score == PAGERANK_SCORE


async def test_sad8_search_node_not_in_graph(service: MemoryService) -> None:
    """When vector result ID is not in graph, it's excluded."""
    service.vector_store.search.return_value = [
        {"_id": "orphan-id", "_score": PAGERANK_SCORE},
    ]
    service.repo.get_subgraph.return_value = {"nodes": [], "edges": []}

    _res = await service.search(SearchMemoryParams(query=SEARCH_QUERY, limit=SEARCH_LIMIT))

    result = _res.get("results", []) if isinstance(_res, dict) else _res
    assert result == []


# ─── search with project_id filter ─────────────────────────────────


async def test_happy_search_with_project_id_filter(service: MemoryService) -> None:
    """Search with project_id passes filter to vector store."""
    service.vector_store.search.return_value = [
        {"_id": ENTITY_ID, "_score": PAGERANK_SCORE},
    ]
    service.repo.get_subgraph.return_value = {
        "nodes": [
            {
                "id": ENTITY_ID,
                "name": ENTITY_NAME,
                "node_type": ENTITY_TYPE,
                "project_id": PROJECT_ID,
                "description": "A language",
            }
        ],
        "edges": [],
    }

    _res = await service.search(
        SearchMemoryParams(query=SEARCH_QUERY, limit=SEARCH_LIMIT, project_id=PROJECT_ID)
    )
    result = _res.get("results", []) if isinstance(_res, dict) else _res
    assert len(result) == 1

    # Verify filter was passed to vector_store.search
    call_kwargs = service.vector_store.search.call_args[1]
    assert call_kwargs["filter"] == {"project_id": PROJECT_ID}


# ─── point_in_time_query Tests ─────────────────────────────────────


async def test_sad9_point_in_time_query_no_results(service: MemoryService) -> None:
    service.vector_store.search.return_value = []

    result = await service.point_in_time_query(
        PointInTimeQueryParams(query_text=SEARCH_QUERY, as_of=TIME_AS_OF)
    )
    assert result == []


async def test_happy_point_in_time_query_with_results(service: MemoryService) -> None:
    service.vector_store.search.return_value = [
        {"_id": ENTITY_ID},
    ]
    service.repo.get_subgraph.return_value = {
        "nodes": [{"id": ENTITY_ID, "name": ENTITY_NAME}],
        "edges": [],
    }

    result = await service.point_in_time_query(
        PointInTimeQueryParams(query_text=SEARCH_QUERY, as_of=TIME_AS_OF)
    )
    assert len(result) == 1
    assert result[0]["id"] == ENTITY_ID


# ─── analyze_graph Tests ──────────────────────────────────────────


async def test_happy_analyze_graph_pagerank_success(service: MemoryService) -> None:
    mock_node = MagicMock()
    mock_node.properties = {"name": ENTITY_NAME, "rank": PAGERANK_SCORE}
    mock_node.labels = [ENTITY_TYPE, "Entity"]

    service.repo.execute_cypher.side_effect = [
        _make_cypher_result([[mock_node]]),  # MATCH (n:Entity) RETURN n
        _make_cypher_result([]),  # MATCH edges
    ]

    with patch(
        "claude_memory.analysis.compute_pagerank",
        return_value=[{"name": ENTITY_NAME, "rank": PAGERANK_SCORE}],
    ):
        result = await service.analyze_graph(AnalyzeGraphParams(algorithm="pagerank"))
    assert len(result) == 1
    assert result[0]["name"] == ENTITY_NAME
    assert result[0]["rank"] == PAGERANK_SCORE


async def test_happy_analyze_graph_pagerank_only_entity_label(service: MemoryService) -> None:
    """When node only has 'Entity' label, type should be 'Entity'."""
    mock_node = MagicMock()
    mock_node.properties = {"name": ENTITY_NAME, "rank": PAGERANK_SCORE}
    mock_node.labels = ["Entity"]  # Only Entity label

    service.repo.execute_cypher.side_effect = [
        _make_cypher_result([[mock_node]]),
        _make_cypher_result([]),
    ]

    with patch(
        "claude_memory.analysis.compute_pagerank",
        return_value=[{"name": ENTITY_NAME, "rank": PAGERANK_SCORE, "type": "Entity"}],
    ):
        result = await service.analyze_graph(AnalyzeGraphParams(algorithm="pagerank"))
    assert result[0]["type"] == "Entity"


async def test_evil8_analyze_graph_pagerank_error(service: MemoryService) -> None:
    service.repo.execute_cypher.side_effect = RuntimeError("algo not available")

    with pytest.raises(RuntimeError, match="algo not available"):
        await service.analyze_graph(AnalyzeGraphParams(algorithm="pagerank"))


async def test_happy_analyze_graph_louvain_success(service: MemoryService) -> None:
    mock_node = MagicMock()
    mock_node.properties = {"name": ENTITY_NAME}
    mock_node.labels = ["Entity"]

    service.repo.execute_cypher.side_effect = [
        _make_cypher_result([[mock_node]]),  # MATCH (n:Entity) RETURN n
        _make_cypher_result([]),  # MATCH edges
    ]

    with patch(
        "claude_memory.analysis.compute_louvain",
        return_value=[
            {"community_id": COMMUNITY_ID, "size": COMMUNITY_SIZE, "members": COMMUNITY_MEMBERS}
        ],
    ):
        result = await service.analyze_graph(AnalyzeGraphParams(algorithm="louvain"))
    assert len(result) == 1
    assert result[0]["community_id"] == COMMUNITY_ID
    assert result[0]["size"] == COMMUNITY_SIZE


async def test_evil9_analyze_graph_louvain_error(service: MemoryService) -> None:
    service.repo.execute_cypher.side_effect = RuntimeError("algo not available")

    with pytest.raises(RuntimeError, match="algo not available"):
        await service.analyze_graph(AnalyzeGraphParams(algorithm="louvain"))


async def test_sad10_analyze_graph_unsupported_algorithm(service: MemoryService) -> None:
    """Branch 587→601: algorithm is neither 'pagerank' nor 'louvain' → raises ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        await service.analyze_graph(AnalyzeGraphParams(algorithm="unknown"))  # type: ignore[arg-type]


# ─── get_stale_entities Tests ──────────────────────────────────────


async def test_sad11_get_stale_entities(service: MemoryService) -> None:
    mock_node = MagicMock()
    mock_node.properties = {"id": ENTITY_ID, "name": ENTITY_NAME, "embedding": MOCK_EMBEDDING}

    service.repo.execute_cypher.return_value = _make_cypher_result([[mock_node]])

    result = await service.get_stale_entities(days=STALE_DAYS)
    assert len(result) == 1
    assert result[0]["id"] == ENTITY_ID
    # Verify embedding was stripped
    assert "embedding" not in result[0]


# ─── consolidate_memories Tests ─────────────────────────────────────


async def test_happy_consolidate_memories(service: MemoryService) -> None:
    service.repo.create_node.return_value = {"id": "consolidated-001", "name": "Consolidated"}

    result = await service.consolidate_memories(
        entity_ids=[ENTITY_ID, ENTITY_ID_2],
        summary=CONSOLIDATION_SUMMARY,
    )
    assert result["id"] == "consolidated-001"

    # Verify edges and archives for each old entity
    assert service.repo.create_edge.call_count == 2
    assert service.repo.update_node.call_count == 2
    service.vector_store.upsert.assert_awaited_once()


async def test_evil10_consolidate_memories_edge_error(service: MemoryService) -> None:
    """When linking an old entity fails, continue with remaining."""
    service.repo.create_node.return_value = {"id": "consolidated-001", "name": "Consolidated"}
    service.repo.create_edge.side_effect = [
        OSError("edge failed"),  # First entity fails
        MagicMock(),  # Second succeeds
    ]
    service.repo.update_node.return_value = {}

    result = await service.consolidate_memories(
        entity_ids=[ENTITY_ID, ENTITY_ID_2],
        summary=CONSOLIDATION_SUMMARY,
    )
    assert result["id"] == "consolidated-001"
    # Only one update_node since first one errored before reaching it
    assert service.repo.update_node.call_count == 1


# ─── create_memory_type Tests ──────────────────────────────────────


def test_happy_create_memory_type(service: MemoryService) -> None:
    result = service.create_memory_type(
        CreateMemoryTypeParams(
            name="Recipe",
            description="Culinary recipe",
            required_properties=["ingredients"],
        )
    )
    assert result["name"] == "Recipe"
    assert result["status"] == "active"
    service.ontology.add_type.assert_called_once_with("Recipe", "Culinary recipe", ["ingredients"])


def test_sad12_create_memory_type_defaults(service: MemoryService) -> None:
    result = service.create_memory_type(
        CreateMemoryTypeParams(name="Recipe", description="Culinary recipe")
    )
    assert result["required_properties"] == []


# ─── get_hologram Tests ────────────────────────────────────────────

HOLOGRAM_QUERY = "async patterns"
HOLOGRAM_DEPTH = 2
HOLOGRAM_MAX_TOKENS = 4000


async def test_sad13_get_hologram_no_anchors(service: MemoryService) -> None:
    """Line 715: search returns no anchors → early return."""
    service.vector_store.search.return_value = []

    result = await service.get_hologram(
        GetHologramParams(query=HOLOGRAM_QUERY, depth=HOLOGRAM_DEPTH)
    )
    assert result == {"nodes": [], "edges": []}


async def test_happy_get_hologram_with_non_dict_nodes(service: MemoryService) -> None:
    """Branch 733→732: raw_nodes contains a non-dict item → isinstance check False."""
    service.vector_store.search.return_value = [
        {"_id": ENTITY_ID, "_score": PAGERANK_SCORE},
    ]
    service.repo.get_subgraph.return_value = {
        "nodes": [
            {
                "id": ENTITY_ID,
                "name": ENTITY_NAME,
                "node_type": ENTITY_TYPE,
                "embedding": MOCK_EMBEDDING,
            },
        ],
        "edges": [],
    }

    # Mock search properly — it calls get_subgraph internally
    mock_search_result = MagicMock()
    mock_search_result.id = ENTITY_ID
    mock_search_result.name = ENTITY_NAME
    mock_search_result.score = PAGERANK_SCORE
    mock_search_result.model_dump.return_value = {"id": ENTITY_ID, "name": ENTITY_NAME}

    # Hologram's internal search call returns results
    with patch.object(service, "search", return_value=[mock_search_result]):
        # get_subgraph returns both dict and non-dict nodes
        service.repo.get_subgraph.return_value = {
            "nodes": [
                {"id": ENTITY_ID, "name": ENTITY_NAME, "embedding": MOCK_EMBEDDING},
                MagicMock(),  # non-dict node → branch 733→732 False
            ],
            "edges": [],
        }
        service.context_manager.optimize.return_value = [
            {"id": ENTITY_ID, "name": ENTITY_NAME},
        ]

        result = await service.get_hologram(
            GetHologramParams(
                query=HOLOGRAM_QUERY, depth=HOLOGRAM_DEPTH, max_tokens=HOLOGRAM_MAX_TOKENS
            )
        )

    assert result["query"] == HOLOGRAM_QUERY
    assert len(result["nodes"]) == 1
    # Embedding should have been stripped from the dict node
    assert "embedding" not in result["nodes"][0]
