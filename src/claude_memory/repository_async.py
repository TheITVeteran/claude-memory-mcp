"""Async wrapper around the synchronous MemoryRepository.

PHASE 1 (current): Uses ``asyncio.to_thread()`` to defer every sync
FalkorDB call to the default thread-pool executor.  This unblocks
the event loop but limits concurrency to the thread-pool size
(``min(32, os.cpu_count() + 4)`` workers by default).

PHASE 2 (available): FalkorDB Python client v1.4.0 ships a native
async API via ``falkordb.asyncio.FalkorDB`` backed by
``redis.asyncio.Redis``.  Migration path: replace this wrapper with
a direct ``falkordb.asyncio`` repository implementation.
Track upstream: https://github.com/FalkorDB/falkordb-py

The Phase 2 migration is a separate epic (B10.5) — requires new
connection management, retry logic rewrite, and full test
re-validation.  This wrapper is the correct intermediate state.
"""

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from claude_memory.repository import MemoryRepository


class AsyncMemoryRepository:
    """Async facade over :class:`MemoryRepository`.

    Every public method mirrors the sync original, delegating via
    ``asyncio.to_thread`` so the event loop is never blocked by
    FalkorDB I/O.

    Usage during migration (B10.B-E)::

        # MemoryService.__init__
        self.repo = MemoryRepository(...)
        self.async_repo = AsyncMemoryRepository(self.repo)

    Post-migration cleanup (B10.E-cleanup)::

        self.repo = AsyncMemoryRepository(MemoryRepository(...))
    """

    def __init__(self, sync_repo: "MemoryRepository") -> None:
        """Wrap an already-connected sync repository instance."""
        self._sync_repo = sync_repo

    # ── MemoryRepository core (repository.py) ─────────────────────────

    async def select_graph(self) -> Any:
        """Return the active FalkorDB graph handle."""
        return await asyncio.to_thread(self._sync_repo.select_graph)

    async def ensure_indices(self) -> None:
        """Create necessary indices if they don't exist."""
        await asyncio.to_thread(self._sync_repo.ensure_indices)

    async def create_node(self, label: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a node in the graph."""
        return await asyncio.to_thread(self._sync_repo.create_node, label, properties)

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieve a node by its ID."""
        return await asyncio.to_thread(self._sync_repo.get_node, node_id)

    async def update_node(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Update a node's properties."""
        return await asyncio.to_thread(self._sync_repo.update_node, node_id, properties)

    async def delete_node(
        self, node_id: str, soft_delete: bool = False, reason: str | None = None
    ) -> bool:
        """Delete a node (hard or soft)."""
        return await asyncio.to_thread(self._sync_repo.delete_node, node_id, soft_delete, reason)

    async def create_edge(
        self, from_id: str, to_id: str, relation_type: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or merge a relationship between two nodes."""
        return await asyncio.to_thread(
            self._sync_repo.create_edge, from_id, to_id, relation_type, properties
        )

    async def delete_edge(self, edge_id: str) -> bool:
        """Delete a relationship by ID."""
        return await asyncio.to_thread(self._sync_repo.delete_edge, edge_id)

    async def execute_cypher(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a raw Cypher query."""
        return await asyncio.to_thread(self._sync_repo.execute_cypher, query, params)

    # ── RepositoryQueryMixin (repository_queries.py) ──────────────────

    async def query_timeline(
        self,
        start: str,
        end: str,
        limit: int = 20,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch entities within a time window, ordered by occurred_at."""
        return await asyncio.to_thread(
            self._sync_repo.query_timeline, start, end, limit, project_id
        )

    async def get_temporal_neighbors(
        self,
        entity_id: str,
        direction: str = "both",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find entities connected by temporal edges."""
        return await asyncio.to_thread(
            self._sync_repo.get_temporal_neighbors, entity_id, direction, limit
        )

    async def create_temporal_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str = "PRECEDED_BY",
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a temporal relationship between two entities."""
        return await asyncio.to_thread(
            self._sync_repo.create_temporal_edge, from_id, to_id, edge_type, properties
        )

    async def get_bottles(
        self,
        limit: int = 10,
        search_text: str | None = None,
        before_date: str | None = None,
        after_date: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query 'Bottle' entities with optional filters."""
        return await asyncio.to_thread(
            self._sync_repo.get_bottles, limit, search_text, before_date, after_date, project_id
        )

    async def get_graph_health(self) -> dict[str, Any]:
        """Compute basic graph health metrics."""
        return await asyncio.to_thread(self._sync_repo.get_graph_health)

    async def list_orphans(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return nodes with zero relationships for triage."""
        return await asyncio.to_thread(self._sync_repo.list_orphans, limit)

    async def get_all_edges(self) -> list[dict[str, Any]]:
        """Fetch all edges between Entity nodes for gap detection."""
        return await asyncio.to_thread(self._sync_repo.get_all_edges)

    async def get_all_node_ids(self, limit: int = 10000) -> list[str]:
        """Return all Entity node IDs for diagnostics."""
        return await asyncio.to_thread(self._sync_repo.get_all_node_ids, limit)

    async def get_observations_for_entity(
        self, entity_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch observations linked to an entity via HAS_OBSERVATION."""
        return await asyncio.to_thread(
            self._sync_repo.get_observations_for_entity, entity_id, limit
        )

    # ── RepositoryTraversalMixin (repository_traversal.py) ────────────

    async def get_subgraph(self, start_node_ids: list[str], depth: int = 1) -> dict[str, Any]:
        """Retrieve a subgraph of connected nodes up to N hops."""
        return await asyncio.to_thread(self._sync_repo.get_subgraph, start_node_ids, depth)

    async def get_all_nodes(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Retrieve all entity nodes for clustering."""
        return await asyncio.to_thread(self._sync_repo.get_all_nodes, limit)

    async def get_total_node_count(self) -> int:
        """Return the total number of nodes in the graph."""
        return await asyncio.to_thread(self._sync_repo.get_total_node_count)

    async def increment_salience(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Atomically increment retrieval_count and recalculate salience_score."""
        return await asyncio.to_thread(self._sync_repo.increment_salience, node_ids)

    async def get_most_recent_entity(self, project_id: str) -> dict[str, Any] | None:
        """Return the most recently created entity in a project."""
        return await asyncio.to_thread(self._sync_repo.get_most_recent_entity, project_id)

    async def shortest_path_length(self, from_id: str, to_id: str) -> int | None:
        """Return the shortest path length between two entities."""
        return await asyncio.to_thread(self._sync_repo.shortest_path_length, from_id, to_id)
