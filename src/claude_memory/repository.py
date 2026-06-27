"""FalkorDB sync data access layer — Cypher queries, CRUD, index management.

Post-B10.5 role: PRESERVED for diagnostics + CLI ops scripts (e.g.
scripts/heal_graph.py, scripts/recover_graph.py). Production async path
goes through AsyncMemoryRepository (native async) in repository_async.py.
Both share canonical Cypher templates via cypher_queries.py.
"""

import logging
import os
import re
import time
from typing import Any

from falkordb import FalkorDB

from claude_memory.cypher_queries import (
    CREATE_EDGE,
    CREATE_NODE,
    DELETE_EDGE,
    GET_NODE_BY_ID,
    HARD_DELETE_NODE,
    SOFT_DELETE_NODE,
    UPDATE_NODE,
)
from claude_memory.repository_queries import RepositoryQueryMixin
from claude_memory.repository_traversal import RepositoryTraversalMixin
from claude_memory.retry import retry_on_transient

logger = logging.getLogger(__name__)

_CONSTRUCTOR_MAX_RETRIES = 3
_CONSTRUCTOR_BASE_DELAY = 1.0


class MemoryRepository(RepositoryQueryMixin, RepositoryTraversalMixin):
    """FalkorDB sync data access layer — Cypher queries, CRUD, index management.

    Post-B10.5 role: PRESERVED for diagnostics + CLI ops scripts (e.g.
    scripts/heal_graph.py, scripts/recover_graph.py). Production async path
    goes through AsyncMemoryRepository (native async) in repository_async.py.
    Both share canonical Cypher templates via cypher_queries.py, giving a sync
    x-ray vision into the same database.
    """

    def __init__(
        self, host: str | None = None, port: int | None = None, password: str | None = None
    ) -> None:
        """Connect to FalkorDB using host, port, and password from args or env vars."""
        self.host = host or os.getenv("FALKORDB_HOST", "localhost")
        self.port = port or int(os.getenv("FALKORDB_PORT", "6379"))
        self.password = password or os.getenv("FALKORDB_PASSWORD")

        self.client = self._connect_with_retry()
        self.graph_name = "claude_memory"

    def _connect_with_retry(self) -> FalkorDB:
        """Attempt to connect to FalkorDB with retry on transient failures."""
        for attempt in range(_CONSTRUCTOR_MAX_RETRIES):
            try:
                return FalkorDB(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                )
            except (ConnectionError, TimeoutError, OSError) as exc:
                if attempt == _CONSTRUCTOR_MAX_RETRIES - 1:
                    logger.error(
                        "FalkorDB connection failed after %d attempts: %s",
                        _CONSTRUCTOR_MAX_RETRIES,
                        exc,
                    )
                    raise
                delay = _CONSTRUCTOR_BASE_DELAY * (2**attempt)
                logger.warning(
                    "FalkorDB connect retry %d/%d in %.1fs — %s",
                    attempt + 1,
                    _CONSTRUCTOR_MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
        raise ConnectionError("FalkorDB connection exhausted retries")  # pragma: no cover

    @retry_on_transient()
    def select_graph(self) -> Any:
        """Return the active FalkorDB graph handle."""
        return self.client.select_graph(self.graph_name)

    def ensure_indices(self) -> None:
        """Create necessary indices if they don't exist."""
        # No longer manages vector indices.
        # Could add index on 'id' or 'name' for speed if not implicit in Node Key.
        pass

    @retry_on_transient()
    def create_node(self, label: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Creates a node (embedding logic moved to VectorStore)."""
        assert re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,63}", label), (  # noqa: S101
            f"Invalid Cypher label: {label!r} — must pass through CreateMemoryTypeParams validator"
        )

        graph = self.select_graph()
        props = properties.copy()

        # Build query
        params: dict[str, Any] = {"props": props}

        # MERGE to prevent duplicates
        params["name"] = props.get("name")
        params["project_id"] = props.get("project_id")
        params["updated_at"] = props.get("updated_at")

        result = graph.query(CREATE_NODE.format(label=label), params)
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @retry_on_transient()
    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieves a node by its ID."""
        graph = self.select_graph()
        result = graph.query(GET_NODE_BY_ID, {"id": node_id})

        if not result.result_set:
            return None

        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    @retry_on_transient()
    def update_node(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Updates a node's properties."""
        graph = self.select_graph()
        props = properties.copy()

        params = {"id": node_id, "props": props}

        result = graph.query(UPDATE_NODE, params)
        if not result.result_set:
            return {}
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    def delete_node(
        self, node_id: str, soft_delete: bool = False, reason: str | None = None
    ) -> bool:
        """Deletes a node (hard or soft)."""
        graph = self.select_graph()

        if soft_delete:
            res = graph.query(SOFT_DELETE_NODE, {"id": node_id, "reason": reason})
            return bool(res.result_set)
        else:
            graph.query(HARD_DELETE_NODE, {"id": node_id})
            return True

    def create_edge(
        self, from_id: str, to_id: str, relation_type: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """Creates or merges a relationship between two nodes.

        Uses merge logic to prevent duplicate edges on retry.
        """
        graph = self.select_graph()

        result = graph.query(
            CREATE_EDGE.format(relation_type=relation_type),
            {"from": from_id, "to": to_id, "props": properties},
        )
        if not result.result_set:
            return {}
        return result.result_set[0][0].properties  # type: ignore[no-any-return]

    def delete_edge(self, edge_id: str) -> bool:
        """Deletes a relationship by ID."""
        graph = self.select_graph()
        graph.query(DELETE_EDGE, {"id": edge_id})
        return True

    @retry_on_transient()
    def execute_cypher(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Executes a raw Cypher query."""
        graph = self.select_graph()
        return graph.query(query, params or {})
