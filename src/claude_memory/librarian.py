"""Autonomous librarian agent — clusters, consolidates, and prunes memory nodes."""

import logging
from datetime import UTC, datetime
from typing import Any

from claude_memory.schema import PruneStaleParams

from .clustering import ClusteringService, detect_gaps
from .tools import MemoryService

logger = logging.getLogger(__name__)


class LibrarianAgent:
    """
    Autonomous agent responsible for memory maintenance, clustering, and consolidation.
    "The Librarian" brings order to chaos.
    """

    def __init__(
        self,
        memory_service: MemoryService,
        clustering_service: ClusteringService,
    ):
        """Initialize with memory and clustering service dependencies."""
        self.memory = memory_service
        self.clustering = clustering_service

    async def run_cycle(self) -> dict[str, Any]:
        """Executes a full maintenance cycle.

        1. Fetch all nodes.
        2. Cluster them.
        3. Consolidate dense clusters.
        4. Detect and store gaps.
        5. Prune stale data.
        """
        logger.info("Starting Librarian Maintenance Cycle...")
        report: dict[str, Any] = {
            "clusters_found": 0,
            "consolidations_created": 0,
            "deleted_stale": 0,
            "gaps_detected": 0,
            "gap_reports_stored": 0,
            "errors": [],
        }

        # 1. Fetch
        try:
            nodes = await self.memory.repo.get_all_nodes(limit=2000)
            logger.info("Fetched %d nodes for analysis.", len(nodes))
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error("Failed to fetch nodes: %s", e)
            report["errors"].append(str(e))
            return report

        if len(nodes) < self.clustering.min_samples:
            logger.info("Not enough nodes to form clusters.")
            return report

        # 2. Cluster
        clusters = self.clustering.cluster_nodes(nodes)
        report["clusters_found"] = len(clusters)

        # 3. Consolidate
        await self._consolidate_clusters(clusters, report)

        # 4. Gap Detection
        edges = await self.memory.repo.get_all_edges()
        gaps = detect_gaps(clusters, edges)
        report["gaps_detected"] = len(gaps)
        await self._store_gap_reports(clusters, gaps, report)

        # 5. Prune Stale
        await self._prune_stale(report)

        logger.info("Librarian Cycle Complete.")
        return report

    async def _consolidate_clusters(self, clusters: list[Any], report: dict[str, Any]) -> None:
        """Consolidate each cluster into a summary entity."""
        for cluster in clusters:
            summary = self._synthesize_summary(cluster.nodes)
            entity_ids = [n["id"] for n in cluster.nodes if "id" in n]

            logger.info("Consolidating Cluster %s with %d nodes.", cluster.id, len(entity_ids))
            try:
                res = await self.memory.consolidate_memories(entity_ids, summary)
                if res and "id" in res:
                    report["consolidations_created"] += 1
            except (ConnectionError, TimeoutError, OSError, ValueError) as e:
                logger.error("Failed to consolidate cluster %s: %s", cluster.id, e)
                report["errors"].append(f"Cluster {cluster.id}: {e!s}")

    async def _store_gap_reports(
        self, clusters: list[Any], gaps: list[Any], report: dict[str, Any]
    ) -> None:
        """Store top 3 structural gaps as GapReport entities."""
        gap_limit = 3
        for gap in gaps[:gap_limit]:
            try:
                props = self._build_gap_report(clusters, gap)
                await self.memory.repo.create_node("GapReport", props)
                report["gap_reports_stored"] += 1
            except (ConnectionError, TimeoutError, OSError) as e:
                report["errors"].append(f"GapReport: {e!s}")

    @staticmethod
    def _build_gap_report(clusters: list[Any], gap: Any) -> dict[str, Any]:
        """Build node properties for a GapReport entity."""
        ca_nodes = [c for c in clusters if c.id == gap.cluster_a_id]
        cb_nodes = [c for c in clusters if c.id == gap.cluster_b_id]
        a_names = ", ".join(n.get("name", "?") for n in (ca_nodes[0].nodes[:3] if ca_nodes else []))
        b_names = ", ".join(n.get("name", "?") for n in (cb_nodes[0].nodes[:3] if cb_nodes else []))

        return {
            "name": f"GAP: [{a_names}] ↔ [{b_names}]",
            "entity_type": "GapReport",
            "content": (
                f"Similarity: {gap.similarity:.0%}, "
                f"Cross-edges: {gap.edge_count}, "
                f"Bridges: {len(gap.suggested_bridges)}"
            ),
            "project_id": "librarian",
            "detected_at": datetime.now(UTC).isoformat(),
            "cluster_a_id": gap.cluster_a_id,
            "cluster_b_id": gap.cluster_b_id,
            "similarity": gap.similarity,
            "edge_count": gap.edge_count,
        }

    async def _prune_stale(self, report: dict[str, Any]) -> None:
        """Prune stale entities older than 60 days."""
        try:
            prune_res = await self.memory.prune_stale(PruneStaleParams(days=60))
            report["deleted_stale"] = prune_res.get("deleted_count", 0)
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            report["errors"].append(f"Prune: {e!s}")

    def _synthesize_summary(self, nodes: list[dict[str, Any]]) -> str:
        """
        Mock LLM Synthesis.
        In a real system, this would send node contents to Claude to generate a summary.
        """
        # Extract names/titles
        titles = [n.get("name", "Untitled") for n in nodes[:3]]
        topic = ", ".join(titles)
        return f"Consolidated Architecture regarding: {topic} and {len(nodes) - 3} others."
