"""Tests for AsyncMemoryRepository (B10.5 native async).

Verifies:
- Each async method dispatches to the native async client correctly
- Cypher queries match the canonical templates in cypher_queries.py
- Arguments forwarded with correct parameter binding
- Return values parsed correctly from FalkorDB result format
- Exceptions propagate transparently (SearchError contract preserved)
- Async retry logic operates correctly on transient failures
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from claude_memory.cypher_queries import (
    CREATE_EDGE,
    CREATE_NODE,
    DELETE_EDGE,
    GET_NODE_BY_ID,
    GET_TEMPORAL_NEIGHBORS_AFTER,
    GET_TEMPORAL_NEIGHBORS_BEFORE,
    GET_TEMPORAL_NEIGHBORS_BOTH,
    HARD_DELETE_NODE,
    QUERY_TIMELINE,
    QUERY_TIMELINE_WITH_PROJECT,
    SOFT_DELETE_NODE,
    UPDATE_NODE,
)
from claude_memory.exceptions import SearchError
from claude_memory.repository_async import AsyncMemoryRepository

# ─── Mock Helpers ───────────────────────────────────────────────────


def _make_mock_node(properties: dict[str, Any] | None = None) -> MagicMock:
    node = MagicMock()
    node.properties = properties or {}
    return node


def _make_mock_result(rows: list[list[Any]]) -> MagicMock:
    result = MagicMock()
    result.result_set = rows
    return result


@pytest.fixture
def mock_falkordb():
    """Mock falkordb.asyncio.FalkorDB with async graph + query methods."""
    mock_graph = MagicMock()
    mock_graph.query = AsyncMock()
    mock_client = MagicMock()
    mock_client.select_graph = MagicMock(return_value=mock_graph)
    mock_client.list_graphs = AsyncMock(return_value=[])
    return mock_client, mock_graph


@pytest.fixture
def repo(mock_falkordb):
    """AsyncMemoryRepository with mocked native async client."""
    mock_client, _ = mock_falkordb
    with patch("claude_memory.repository_async.FalkorDB", return_value=mock_client):
        r = AsyncMemoryRepository("localhost", 6379, None)
    return r


# ─── Behavioral Tests per public method (26+ methods) ───────────────


@pytest.mark.asyncio
async def test_select_graph(repo, mock_falkordb):
    mock_client, mock_graph = mock_falkordb
    res = await repo.select_graph()
    assert res == mock_graph
    mock_client.select_graph.assert_called_with("claude_memory")


@pytest.mark.asyncio
async def test_ensure_indices(repo):
    # Should be a no-op
    await repo.ensure_indices()


@pytest.mark.asyncio
async def test_create_node(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "n1", "name": "test"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.create_node("Concept", {"id": "n1", "name": "test"})
    assert res == {"id": "n1", "name": "test"}
    mock_graph.query.assert_awaited_once()
    assert mock_graph.query.call_args[0][0] == CREATE_NODE.format(label="Concept")


@pytest.mark.asyncio
async def test_get_node_found(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "n1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_node("n1")
    assert res == {"id": "n1"}
    mock_graph.query.assert_awaited_once_with(GET_NODE_BY_ID, {"id": "n1"})


@pytest.mark.asyncio
async def test_get_node_not_found(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([])

    res = await repo.get_node("n2")
    assert res is None


@pytest.mark.asyncio
async def test_update_node_success(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "n1", "val": 2})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.update_node("n1", {"val": 2})
    assert res == {"id": "n1", "val": 2}
    mock_graph.query.assert_awaited_once_with(UPDATE_NODE, {"id": "n1", "props": {"val": 2}})


@pytest.mark.asyncio
async def test_update_node_empty(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([])

    res = await repo.update_node("n1", {"val": 2})
    assert res == {}


@pytest.mark.asyncio
async def test_delete_node_soft(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([[1]])

    res = await repo.delete_node("n1", soft_delete=True, reason="test")
    assert res is True
    mock_graph.query.assert_awaited_once_with(SOFT_DELETE_NODE, {"id": "n1", "reason": "test"})


@pytest.mark.asyncio
async def test_delete_node_hard(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    res = await repo.delete_node("n1", soft_delete=False)
    assert res is True
    mock_graph.query.assert_awaited_once_with(HARD_DELETE_NODE, {"id": "n1"})


@pytest.mark.asyncio
async def test_create_edge(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_edge = MagicMock()
    mock_edge.properties = {"confidence": 0.9}
    mock_graph.query.return_value = _make_mock_result([[mock_edge]])

    res = await repo.create_edge("n1", "n2", "RELATED_TO", {"confidence": 0.9})
    assert res == {"confidence": 0.9}
    mock_graph.query.assert_awaited_once_with(
        CREATE_EDGE.format(relation_type="RELATED_TO"),
        {"from": "n1", "to": "n2", "props": {"confidence": 0.9}},
    )


@pytest.mark.asyncio
async def test_create_edge_empty(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([])

    res = await repo.create_edge("n1", "n2", "RELATED_TO", {})
    assert res == {}


@pytest.mark.asyncio
async def test_delete_edge(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    res = await repo.delete_edge("e1")
    assert res is True
    mock_graph.query.assert_awaited_once_with(DELETE_EDGE, {"id": "e1"})


@pytest.mark.asyncio
async def test_execute_cypher(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = "raw_result"

    res = await repo.execute_cypher("MATCH (n) RETURN n", {"x": 1})
    assert res == "raw_result"
    mock_graph.query.assert_awaited_once_with("MATCH (n) RETURN n", {"x": 1})


@pytest.mark.asyncio
async def test_query_timeline_no_project(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "e1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.query_timeline("2026-01-01", "2026-01-02", limit=5)
    assert res == [{"id": "e1"}]
    mock_graph.query.assert_awaited_once_with(
        QUERY_TIMELINE,
        {"start": "2026-01-01", "end": "2026-01-02", "limit": 5},
    )


@pytest.mark.asyncio
async def test_query_timeline_with_project(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "e1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.query_timeline("2026-01-01", "2026-01-02", limit=5, project_id="p1")
    assert res == [{"id": "e1"}]
    mock_graph.query.assert_awaited_once_with(
        QUERY_TIMELINE_WITH_PROJECT,
        {"start": "2026-01-01", "end": "2026-01-02", "limit": 5, "project_id": "p1"},
    )


@pytest.mark.asyncio
async def test_get_temporal_neighbors_before(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "e1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_temporal_neighbors("n1", direction="before", limit=5)
    assert res == [{"id": "e1"}]
    mock_graph.query.assert_awaited_once_with(
        GET_TEMPORAL_NEIGHBORS_BEFORE,
        {"entity_id": "n1", "limit": 5},
    )


@pytest.mark.asyncio
async def test_get_temporal_neighbors_after(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "e1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_temporal_neighbors("n1", direction="after", limit=5)
    assert res == [{"id": "e1"}]
    mock_graph.query.assert_awaited_once_with(
        GET_TEMPORAL_NEIGHBORS_AFTER,
        {"entity_id": "n1", "limit": 5},
    )


@pytest.mark.asyncio
async def test_get_temporal_neighbors_both(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "e1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_temporal_neighbors("n1", direction="both", limit=5)
    assert res == [{"id": "e1"}]
    mock_graph.query.assert_awaited_once_with(
        GET_TEMPORAL_NEIGHBORS_BOTH,
        {"entity_id": "n1", "limit": 5},
    )


@pytest.mark.asyncio
async def test_create_temporal_edge(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([["PRECEDED_BY", "n1", "n2"]])

    res = await repo.create_temporal_edge("n1", "n2", "PRECEDED_BY", {"weight": 1.0})
    assert res == {"rel_type": "PRECEDED_BY", "from_id": "n1", "to_id": "n2"}
    mock_graph.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_temporal_edge_empty(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([])

    res = await repo.create_temporal_edge("n1", "n2")
    assert "error" in res


@pytest.mark.asyncio
async def test_get_bottles(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "b1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_bottles(
        limit=5, search_text="hello", before_date="2026", after_date="2025", project_id="p1"
    )
    assert res == [{"id": "b1"}]
    mock_graph.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_graph_health(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    # Mock return values for counts: total, entity, obs, edges, orphans
    mock_graph.query.side_effect = [
        _make_mock_result([[10]]),  # total nodes
        _make_mock_result([[6]]),  # entity
        _make_mock_result([[4]]),  # obs
        _make_mock_result([[15]]),  # edges
        _make_mock_result([[2]]),  # orphans
    ]

    res = await repo.get_graph_health()
    assert res["total_nodes"] == 10
    assert res["entity_count"] == 6
    assert res["observation_count"] == 4
    assert res["total_edges"] == 15
    assert res["orphan_count"] == 2
    assert res["density"] == round(15 / 90, 6)
    assert res["avg_degree"] == 1.5


@pytest.mark.asyncio
async def test_list_orphans(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result(
        [["n1", "name", "Concept", "p1", True, ["Entity"], "2026"]]
    )

    res = await repo.list_orphans(limit=5)
    assert len(res) == 1
    assert res[0]["id"] == "n1"


@pytest.mark.asyncio
async def test_get_all_edges(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([["n1", "n2", "RELATED_TO"]])

    res = await repo.get_all_edges()
    assert res == [{"source": "n1", "target": "n2", "type": "RELATED_TO"}]


@pytest.mark.asyncio
async def test_get_all_node_ids(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([["n1"], ["n2"]])

    res = await repo.get_all_node_ids(limit=5)
    assert res == ["n1", "n2"]


@pytest.mark.asyncio
async def test_get_observations_for_entity(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"content": "obs1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_observations_for_entity("n1", limit=5)
    assert res == [{"content": "obs1"}]


@pytest.mark.asyncio
async def test_get_subgraph_depth_zero(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([[[{"properties": {"id": "n1"}}]]])

    res = await repo.get_subgraph(["n1"], depth=0)
    assert res["nodes"] == [{"id": "n1"}]
    assert res["edges"] == []


@pytest.mark.asyncio
async def test_get_subgraph_depth_one(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    edges = [{"id": "e1", "source": "n1", "target": "n2", "type": "RELATED_TO", "properties": {}}]
    nodes = [
        {"id": "n1", "labels": ["Entity"], "properties": {"id": "n1"}},
        {"id": "n2", "labels": ["Entity"], "properties": {"id": "n2"}},
    ]
    mock_graph.query.return_value = _make_mock_result([[edges, nodes]])

    res = await repo.get_subgraph(["n1"], depth=1)
    assert len(res["nodes"]) == 2
    assert len(res["edges"]) == 1


@pytest.mark.asyncio
async def test_get_all_nodes(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "n1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_all_nodes(limit=5)
    assert res == [{"id": "n1"}]


@pytest.mark.asyncio
async def test_get_total_node_count(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([[42]])

    res = await repo.get_total_node_count()
    assert res == 42


@pytest.mark.asyncio
async def test_increment_salience(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = _make_mock_result([["n1", 2.5, 3]])

    res = await repo.increment_salience(["n1"])
    assert res == [{"id": "n1", "salience_score": 2.5, "retrieval_count": 3}]


@pytest.mark.asyncio
async def test_get_most_recent_entity(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_node = _make_mock_node({"id": "n1"})
    mock_graph.query.return_value = _make_mock_result([[mock_node]])

    res = await repo.get_most_recent_entity("p1")
    assert res == {"id": "n1"}


@pytest.mark.asyncio
async def test_shortest_path_length_forward(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.side_effect = [
        _make_mock_result([[3]]),  # forward
    ]

    res = await repo.shortest_path_length("n1", "n2")
    assert res == 3


@pytest.mark.asyncio
async def test_shortest_path_length_reverse(repo, mock_falkordb):
    _, mock_graph = mock_falkordb
    mock_graph.query.side_effect = [
        Exception("forward failed"),  # forward
        _make_mock_result([[4]]),  # reverse
    ]

    res = await repo.shortest_path_length("n1", "n2")
    assert res == 4


# ─── Contract & Exception Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_search_error_propagates_on_falkordb_failure(repo, mock_falkordb):
    """When falkordb.asyncio raises, SearchError contract is preserved."""
    _, mock_graph = mock_falkordb
    mock_graph.query.side_effect = RedisConnectionError("falkordb down")

    with pytest.raises(SearchError):
        await repo.get_node("n1")


# ─── Connection & Retry Logic Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_connect_with_retry_success(mock_falkordb):
    mock_client, _ = mock_falkordb
    mock_client.list_graphs.return_value = []

    with patch("claude_memory.repository_async.FalkorDB", return_value=mock_client):
        repo = AsyncMemoryRepository("localhost", 6379, None)
        await repo._connect_with_retry()

    assert repo._connected is True
    mock_client.list_graphs.assert_called_once()


@pytest.mark.asyncio
async def test_connect_with_retry_failure_then_success(mock_falkordb):
    mock_client, _ = mock_falkordb
    # Fail twice, then succeed
    mock_client.list_graphs.side_effect = [
        RedisConnectionError("temp error"),
        RedisConnectionError("temp error 2"),
        [],
    ]

    with patch("claude_memory.repository_async.FalkorDB", return_value=mock_client):
        repo = AsyncMemoryRepository("localhost", 6379, None)
        repo._connect_backoff = 0.001  # speed up test
        await repo._connect_with_retry()

    assert repo._connected is True
    assert mock_client.list_graphs.call_count == 3


@pytest.mark.asyncio
async def test_connect_with_retry_exhausted(mock_falkordb):
    mock_client, _ = mock_falkordb
    mock_client.list_graphs.side_effect = RedisConnectionError("down")

    with patch("claude_memory.repository_async.FalkorDB", return_value=mock_client):
        repo = AsyncMemoryRepository("localhost", 6379, None)
        repo._connect_backoff = 0.001
        with pytest.raises(ConnectionError, match="FalkorDB connection exhausted retries"):
            await repo._connect_with_retry()

    assert repo._connected is False
