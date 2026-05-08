"""Tests for AsyncMemoryRepository (B10.A).

Verifies:
- Every async method delegates to the correct sync method via asyncio.to_thread
- Arguments are forwarded correctly (no signature mismatches)
- Exceptions propagate transparently through the wrapper
- None/empty returns are forwarded without mangling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.repository_async import AsyncMemoryRepository


@pytest.fixture()
def sync_repo() -> MagicMock:
    """Create a mock MemoryRepository with all public methods."""
    repo = MagicMock()
    # Set default return values for methods that return specific types
    repo.create_node.return_value = {"id": "abc-123", "name": "Test"}
    repo.get_node.return_value = {"id": "abc-123", "name": "Test"}
    repo.update_node.return_value = {"id": "abc-123", "name": "Updated"}
    repo.delete_node.return_value = True
    repo.create_edge.return_value = {"id": "edge-1"}
    repo.delete_edge.return_value = True
    repo.execute_cypher.return_value = MagicMock(result_set=[])
    repo.query_timeline.return_value = [{"id": "e1"}]
    repo.get_temporal_neighbors.return_value = [{"id": "e2"}]
    repo.create_temporal_edge.return_value = {"rel_type": "PRECEDED_BY"}
    repo.get_bottles.return_value = [{"id": "bottle-1"}]
    repo.get_graph_health.return_value = {"total_nodes": 42}
    repo.list_orphans.return_value = [{"id": "orphan-1"}]
    repo.get_all_edges.return_value = [{"source": "a", "target": "b"}]
    repo.get_all_node_ids.return_value = ["id-1", "id-2"]
    repo.get_observations_for_entity.return_value = [{"content": "obs"}]
    repo.get_subgraph.return_value = {"nodes": [], "edges": []}
    repo.get_all_nodes.return_value = [{"id": "n1"}]
    repo.get_total_node_count.return_value = 100
    repo.increment_salience.return_value = [{"id": "n1", "salience_score": 2.0}]
    repo.get_most_recent_entity.return_value = {"id": "recent-1"}
    repo.shortest_path_length.return_value = 3
    repo.select_graph.return_value = MagicMock()
    repo.ensure_indices.return_value = None
    return repo


@pytest.fixture()
def wrapper(sync_repo: MagicMock) -> AsyncMemoryRepository:
    """Create an AsyncMemoryRepository wrapping the mock."""
    return AsyncMemoryRepository(sync_repo)


# ── Parameterized delegation tests ────────────────────────────────────
# One entry per public method: (method_name, args, kwargs)
# Verifies asyncio.to_thread is called with the right delegate + args.

_DELEGATION_CASES = [
    # ── repository.py core ──
    ("select_graph", (), {}),
    ("ensure_indices", (), {}),
    ("create_node", ("Entity", {"name": "X"}), {}),
    ("get_node", ("abc-123",), {}),
    ("update_node", ("abc-123", {"name": "Y"}), {}),
    ("delete_node", ("abc-123", False, None), {}),
    ("delete_node", ("abc-123", True, "stale"), {}),
    ("create_edge", ("a", "b", "RELATES_TO", {"weight": 1.0}), {}),
    ("delete_edge", ("edge-1",), {}),
    ("execute_cypher", ("MATCH (n) RETURN n", None), {}),
    ("execute_cypher", ("MATCH (n) RETURN n", {"id": "x"}), {}),
    # ── repository_queries.py ──
    ("query_timeline", ("2026-01-01", "2026-12-31", 20, None), {}),
    ("query_timeline", ("2026-01-01", "2026-12-31", 10, "proj-1"), {}),
    ("get_temporal_neighbors", ("entity-1", "both", 10), {}),
    ("get_temporal_neighbors", ("entity-1", "before", 5), {}),
    ("create_temporal_edge", ("a", "b", "PRECEDED_BY", None), {}),
    ("create_temporal_edge", ("a", "b", "EVOLVED_FROM", {"ts": "now"}), {}),
    ("get_bottles", (10, None, None, None, None), {}),
    ("get_bottles", (5, "search", None, None, "proj"), {}),
    ("get_graph_health", (), {}),
    ("list_orphans", (50,), {}),
    ("list_orphans", (100,), {}),
    ("get_all_edges", (), {}),
    ("get_all_node_ids", (10000,), {}),
    ("get_all_node_ids", (500,), {}),
    ("get_observations_for_entity", ("entity-1", 20), {}),
    ("get_observations_for_entity", ("entity-1", 50), {}),
    # ── repository_traversal.py ──
    ("get_subgraph", (["id-1", "id-2"], 1), {}),
    ("get_subgraph", (["id-1"], 3), {}),
    ("get_all_nodes", (1000,), {}),
    ("get_all_nodes", (2000,), {}),
    ("get_total_node_count", (), {}),
    ("increment_salience", (["id-1", "id-2"],), {}),
    ("get_most_recent_entity", ("proj-1",), {}),
    ("shortest_path_length", ("a", "b"), {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    _DELEGATION_CASES,
    ids=[f"{c[0]}({','.join(str(a) for a in c[1])})" for c in _DELEGATION_CASES],
)
async def test_happy_delegation(
    sync_repo: MagicMock,
    wrapper: AsyncMemoryRepository,
    method_name: str,
    args: tuple,
    kwargs: dict,
) -> None:
    """B10.A: each async method delegates to the correct sync method via to_thread."""
    sync_method = getattr(sync_repo, method_name)
    expected_return = sync_method.return_value

    with patch(
        "claude_memory.repository_async.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_tt:
        mock_tt.return_value = expected_return
        async_method = getattr(wrapper, method_name)
        result = await async_method(*args, **kwargs)

    mock_tt.assert_awaited_once_with(sync_method, *args, **kwargs)
    assert result == expected_return


# ── Evil path: exceptions propagate through asyncio.to_thread ─────────

_EXCEPTION_CASES = [
    ("create_node", ("Entity", {"name": "X"}), ConnectionError("FalkorDB down")),
    ("execute_cypher", ("BAD CYPHER",), RuntimeError("Syntax error")),
    ("get_node", ("missing",), TimeoutError("DB timeout")),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "exc"),
    _EXCEPTION_CASES,
    ids=[f"evil1_{c[0]}_{type(c[2]).__name__}" for c in _EXCEPTION_CASES],
)
async def test_evil1_exception_propagation(
    sync_repo: MagicMock,
    wrapper: AsyncMemoryRepository,
    method_name: str,
    args: tuple,
    exc: Exception,
) -> None:
    """B10.A evil: sync exceptions propagate transparently through the wrapper."""
    with patch(
        "claude_memory.repository_async.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_tt:
        mock_tt.side_effect = exc
        with pytest.raises(type(exc), match=str(exc)):
            await getattr(wrapper, method_name)(*args)


@pytest.mark.asyncio
async def test_evil2_wrong_sync_repo_type() -> None:
    """B10.A evil: constructing with a non-repo object stores it but fails on call."""
    fake = MagicMock(spec=[])  # empty spec — no methods
    wrapper = AsyncMemoryRepository(fake)
    # The wrapper stores whatever you give it — failure surfaces at call time
    assert wrapper._sync_repo is fake


@pytest.mark.asyncio
async def test_evil3_concurrent_calls_do_not_interfere(
    sync_repo: MagicMock,
    wrapper: AsyncMemoryRepository,
) -> None:
    """B10.A evil: concurrent async calls to different methods don't cross-contaminate."""
    sync_repo.get_node.return_value = {"id": "node-1"}
    sync_repo.get_graph_health.return_value = {"total_nodes": 5}

    with patch(
        "claude_memory.repository_async.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_tt:
        # Make to_thread return the correct value based on which sync method is called
        async def side_effect(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        mock_tt.side_effect = side_effect

        results = await asyncio.gather(
            wrapper.get_node("node-1"),
            wrapper.get_graph_health(),
        )

    assert results[0] == {"id": "node-1"}
    assert results[1] == {"total_nodes": 5}


# ── Sad path: None/empty returns forwarded correctly ──────────────────


@pytest.mark.asyncio
async def test_sad1_none_return_forwarded(
    sync_repo: MagicMock,
    wrapper: AsyncMemoryRepository,
) -> None:
    """B10.A sad: when sync repo returns None, wrapper returns None (not swallowed)."""
    with patch(
        "claude_memory.repository_async.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_tt:
        mock_tt.return_value = None
        result = await wrapper.get_node("nonexistent")

    assert result is None


# ── Happy path: wrapper stores sync_repo correctly ────────────────────


def test_happy_init_stores_sync_repo(sync_repo: MagicMock) -> None:
    """B10.A happy: wrapper stores the sync repo as _sync_repo."""
    wrapper = AsyncMemoryRepository(sync_repo)
    assert wrapper._sync_repo is sync_repo


@pytest.mark.asyncio
async def test_happy_full_roundtrip(
    sync_repo: MagicMock,
    wrapper: AsyncMemoryRepository,
) -> None:
    """B10.A happy: create → read → update → delete roundtrip through wrapper."""
    with patch(
        "claude_memory.repository_async.asyncio.to_thread", new_callable=AsyncMock
    ) as mock_tt:
        # Create
        mock_tt.return_value = {"id": "new-1", "name": "Test"}
        created = await wrapper.create_node("Entity", {"name": "Test"})
        assert created["id"] == "new-1"

        # Read
        mock_tt.return_value = {"id": "new-1", "name": "Test"}
        found = await wrapper.get_node("new-1")
        assert found["id"] == "new-1"

        # Update
        mock_tt.return_value = {"id": "new-1", "name": "Updated"}
        updated = await wrapper.update_node("new-1", {"name": "Updated"})
        assert updated["name"] == "Updated"

        # Delete
        mock_tt.return_value = True
        deleted = await wrapper.delete_node("new-1")
        assert deleted is True
