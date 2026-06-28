"""Mixin for graph traversal and analytics queries."""

import logging
from typing import Any

from claude_memory.cypher_queries import (
    COUNT_ALL_NODES,
    GET_ALL_NODES,
    GET_MOST_RECENT_ENTITY,
    GET_SUBGRAPH_DEPTH_ZERO,
    GET_SUBGRAPH_TEMPLATE,
    INCREMENT_SALIENCE,
    SHORTEST_PATH_FORWARD,
    SHORTEST_PATH_REVERSE,
)
from claude_memory.retry import retry_on_transient

logger = logging.getLogger(__name__)


class RepositoryTraversalMixin:
    """Methods for traversing the graph and retrieving aggregate data."""

    def select_graph(self) -> Any:
        """Protocol method to be implemented by the main Repository class."""
        raise NotImplementedError

    @retry_on_transient()
    def get_subgraph(self, start_node_ids: list[str], depth: int = 1) -> dict[str, Any]:
        """Retrieves a subgraph of connected nodes up to 'depth' hops from start nodes."""
        if not start_node_ids:
            return {"nodes": [], "edges": []}

        graph = self.select_graph()

        # Optimization: If depth is 0, just fetch nodes directly (Fixes UNWIND bug on empty paths)
        if depth == 0:
            res_nodes = graph.query(GET_SUBGRAPH_DEPTH_ZERO, {"ids": start_node_ids})
            if res_nodes.result_set:
                # Extract inner dict properties
                return {
                    "nodes": [n["properties"] for n in res_nodes.result_set[0][0]],
                    "edges": [],
                }
            return {"nodes": [], "edges": []}

        result = graph.query(GET_SUBGRAPH_TEMPLATE.format(depth=depth), {"ids": start_node_ids})

        # Now we parse the JSON-like maps returned
        if not result.result_set:
            # It might be empty if 0 hops and no edges?
            # Fallback for isolated nodes (depth 0)
            res_nodes = graph.query(GET_SUBGRAPH_DEPTH_ZERO, {"ids": start_node_ids})
            if res_nodes.result_set:
                return {
                    "nodes": [n["properties"] for n in res_nodes.result_set[0][0]],
                    "edges": [],
                }
            return {"nodes": [], "edges": []}

        row = result.result_set[0]
        edges_data = row[0]
        nodes_data = row[1]

        # Deduplicate nodes by ID (Cypher set might not be perfect with maps)
        unique_nodes = {n["id"]: n["properties"] for n in nodes_data}
        unique_edges = {e["id"]: e for e in edges_data}  # e has source/target/type merged in

        return {"nodes": list(unique_nodes.values()), "edges": list(unique_edges.values())}

    def get_all_nodes(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Retrieves all entity nodes for clustering."""
        graph = self.select_graph()
        result = graph.query(GET_ALL_NODES, {"limit": limit})
        return [row[0].properties for row in result.result_set]

    def get_total_node_count(self) -> int:
        """Returns the total number of nodes in the graph (for receipts)."""
        graph = self.select_graph()
        result = graph.query(COUNT_ALL_NODES)
        if not result.result_set:
            return 0
        return int(result.result_set[0][0])

    @retry_on_transient()
    def increment_salience(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Atomically increment retrieval_count and recalculate salience_score for nodes.

        Formula: salience_score = 1.0 + log2(1 + retrieval_count)
        Uses log(x)/log(2) since FalkorDB doesn't support log2().
        This gives diminishing returns — early retrievals boost salience fast.
        """
        if not node_ids:
            return []
        graph = self.select_graph()
        result = graph.query(INCREMENT_SALIENCE, {"ids": node_ids})
        return [
            {
                "id": row[0],
                "salience_score": row[1],
                "retrieval_count": row[2],
            }
            for row in result.result_set
        ]

    @retry_on_transient()
    def get_most_recent_entity(self, project_id: str) -> dict[str, Any] | None:
        """Return the most recently created entity in a project (for PRECEDED_BY linking)."""
        graph = self.select_graph()
        result = graph.query(GET_MOST_RECENT_ENTITY, {"pid": project_id})
        if not result.result_set:
            return None
        node = result.result_set[0][0]
        return dict(node.properties) if hasattr(node, "properties") else None

    @retry_on_transient()
    def shortest_path_length(self, from_id: str, to_id: str) -> int | None:
        """Return the shortest path length between two entities.

        FalkorDB requires directed ``shortestPath`` traversals, so we
        try forward first, then reverse.  Uses ``WITH`` clause (not
        ``MATCH``) for FalkorDB compatibility.

        Returns:
            Path length as ``int``, or ``None`` if no path exists or
            either node is missing.
        """
        graph = self.select_graph()
        params = {"from_id": from_id, "to_id": to_id}

        # Try forward direction
        try:
            res = graph.query(SHORTEST_PATH_FORWARD, params)
            if res.result_set and res.result_set[0][0] is not None:
                return int(res.result_set[0][0])
        except Exception:
            logger.warning(
                "shortest_path_length forward query failed for %s->%s",
                from_id,
                to_id,
                exc_info=True,
            )

        # Try reverse direction
        try:
            res = graph.query(SHORTEST_PATH_REVERSE, params)
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
