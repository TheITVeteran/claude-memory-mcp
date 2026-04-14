"""Semantic Radar — batch project scanner for structural gap detection.

Scans the knowledge graph for entity pairs that are semantically similar
(high vector cosine) but structurally distant (high graph distance),
surfacing opportunities to create new connections.

Split from analysis.py to keep modules under 300 lines.
"""

import asyncio
import logging
import math
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .interfaces import Embedder, VectorStore
    from .repository import MemoryRepository

logger = logging.getLogger(__name__)


class SearchRadarMixin:
    """Semantic radar operations — mixed into MemoryService.

    Provides ``find_semantic_opportunities`` for batch gap detection.
    """

    repo: "MemoryRepository"
    embedder: "Embedder"
    vector_store: "VectorStore"

    async def find_semantic_opportunities(
        self,
        project_id: str | None = None,
        similarity_threshold: float = 0.6,
        limit: int = 20,
        min_graph_distance: int = 3,
    ) -> dict[str, Any]:
        """Scan graph for entity pairs that should be connected.

        Iterates over entities, finds vector-similar neighbors, checks
        graph distance, and surfaces pairs that are semantically close
        but structurally distant.

        Uses ``asyncio.Semaphore`` to cap concurrent graph queries.

        Note: ``min_graph_distance=3`` is intentionally more aggressive
        than ``semantic_radar``'s ``<= 1`` filter.  Batch scanning should
        surface only significant gaps, not near-neighbors that are
        simply 2 hops away.
        """
        concurrency = int(os.getenv("RADAR_CONCURRENCY", "10"))
        max_dist_factor = float(os.getenv("RADAR_MAX_DISTANCE_FACTOR", "5.0"))
        semaphore = asyncio.Semaphore(concurrency)

        start_time = time.monotonic()

        # Fetch entity IDs — optionally filtered by project
        if project_id:
            query = "MATCH (n:Entity {project_id: $pid}) RETURN n.id LIMIT 200"
            res = self.repo.execute_cypher(query, {"pid": project_id})
            entity_ids = [row[0] for row in res.result_set if row]
        else:
            entity_ids = self.repo.get_all_node_ids(limit=200)

        if not entity_ids:
            return {
                "opportunities": [],
                "stats": {
                    "entities_scanned": 0,
                    "pairs_evaluated": 0,
                    "bridges_found": 0,
                    "already_connected": 0,
                    "scan_time_ms": 0,
                },
            }

        # Scan each entity concurrently
        raw_pairs: list[dict[str, Any]] = []
        already_connected = 0
        pairs_evaluated = 0

        async def _scan_entity(entity_id: str) -> None:
            """Scan a single entity for semantically similar but disconnected neighbors."""
            nonlocal already_connected, pairs_evaluated
            async with semaphore:
                similar = await self.vector_store.find_similar_by_id(
                    entity_id,
                    limit=5,
                    threshold=similarity_threshold,
                )
                for candidate in similar:
                    pairs_evaluated += 1
                    cid = candidate["_id"]
                    cosine_sim = candidate["_score"]

                    graph_dist = self.repo.shortest_path_length(entity_id, cid)

                    if graph_dist is not None and graph_dist < min_graph_distance:
                        already_connected += 1
                        continue

                    if graph_dist is None:
                        radar_score = cosine_sim * math.log(1 + max_dist_factor * 10)
                    else:
                        radar_score = cosine_sim * math.log(1 + graph_dist)

                    payload = candidate.get("payload", {})
                    raw_pairs.append(
                        {
                            "entity_a_id": entity_id,
                            "entity_b_id": cid,
                            "entity_b_name": payload.get("name", "Unknown"),
                            "entity_b_type": payload.get("node_type", "Entity"),
                            "cosine_similarity": round(cosine_sim, 4),
                            "graph_distance": graph_dist,
                            "radar_score": round(radar_score, 4),
                        }
                    )

        await asyncio.gather(*[_scan_entity(eid) for eid in entity_ids])

        # Deduplicate bidirectional pairs — keep higher score
        seen: dict[frozenset[str], dict[str, Any]] = {}
        for pair in raw_pairs:
            key = frozenset({pair["entity_a_id"], pair["entity_b_id"]})
            if key not in seen or pair["radar_score"] > seen[key]["radar_score"]:
                seen[key] = pair

        opportunities = sorted(seen.values(), key=lambda p: p["radar_score"], reverse=True)[:limit]

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return {
            "opportunities": opportunities,
            "stats": {
                "entities_scanned": len(entity_ids),
                "pairs_evaluated": pairs_evaluated,
                "bridges_found": len(opportunities),
                "already_connected": already_connected,
                "scan_time_ms": elapsed_ms,
            },
        }
