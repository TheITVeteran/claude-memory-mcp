"""Individual retrieval channel methods for the hybrid search pipeline.

Provides vector search execution, graph enrichment (temporal, relational,
associative), score attachment, result hydration, and recency computation.

Split from search.py (ADR-007) to keep modules under 300 lines.
"""

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .activation import ActivationEngine
    from .context_manager import ContextManager
    from .interfaces import Embedder, VectorStore
    from .merge import MergedResult
    from .repository import MemoryRepository
    from .router import QueryRouter
    from .schema import SearchResult

logger = logging.getLogger(__name__)


class SearchChannelsMixin:
    """Retrieval channel methods — mixed into SearchMixin.

    Each ``_*`` method is an individual retrieval channel or hydration
    helper called by :meth:`SearchMixin.search`.
    """

    repo: "MemoryRepository"
    embedder: "Embedder"
    vector_store: "VectorStore"
    router: "QueryRouter"
    activation_engine: "ActivationEngine"
    context_manager: "ContextManager"

    # ── Explicit strategy dispatch (ADR-007 §8) ─────────────────────

    async def _direct_strategy_search(
        self,
        query: str,
        strategy: str,
        limit: int,
        project_id: str | None,
        temporal_window_days: int,
    ) -> list["SearchResult"]:
        """Dispatch to a specific strategy, with vector score attachment.

        Replaces the old ``_route_strategy_search``.  For graph-only
        strategies (temporal/relational), attaches real vector scores
        so ``score`` is never misleadingly 0.0.
        """
        from .router import QueryIntent  # noqa: PLC0415
        from .schema import SearchResult  # noqa: PLC0415

        intent = QueryIntent(strategy)
        results = await self.router.route(
            query,
            self,  # type: ignore[arg-type]
            intent=intent,
            limit=limit,
            project_id=project_id,
            temporal_window_days=temporal_window_days,
        )

        # Convert dicts to SearchResult if needed (temporal/relational return dicts)
        if results and isinstance(results[0], dict):
            results = [
                SearchResult(
                    id=r.get("id", ""),
                    name=r.get("name", "Unknown"),
                    node_type=r.get("node_type", "Entity"),
                    project_id=r.get("project_id", "unknown"),
                    content=r.get("description", ""),
                    score=0.0,
                    distance=0.0,
                )
                for r in results
            ]

        # Fix the score-0 problem for explicit graph strategies
        if intent in (QueryIntent.TEMPORAL, QueryIntent.RELATIONAL):
            results = await self._attach_vector_scores(query, results)

        # Tag all results with their retrieval strategy
        for r in results:
            if isinstance(r, SearchResult):
                r.retrieval_strategy = strategy

        return results

    # ── FTS5 lexical search channel (Tier 1.2) ───────────────────────

    async def _fts_enrichment(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Run FTS5 BM25 search as a lexical retrieval channel.

        Complements vector search by finding exact keyword matches,
        rare terms, and named entities that embedding models may miss.

        Returns results in the same dict format as other graph enrichment
        channels (``entity_id`` key), ready for RRF merge.
        """
        if not hasattr(self, "fts_store"):
            return []

        try:
            fts_results = self.fts_store.search(query=query, limit=limit)
            # Convert to the dict format expected by rrf_merge
            return [{"_id": r["entity_id"], "_score": r["bm25_score"], **r} for r in fts_results]
        except Exception:
            logger.warning("FTS search failed, returning empty", exc_info=True)
            return []

    # ── Graph enrichment helpers ─────────────────────────────────────

    async def _temporal_enrichment(
        self,
        query: str,
        limit: int,
        project_id: str | None,
        temporal_window_days: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Run temporal graph query and return (results, exhausted)."""
        from datetime import timedelta  # noqa: PLC0415

        from .schema import TemporalQueryParams  # noqa: PLC0415

        now = datetime.now(UTC)
        params = TemporalQueryParams(
            start=now - timedelta(days=temporal_window_days),
            end=now,
            limit=limit,
            project_id=project_id,
        )
        results = await self.query_timeline(params)  # type: ignore[attr-defined]
        exhausted = len(results) < limit
        return results, exhausted

    async def _relational_enrichment(self, query: str) -> list[dict[str, Any]]:
        """Extract entity refs from query and traverse graph paths."""
        import re  # noqa: PLC0415

        quoted = re.findall(r'"([^"]+)"', query)
        if len(quoted) >= 2:  # noqa: PLR2004
            path = await self.traverse_path(quoted[0], quoted[1])  # type: ignore[attr-defined]
            # Convert path nodes to dict format with id keys
            return [{"id": n.get("id", ""), **n} for n in path if isinstance(n, dict)]
        return []

    async def _associative_enrichment(
        self,
        query: str,
        vector_results: list[dict[str, Any]],
        limit: int,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        """Run spreading activation using Step 1's vector results as seeds.

        Does NOT re-search Qdrant — avoids the double-dip that calling
        ``search_associative()`` directly would cause.
        """
        if not vector_results:
            return []

        seed_ids = [vr["_id"] for vr in vector_results]
        activation_map = self.activation_engine.activate(seed_ids)
        spread_map = self.activation_engine.spread(activation_map, decay=0.6, max_hops=3)

        # Gather all activated entity IDs
        all_ids = list(set(seed_ids) | set(spread_map.keys()))
        graph_data = self.repo.get_subgraph(all_ids, depth=0)

        return [
            {"id": n.get("id", ""), **n}
            for n in graph_data.get("nodes", [])
            if isinstance(n, dict) and n.get("id")
        ][:limit]

    # ── Vector score attachment (ADR-007 §8) ─────────────────────────

    async def _attach_vector_scores(
        self,
        query: str,
        results: list["SearchResult"],
    ) -> list["SearchResult"]:
        """Batch vector lookup by entity ID to attach real scores.

        Uses ``retrieve_by_ids`` for direct point retrieval rather than
        re-running a similarity search (which could silently miss entities).
        """
        if not results:
            return results

        try:
            vec = self.embedder.encode(query)
            entity_ids = [r.id for r in results]

            # Use batch point retrieval if available, fallback to search
            if hasattr(self.vector_store, "retrieve_by_ids"):
                score_map = await self.vector_store.retrieve_by_ids(
                    ids=entity_ids, query_vector=vec
                )
            else:
                # Fallback for non-Qdrant stores
                vector_hits = await self.vector_store.search(vector=vec, limit=len(results) * 2)
                score_map = {vh["_id"]: vh["_score"] for vh in vector_hits}

            for r in results:
                if r.id in score_map:
                    r.score = score_map[r.id]
                    r.distance = 1.0 - score_map[r.id]
                    r.vector_score = score_map[r.id]
                else:
                    # Entity genuinely has no vector embedding
                    r.vector_score = None
        except (ConnectionError, TimeoutError, OSError, ValueError):
            logger.warning("_attach_vector_scores failed, scores remain 0.0", exc_info=True)

        return results

    # ── Hydration & recency ──────────────────────────────────────────

    async def _hydrate_merged_results(
        self,
        merged: list["MergedResult"],
        detected_intent: Any,
        deep: bool,
        vector_results: list[dict[str, Any]],
    ) -> list["SearchResult"]:
        """Build SearchResult objects from MergedResult entries."""
        from .router import QueryIntent  # noqa: PLC0415
        from .schema import SearchResult  # noqa: PLC0415

        if not merged:
            return []

        ids = [m.entity_id for m in merged]
        graph_depth = 1 if deep else 0
        graph_data = self.repo.get_subgraph(ids, depth=graph_depth)
        nodes_map = {n["id"]: n for n in graph_data["nodes"]}

        # Fire-and-forget salience update
        self._fire_salience_update(ids)  # type: ignore[attr-defined]
        salience_map = {nid: props.get("salience_score", 0.0) for nid, props in nodes_map.items()}

        results: list[SearchResult] = []
        for m in merged:
            node_props = nodes_map.get(m.entity_id)
            if not node_props:
                continue

            observations, relationships = self._deep_hydrate_node(m.entity_id, graph_data, deep)

            # Determine retrieval strategy label
            if len(m.retrieval_sources) > 1:
                strategy = "hybrid"
            elif "vector" in m.retrieval_sources:
                strategy = "semantic"
            else:
                strategy = (
                    detected_intent.value
                    if isinstance(detected_intent, QueryIntent)
                    else "semantic"
                )

            # Use vector score when available, otherwise RRF score
            score = m.vector_score if m.vector_score is not None else m.rrf_score
            distance = 1.0 - score if score > 0 else 0.0

            results.append(
                SearchResult(
                    id=m.entity_id,
                    name=node_props.get("name", "Unknown"),
                    node_type=node_props.get("node_type", "Entity"),
                    project_id=node_props.get("project_id", "unknown"),
                    content=node_props.get("description", ""),
                    score=score,
                    distance=distance,
                    salience_score=salience_map.get(
                        m.entity_id,
                        node_props.get("salience_score", 0.0),
                    ),
                    observations=observations,
                    relationships=relationships,
                    retrieval_strategy=strategy,
                    vector_score=m.vector_score,
                    path_distance=m.graph_metadata.get("path_distance"),
                    activation_score=m.graph_metadata.get("composite_score", 0.0),
                )
            )
            # Compute recency from graph timestamp while we have node_props
            results[-1].recency_score = self._compute_recency(
                results[-1], occurred_at=node_props.get("occurred_at")
            )
        return results

    @staticmethod
    def _compute_recency(
        result: "SearchResult",
        occurred_at: str | None = None,
    ) -> float:
        """Compute 0-1 exponential decay recency score.

        Uses ``RECENCY_HALF_LIFE_DAYS`` env var (default 7).
        Formula: ``2 ** (-age_days / half_life)``

        Args:
            result: SearchResult to score.
            occurred_at: ISO 8601 timestamp string from graph node.
                If None, returns the existing ``recency_score``.
        """
        if occurred_at is None:
            return result.recency_score

        half_life = float(os.getenv("RECENCY_HALF_LIFE_DAYS", "7"))

        try:
            ts = datetime.fromisoformat(occurred_at)
            # Ensure timezone-aware comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - ts).total_seconds() / 86400.0
            if age_days < 0:
                return 1.0  # future timestamps → max recency
            return float(2.0 ** (-age_days / half_life))
        except (ValueError, TypeError):
            logger.debug("Invalid occurred_at '%s', falling back to default", occurred_at)
            return result.recency_score

    # ── Existing helpers (unchanged) ─────────────────────────────────

    async def _execute_vector_search(
        self,
        query: str,
        limit: int,
        project_id: str | None,
        offset: int,
        mmr: bool,
    ) -> list[dict[str, Any]]:
        """Embed query and search Qdrant (standard or MMR)."""
        vec = self.embedder.encode(query)

        search_filter: dict[str, Any] | None = None
        if project_id:
            search_filter = {"project_id": project_id}

        if mmr:
            return await self.vector_store.search_mmr(vector=vec, limit=limit, filter=search_filter)
        return await self.vector_store.search(
            vector=vec, limit=limit, filter=search_filter, offset=offset
        )

    def _hydrate_search_results(
        self,
        vector_results: list[dict[str, Any]],
        deep: bool,
    ) -> list["SearchResult"]:
        """Hydrate vector hits from graph and build SearchResult list."""
        from .schema import SearchResult  # noqa: PLC0415

        ids = [item["_id"] for item in vector_results]

        graph_depth = 1 if deep else 0
        graph_data = self.repo.get_subgraph(ids, depth=graph_depth)
        nodes_map = {n["id"]: n for n in graph_data["nodes"]}

        # Fire-and-forget salience update (non-blocking)
        self._fire_salience_update(ids)  # type: ignore[attr-defined]
        salience_map = {nid: props.get("salience_score", 0.0) for nid, props in nodes_map.items()}

        results = []
        for v_res in vector_results:
            node_id = v_res["_id"]
            if node_id not in nodes_map:
                continue

            node_props = nodes_map[node_id]
            observations, relationships = self._deep_hydrate_node(node_id, graph_data, deep)

            results.append(
                SearchResult(
                    id=node_id,
                    name=node_props.get("name", "Unknown"),
                    node_type=node_props.get("node_type", "Entity"),
                    project_id=node_props.get("project_id", "unknown"),
                    content=node_props.get("description", ""),
                    score=v_res["_score"],
                    distance=1.0 - v_res["_score"],
                    salience_score=salience_map.get(
                        node_id,
                        node_props.get("salience_score", 0.0),
                    ),
                    observations=observations,
                    relationships=relationships,
                )
            )
        return results

    def _deep_hydrate_node(
        self,
        node_id: str,
        graph_data: dict[str, Any],
        deep: bool,
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Fetch observations and relationships for a node when deep=True."""
        if not deep:
            return [], []

        obs_query = (
            "MATCH (e:Entity {id: $eid})-[:HAS_OBSERVATION]->(o) "
            "RETURN o.content ORDER BY o.created_at ASC"
        )
        obs_res = self.repo.execute_cypher(obs_query, {"eid": node_id})
        observations = [row[0] for row in obs_res.result_set if row[0]]
        relationships = [
            e for e in graph_data["edges"] if e.get("src") == node_id or e.get("dst") == node_id
        ]
        return observations, relationships
