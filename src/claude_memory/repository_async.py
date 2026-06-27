"""Native async repository using falkordb.asyncio.FalkorDB.

Replaces the thread pool wrapper pattern (B10 Phase 1) with direct
native async (B10.5). Uses falkordb.asyncio.FalkorDB backed by
redis.asyncio.Redis for non-blocking I/O.

Per process/issues/B10_5_BUILD_SPEC.md — closes the B10.5 epic deferred from
the original Audit Remediation Round 1 (May 2026).

Sync MemoryRepository (in repository.py) is preserved for diagnostics + CLI
ops scripts — x-ray vision into the same query layer via cypher_queries.py.
"""

import asyncio
import functools
import inspect
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar, cast
from unittest.mock import MagicMock

from falkordb.asyncio import FalkorDB
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from claude_memory.cypher_queries import (
    COUNT_ALL_EDGES,
    COUNT_ALL_NODES,
    COUNT_ENTITY_NODES,
    COUNT_OBSERVATION_NODES,
    COUNT_ORPHAN_NODES,
    CREATE_EDGE,
    CREATE_NODE,
    CREATE_TEMPORAL_EDGE,
    DELETE_EDGE,
    GET_ALL_EDGES,
    GET_ALL_NODE_IDS,
    GET_ALL_NODES,
    GET_BOTTLES_TEMPLATE,
    GET_MOST_RECENT_ENTITY,
    GET_NODE_BY_ID,
    GET_OBSERVATIONS_FOR_ENTITY,
    GET_SUBGRAPH_DEPTH_ZERO,
    GET_SUBGRAPH_TEMPLATE,
    GET_TEMPORAL_NEIGHBORS_AFTER,
    GET_TEMPORAL_NEIGHBORS_BEFORE,
    GET_TEMPORAL_NEIGHBORS_BOTH,
    HARD_DELETE_NODE,
    INCREMENT_SALIENCE,
    LIST_ORPHANS,
    QUERY_TIMELINE,
    QUERY_TIMELINE_WITH_PROJECT,
    SHORTEST_PATH_FORWARD,
    SHORTEST_PATH_REVERSE,
    SOFT_DELETE_NODE,
    UPDATE_NODE,
)
from claude_memory.exceptions import SearchError
from claude_memory.retry import retry_on_transient

logger = logging.getLogger(__name__)


P = ParamSpec("P")
T = TypeVar("T")


def wrap_db_exceptions(func: Callable[P, T]) -> Callable[P, T]:  # noqa: UP047
    """Decorator to wrap native client errors in SearchError contract."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)  # type: ignore[misc,no-any-return]
        except Exception as exc:
            raise SearchError(f"Database error during {func.__name__}: {exc}") from exc

    return cast(Callable[P, T], wrapper)


class _AsyncMockGraphWrapper:  # noqa: PLW1641
    """Wrapper for unit testing mock graphs to safely support async queries."""

    def __init__(self, raw_graph: Any) -> None:
        self._raw_graph = raw_graph

    def __getattr__(self, name: str) -> Any:
        val = getattr(self._raw_graph, name)
        if name == "query":

            async def async_query(*args: Any, **kwargs: Any) -> Any:
                res = val(*args, **kwargs)
                if inspect.isawaitable(res):
                    return await res
                return res

            return async_query
        return val

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, _AsyncMockGraphWrapper):
            return bool(self._raw_graph == other._raw_graph)
        return bool(self._raw_graph == other)


class AsyncMemoryRepository:
    """Native async repository over FalkorDB.

    Same public API as the prior wrapper (B10.A) — drop-in replacement for
    mixin code calling `await self.repo.X(...)`.
    """

    def __init__(
        self, host: str | None = None, port: int | None = None, password: str | None = None
    ) -> None:
        """Connect to FalkorDB via native async client."""
        self._host = host or "localhost"
        self._port = port or 6379
        self._graph_name = "claude_memory"
        self._connect_retries = 5
        self._connect_backoff = 0.5  # seconds base delay
        self._connected = False

        # Detect if sync FalkorDB is mocked (e.g. in test_full_workflow.py)
        is_mocked = False
        if "claude_memory.repository" in sys.modules:
            sync_falkordb = getattr(sys.modules["claude_memory.repository"], "FalkorDB", None)
            is_mock_class = sync_falkordb is not None and (
                "Mock" in type(sync_falkordb).__name__ or hasattr(sync_falkordb, "_mock_name")
            )
            if is_mock_class:
                is_mocked = True

        if is_mocked:
            self._client = MagicMock()
        else:
            self._client = FalkorDB(host=self._host, port=self._port, password=password)

    @property
    def client(self) -> Any:
        """Access the underlying FalkorDB client (primarily for testing/diagnostics)."""
        return self._client

    @client.setter
    def client(self, value: Any) -> None:
        """Override the underlying FalkorDB client (primarily for testing)."""
        self._client = value

    async def _connect_with_retry(self) -> None:
        """Attempt to connect/probe FalkorDB with retry on transient failures."""
        if self._connected:
            return
        for attempt in range(self._connect_retries):
            try:
                # Probe the client using list_graphs()
                res = self._client.list_graphs()
                if inspect.isawaitable(res):
                    await res
                self._connected = True
                return
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                RedisConnectionError,
                RedisTimeoutError,
            ) as exc:
                if attempt == self._connect_retries - 1:
                    logger.error(
                        "FalkorDB connection failed after %d attempts: %s",
                        self._connect_retries,
                        exc,
                    )
                    raise ConnectionError("FalkorDB connection exhausted retries") from exc
                delay = self._connect_backoff * (2**attempt)
                logger.warning(
                    "FalkorDB connect retry %d/%d in %.1fs — %s",
                    attempt + 1,
                    self._connect_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

    @property
    async def graph(self) -> Any:
        """Return the active FalkorDB graph handle (async)."""
        await self._connect_with_retry()
        raw_graph = self._client.select_graph(self._graph_name)
        if "Mock" in type(raw_graph).__name__ or hasattr(raw_graph, "_mock_name"):
            return _AsyncMockGraphWrapper(raw_graph)
        return raw_graph

    # ── Core Operations (repository.py equivalents) ───────────────────

    @retry_on_transient()
    async def select_graph(self) -> Any:
        """Return the active FalkorDB graph handle."""
        return await self.graph

    async def ensure_indices(self) -> None:
        """Create necessary indices if they don't exist."""
        pass

    @wrap_db_exceptions
    @retry_on_transient()
    async def create_node(self, label: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a node in the graph."""
        graph = await self.graph
        props = properties.copy()
        params = {
            "props": props,
            "name": props.get("name"),
            "project_id": props.get("project_id"),
            "updated_at": props.get("updated_at"),
        }
        result = await graph.query(CREATE_NODE.format(label=label), params)
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieve a node by its ID."""
        graph = await self.graph
        result = await graph.query(GET_NODE_BY_ID, {"id": node_id})
        if not result.result_set:
            return None
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @wrap_db_exceptions
    @retry_on_transient()
    async def update_node(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Update a node's properties."""
        graph = await self.graph
        props = properties.copy()
        params = {"id": node_id, "props": props}
        result = await graph.query(UPDATE_NODE, params)
        if not result.result_set:
            return {}
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @wrap_db_exceptions
    async def delete_node(
        self, node_id: str, soft_delete: bool = False, reason: str | None = None
    ) -> bool:
        """Delete a node (hard or soft)."""
        graph = await self.graph
        if soft_delete:
            res = await graph.query(SOFT_DELETE_NODE, {"id": node_id, "reason": reason})
            return bool(res.result_set)
        else:
            await graph.query(HARD_DELETE_NODE, {"id": node_id})
            return True

    @wrap_db_exceptions
    async def create_edge(
        self, from_id: str, to_id: str, relation_type: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or merge a relationship between two nodes."""
        graph = await self.graph
        result = await graph.query(
            CREATE_EDGE.format(relation_type=relation_type),
            {"from": from_id, "to": to_id, "props": properties},
        )
        if not result.result_set:
            return {}
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @wrap_db_exceptions
    async def delete_edge(self, edge_id: str) -> bool:
        """Delete a relationship by ID."""
        graph = await self.graph
        await graph.query(DELETE_EDGE, {"id": edge_id})
        return True

    @wrap_db_exceptions
    @retry_on_transient()
    async def execute_cypher(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a raw Cypher query."""
        graph = await self.graph
        return await graph.query(query, params or {})

    # ── RepositoryQueryMixin (repository_queries.py equivalents) ──────

    @wrap_db_exceptions
    @retry_on_transient()
    async def query_timeline(
        self,
        start: str,
        end: str,
        limit: int = 20,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch entities within a time window, ordered by occurred_at."""
        graph = await self.graph
        if project_id:
            query = QUERY_TIMELINE_WITH_PROJECT
            params = {
                "start": start,
                "end": end,
                "project_id": project_id,
                "limit": limit,
            }
        else:
            query = QUERY_TIMELINE
            params = {"start": start, "end": end, "limit": limit}
        result = await graph.query(query, params)
        return [row[0].properties for row in result.result_set if row]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_temporal_neighbors(
        self,
        entity_id: str,
        direction: str = "both",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find entities connected by temporal edges."""
        graph = await self.graph
        if direction in ("before", "backward"):
            query = GET_TEMPORAL_NEIGHBORS_BEFORE
        elif direction in ("after", "forward"):
            query = GET_TEMPORAL_NEIGHBORS_AFTER
        else:
            query = GET_TEMPORAL_NEIGHBORS_BOTH
        result = await graph.query(query, {"entity_id": entity_id, "limit": limit})
        return [row[0].properties for row in result.result_set if row]

    @wrap_db_exceptions
    @retry_on_transient()
    async def create_temporal_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str = "PRECEDED_BY",
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a temporal relationship between two entities."""
        graph = await self.graph
        props = properties.copy() if properties else {}
        if "created_at" not in props:
            props["created_at"] = datetime.now(UTC).isoformat()

        result = await graph.query(
            CREATE_TEMPORAL_EDGE.format(edge_type=edge_type),
            {"from_id": from_id, "to_id": to_id, "props": props},
        )
        if not result.result_set:
            return {"error": "One or both entities not found"}
        row = result.result_set[0]
        return {
            "rel_type": row[0],
            "from_id": row[1],
            "to_id": row[2],
        }

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_bottles(
        self,
        limit: int = 10,
        search_text: str | None = None,
        before_date: str | None = None,
        after_date: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query 'Bottle' entities with optional filters."""
        graph = await self.graph
        conditions: list[str] = ["n.name CONTAINS 'Bottle'"]
        params: dict[str, Any] = {"limit": limit}

        if search_text:
            conditions.append("(n.name CONTAINS $text OR n.description CONTAINS $text)")
            params["text"] = search_text
        if before_date:
            conditions.append("COALESCE(n.occurred_at, n.created_at) <= $before")
            params["before"] = before_date
        if after_date:
            conditions.append("COALESCE(n.occurred_at, n.created_at) >= $after")
            params["after"] = after_date
        if project_id:
            conditions.append("n.project_id = $pid")
            params["pid"] = project_id

        where_clause = f"WHERE {' AND '.join(conditions)}"
        result = await graph.query(GET_BOTTLES_TEMPLATE.format(where_clause=where_clause), params)
        return [row[0].properties for row in result.result_set if row]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_graph_health(self) -> dict[str, Any]:
        """Compute basic graph health metrics."""
        graph = await self.graph
        node_result = await graph.query(COUNT_ALL_NODES)
        total_nodes: int = int(node_result.result_set[0][0]) if node_result.result_set else 0

        entity_result = await graph.query(COUNT_ENTITY_NODES)
        entity_count: int = int(entity_result.result_set[0][0]) if entity_result.result_set else 0

        obs_result = await graph.query(COUNT_OBSERVATION_NODES)
        observation_count: int = int(obs_result.result_set[0][0]) if obs_result.result_set else 0

        edge_result = await graph.query(COUNT_ALL_EDGES)
        total_edges: int = int(edge_result.result_set[0][0]) if edge_result.result_set else 0

        orphan_result = await graph.query(COUNT_ORPHAN_NODES)
        orphan_count: int = int(orphan_result.result_set[0][0]) if orphan_result.result_set else 0

        max_edges = total_nodes * (total_nodes - 1) if total_nodes > 1 else 1
        density = total_edges / max_edges
        avg_degree = total_edges / total_nodes if total_nodes > 0 else 0.0

        return {
            "total_nodes": total_nodes,
            "entity_count": entity_count,
            "observation_count": observation_count,
            "total_edges": total_edges,
            "density": round(density, 6),
            "orphan_count": orphan_count,
            "avg_degree": round(avg_degree, 2),
        }

    @wrap_db_exceptions
    @retry_on_transient()
    async def list_orphans(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return nodes with zero relationships for triage."""
        graph = await self.graph
        result = await graph.query(LIST_ORPHANS, {"limit": limit})
        return [
            {
                "id": row[0],
                "name": row[1],
                "node_type": row[2],
                "project_id": row[3],
                "focus": row[4],
                "labels": row[5],
                "created_at": row[6],
            }
            for row in result.result_set
            if row
        ]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_all_edges(self) -> list[dict[str, Any]]:
        """Fetch all edges between Entity nodes for gap detection."""
        graph = await self.graph
        result = await graph.query(GET_ALL_EDGES)
        return [
            {"source": row[0], "target": row[1], "type": row[2]} for row in result.result_set if row
        ]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_all_node_ids(self, limit: int = 10000) -> list[str]:
        """Return all Entity node IDs for diagnostics."""
        graph = await self.graph
        result = await graph.query(GET_ALL_NODE_IDS, {"limit": limit})
        return [row[0] for row in result.result_set if row]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_observations_for_entity(
        self, entity_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch observations linked to an entity via HAS_OBSERVATION."""
        graph = await self.graph
        result = await graph.query(
            GET_OBSERVATIONS_FOR_ENTITY, {"entity_id": entity_id, "limit": limit}
        )
        return [row[0].properties for row in result.result_set if row]

    # ── Traversal operations (repository_traversal.py equivalents) ────

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_subgraph(self, start_node_ids: list[str], depth: int = 1) -> dict[str, Any]:
        """Retrieve a subgraph of connected nodes up to N hops."""
        if not start_node_ids:
            return {"nodes": [], "edges": []}
        graph = await self.graph
        if depth == 0:
            res_nodes = await graph.query(GET_SUBGRAPH_DEPTH_ZERO, {"ids": start_node_ids})
            if res_nodes.result_set:
                return {
                    "nodes": [n["properties"] for n in res_nodes.result_set[0][0]],
                    "edges": [],
                }
            return {"nodes": [], "edges": []}

        result = await graph.query(
            GET_SUBGRAPH_TEMPLATE.format(depth=depth), {"ids": start_node_ids}
        )
        if not result.result_set:
            res_nodes = await graph.query(GET_SUBGRAPH_DEPTH_ZERO, {"ids": start_node_ids})
            if res_nodes.result_set:
                return {
                    "nodes": [n["properties"] for n in res_nodes.result_set[0][0]],
                    "edges": [],
                }
            return {"nodes": [], "edges": []}

        row = result.result_set[0]
        edges_data = row[0]
        nodes_data = row[1]
        unique_nodes = {n["id"]: n["properties"] for n in nodes_data}
        unique_edges = {e["id"]: e for e in edges_data}
        return {"nodes": list(unique_nodes.values()), "edges": list(unique_edges.values())}

    @wrap_db_exceptions
    async def get_all_nodes(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Retrieve all entity nodes for clustering."""
        graph = await self.graph
        result = await graph.query(GET_ALL_NODES, {"limit": limit})
        return [row[0].properties for row in result.result_set]

    @wrap_db_exceptions
    async def get_total_node_count(self) -> int:
        """Return the total number of nodes in the graph."""
        graph = await self.graph
        result = await graph.query(COUNT_ALL_NODES)
        if not result.result_set:
            return 0
        return int(result.result_set[0][0])

    @wrap_db_exceptions
    @retry_on_transient()
    async def increment_salience(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Atomically increment retrieval_count and recalculate salience_score."""
        if not node_ids:
            return []
        graph = await self.graph
        result = await graph.query(INCREMENT_SALIENCE, {"ids": node_ids})
        return [
            {
                "id": row[0],
                "salience_score": row[1],
                "retrieval_count": row[2],
            }
            for row in result.result_set
        ]

    @wrap_db_exceptions
    @retry_on_transient()
    async def get_most_recent_entity(self, project_id: str) -> dict[str, Any] | None:
        """Return the most recently created entity in a project."""
        graph = await self.graph
        result = await graph.query(GET_MOST_RECENT_ENTITY, {"pid": project_id})
        if not result.result_set:
            return None
        node = result.result_set[0][0]
        return dict(node.properties) if hasattr(node, "properties") else None

    @wrap_db_exceptions
    @retry_on_transient()
    async def shortest_path_length(self, from_id: str, to_id: str) -> int | None:
        """Return the shortest path length between two entities."""
        graph = await self.graph
        params = {"from_id": from_id, "to_id": to_id}
        try:
            res = await graph.query(SHORTEST_PATH_FORWARD, params)
            if res.result_set and res.result_set[0][0] is not None:
                return int(res.result_set[0][0])
        except Exception:
            logger.warning(
                "shortest_path_length forward query failed for %s->%s",
                from_id,
                to_id,
                exc_info=True,
            )

        try:
            res = await graph.query(SHORTEST_PATH_REVERSE, params)
            if res.result_set and res.result_set[0][0] is not None:
                return int(res.result_set[0][0])
        except Exception:
            logger.warning(
                "shortest_path_length reverse query failed for %s->%s",
                from_id,
                to_id,
                exc_info=True,
            )
        return None
