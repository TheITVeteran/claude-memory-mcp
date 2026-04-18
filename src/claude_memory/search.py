"""Search operations for the Claude Memory system.

Provides vector search, spreading-activation, path traversal, hologram, and
point-in-time queries.  ADR-007 hybrid search unification.

Orchestration lives here; individual retrieval channels are in
``search_channels.py``.
"""

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from claude_memory.merge import MergedResult
from claude_memory.search_advanced import SearchAdvancedMixin
from claude_memory.search_channels import SearchChannelsMixin

if TYPE_CHECKING:  # pragma: no cover
    from .activation import ActivationEngine
    from .context_manager import ContextManager
    from .interfaces import Embedder, VectorStore
    from .repository import MemoryRepository
    from .router import QueryRouter
    from .schema import SearchResult

logger = logging.getLogger(__name__)


def _build_rerank_text(merged_result: MergedResult) -> str:
    """Build rich text for cross-encoder scoring from a MergedResult.

    Never returns a UUID — falls back through name, description,
    entity_type, and observations until something meaningful is found.
    """
    meta = merged_result.graph_metadata
    parts: list[str] = []

    if meta.get("name"):
        parts.append(str(meta["name"]))
    if meta.get("entity_type"):
        parts.append(str(meta["entity_type"]))
    if meta.get("description"):
        parts.append(str(meta["description"])[:500])
    if meta.get("observations"):
        obs = meta["observations"]
        if isinstance(obs, list):
            parts.extend(str(o)[:200] for o in obs[:3])

    return " ".join(parts) if parts else "unknown entity"


class SearchMixin(SearchAdvancedMixin, SearchChannelsMixin):
    """Search / traversal methods — mixed into MemoryService.

    Inherits ``search_associative`` and ``get_hologram`` from SearchAdvancedMixin.
    Inherits retrieval channel methods from SearchChannelsMixin.
    """

    repo: "MemoryRepository"
    embedder: "Embedder"
    vector_store: "VectorStore"
    router: "QueryRouter"
    activation_engine: "ActivationEngine"
    context_manager: "ContextManager"

    async def get_neighbors(
        self, entity_id: str, depth: int = 1, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Retrieve entities connected within a given hop depth."""
        depth = max(depth, 1)
        query = f"""
        MATCH (n)-[*1..{depth}]-(m)
        WHERE n.id = $entity_id
        RETURN distinct m
        SKIP $offset
        LIMIT $limit
        """
        res = self.repo.execute_cypher(
            query, {"entity_id": entity_id, "limit": limit, "offset": offset}
        )
        nodes = [row[0].properties for row in res.result_set if row]
        for n in nodes:
            n.pop("embedding", None)
        return nodes

    async def traverse_path(self, from_id: str, to_id: str) -> list[dict[str, Any]]:
        """Find the shortest path between two entities.

        FalkorDB requires directed shortestPath traversals, so we try
        both directions (forward and reverse) and return whichever succeeds.
        """

        def _extract_path(res: Any) -> list[dict[str, Any]]:
            """Extract node properties from a FalkorDB shortestPath result."""
            path_data: list[dict[str, Any]] = []
            if res.result_set and res.result_set[0]:
                path_obj = res.result_set[0][0]
                if hasattr(path_obj, "nodes"):
                    nodes = path_obj.nodes() if callable(path_obj.nodes) else path_obj.nodes
                    for node in nodes:
                        props = node.properties
                        props.pop("embedding", None)
                        path_data.append(props)
            return path_data

        params = {"start": from_id, "end": to_id}

        # Try forward direction first
        fwd_query = """
        MATCH (a:Entity {id: $start}), (b:Entity {id: $end})
        WITH shortestPath((a)-[*..10]->(b)) AS p
        RETURN p
        """
        try:
            res = self.repo.execute_cypher(fwd_query, params)
            path_data = _extract_path(res)
            if path_data:
                return path_data
        except Exception:  # noqa: S110  # nosec B110
            # Forward traversal failed (e.g. no directed path), try reverse
            pass

        # Try reverse direction
        rev_query = """
        MATCH (a:Entity {id: $start}), (b:Entity {id: $end})
        WITH shortestPath((b)-[*..10]->(a)) AS p
        RETURN p
        """
        res = self.repo.execute_cypher(rev_query, params)
        path_data = _extract_path(res)
        if path_data:
            path_data.reverse()
        return path_data

    async def find_cross_domain_patterns(
        self, entity_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find nodes in different projects connected to this entity."""
        query = """
        MATCH (n:Entity {id: $entity_id})
        MATCH (n)-[*1..3]-(m:Entity)
        WHERE m.project_id <> n.project_id
        RETURN distinct m
        LIMIT $limit
        """
        res = self.repo.execute_cypher(query, {"entity_id": entity_id, "limit": limit})
        nodes = [row[0].properties for row in res.result_set if row]
        for n in nodes:
            n.pop("embedding", None)
        return nodes

    async def get_evolution(self, entity_id: str) -> list[dict[str, Any]]:
        """Retrieve the evolution (history/observations) of an entity."""
        query = """
        MATCH (e:Entity {id: $entity_id})-[:HAS_OBSERVATION]->(o)
        RETURN o
        ORDER BY o.created_at DESC
        """
        res = self.repo.execute_cypher(query, {"entity_id": entity_id})
        nodes = [row[0].properties for row in res.result_set if row]
        for n in nodes:
            n.pop("embedding", None)
        return nodes

    async def point_in_time_query(self, query_text: str, as_of: str) -> list[dict[str, Any]]:
        """Execute a search considering only knowledge known before `as_of`."""
        vec = self.embedder.encode(query_text)

        # Use VectorStore with time filter
        vector_results = await self.vector_store.search(
            vector=vec, limit=10, filter={"created_at_lt": as_of}
        )

        if not vector_results:
            return []

        # Hydrate from Graph
        ids = [item["_id"] for item in vector_results]
        graph_data = self.repo.get_subgraph(ids, depth=0)

        # Flatten
        nodes = list(graph_data["nodes"])
        for n in nodes:
            n.pop("embedding", None)
        return nodes

    async def diff_knowledge_state(
        self,
        as_of_start: datetime,
        as_of_end: datetime,
        project_id: str | None = None,
        include_observations: bool = False,
    ) -> dict[str, Any]:
        """Compute the difference between two knowledge graph snapshots.

        Returns structured diff showing entities and relationships
        added/removed/evolved between two points in time.

        Args:
            as_of_start: Earlier timestamp.
            as_of_end: Later timestamp (must be after start).
            project_id: Optional project scoping.
            include_observations: If True, include per-entity observation diffs.

        Returns:
            Dict with added/removed/evolved entities and relationships,
            superseded entities, optional observation deltas, and a summary.

        Raises:
            ValueError: If as_of_start >= as_of_end.
        """
        if as_of_start >= as_of_end:
            raise ValueError(
                f"as_of_start ({as_of_start.isoformat()}) must be before "
                f"as_of_end ({as_of_end.isoformat()})"
            )

        start_iso = as_of_start.isoformat()
        end_iso = as_of_end.isoformat()
        project_clause = "AND n.project_id = $project_id" if project_id else ""
        params: dict[str, Any] = {"start": start_iso, "end": end_iso}
        if project_id:
            params["project_id"] = project_id

        # Fetch snapshots via helpers
        start_ents, end_ents = self._diff_fetch_entities(params, project_clause)
        start_rels, end_rels = self._diff_fetch_relationships(params, project_clause)
        superseded = self._diff_fetch_supersedes(params, project_clause)

        # Compute diffs
        added_ids = set(end_ents.keys()) - set(start_ents.keys())
        removed_ids = set(start_ents.keys()) - set(end_ents.keys())
        evolved = [
            end_ents[eid]
            for eid in (set(start_ents.keys()) & set(end_ents.keys()))
            if (end_ents[eid].get("updated_at", "") > start_iso)
        ]
        added_rel_ids = set(end_rels.keys()) - set(start_rels.keys())
        removed_rel_ids = set(start_rels.keys()) - set(end_rels.keys())

        result: dict[str, Any] = {
            "window": {"start": start_iso, "end": end_iso},
            "added_entities": [end_ents[eid] for eid in added_ids],
            "removed_entities": [start_ents[eid] for eid in removed_ids],
            "added_relationships": [end_rels[rid] for rid in added_rel_ids],
            "removed_relationships": [start_rels[rid] for rid in removed_rel_ids],
            "evolved_entities": evolved,
            "superseded": superseded,
            "summary": {
                "entities_added": len(added_ids),
                "entities_removed": len(removed_ids),
                "entities_evolved": len(evolved),
                "relationships_added": len(added_rel_ids),
                "relationships_removed": len(removed_rel_ids),
                "superseded_count": len(superseded),
                "total_changes": (
                    len(added_ids)
                    + len(removed_ids)
                    + len(evolved)
                    + len(added_rel_ids)
                    + len(removed_rel_ids)
                ),
            },
        }
        if include_observations:
            result["observation_deltas"] = self._diff_fetch_observations(
                evolved, start_iso, end_iso
            )
        return result

    # ── diff_knowledge_state helpers ──────────────────────────────────

    def _diff_fetch_entities(
        self, params: dict[str, Any], project_clause: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        """Fetch entity snapshots at start and end timestamps."""
        start_q = f"""
        MATCH (n:Entity)
        WHERE n.created_at <= $start
          AND (n.archived_at IS NULL OR n.archived_at > $start)
          {project_clause}
        RETURN n
        """
        end_q = f"""
        MATCH (n:Entity)
        WHERE n.created_at <= $end
          AND (n.archived_at IS NULL OR n.archived_at > $end)
          {project_clause}
        RETURN n
        """
        start_res = self.repo.execute_cypher(start_q, params)
        end_res = self.repo.execute_cypher(end_q, params)
        return (
            self._diff_extract_entities(start_res),
            self._diff_extract_entities(end_res),
        )

    @staticmethod
    def _diff_extract_entities(result: Any) -> dict[str, dict[str, Any]]:
        """Build {id: properties} map from a Cypher entity result set."""
        out: dict[str, dict[str, Any]] = {}
        for row in result.result_set:
            if row and row[0]:
                props = dict(row[0].properties)
                props.pop("embedding", None)
                eid = props.get("id", "")
                if eid:
                    out[eid] = props
        return out

    def _diff_fetch_relationships(
        self, params: dict[str, Any], project_clause: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        """Fetch relationship snapshots at start and end timestamps."""
        proj = project_clause.replace("n.", "a.")
        start_q = f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE r.created_at <= $start {proj}
        RETURN r.id AS rid, type(r) AS rtype,
               a.id AS src, b.id AS dst, r.created_at AS cat
        """
        end_q = f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE r.created_at <= $end {proj}
        RETURN r.id AS rid, type(r) AS rtype,
               a.id AS src, b.id AS dst, r.created_at AS cat
        """
        start_res = self.repo.execute_cypher(start_q, params)
        end_res = self.repo.execute_cypher(end_q, params)
        return self._diff_extract_rels(start_res), self._diff_extract_rels(end_res)

    @staticmethod
    def _diff_extract_rels(result: Any) -> dict[str, dict[str, Any]]:
        """Build {rel_id: info} map from relationship result set."""
        out: dict[str, dict[str, Any]] = {}
        for row in result.result_set:
            if not row:
                continue
            rid = row[0] or f"{row[2]}-{row[1]}-{row[3]}"
            out[str(rid)] = {
                "id": str(rid),
                "type": row[1],
                "source": row[2],
                "target": row[3],
                "created_at": row[4],
            }
        return out

    def _diff_fetch_supersedes(
        self, params: dict[str, Any], project_clause: str
    ) -> list[dict[str, Any]]:
        """Query SUPERSEDES edges created within the diff window."""
        proj = project_clause.replace("n.", "old.")
        q = f"""
        MATCH (old:Entity)-[r:SUPERSEDES]->(new:Entity)
        WHERE r.created_at > $start AND r.created_at <= $end {proj}
        RETURN old.id AS old_id, old.name AS old_name,
               new.id AS new_id, new.name AS new_name
        """
        res = self.repo.execute_cypher(q, params)
        return [
            {"old_id": row[0], "old_name": row[1], "new_id": row[2], "new_name": row[3]}
            for row in res.result_set
            if row
        ]

    def _diff_fetch_observations(
        self, evolved: list[dict[str, Any]], start_iso: str, end_iso: str
    ) -> list[dict[str, Any]]:
        """Fetch new observations for evolved entities within the window."""
        deltas: list[dict[str, Any]] = []
        for entity in evolved:
            obs_q = """
            MATCH (e:Entity {id: $eid})-[:HAS_OBSERVATION]->(o)
            WHERE o.created_at > $start AND o.created_at <= $end
            RETURN o.content AS content, o.created_at AS cat
            ORDER BY o.created_at ASC
            """
            res = self.repo.execute_cypher(
                obs_q, {"eid": entity["id"], "start": start_iso, "end": end_iso}
            )
            new_obs = [
                {"content": row[0], "created_at": row[1]}
                for row in res.result_set
                if row and row[0]
            ]
            if new_obs:
                deltas.append({"entity_id": entity["id"], "new_observations": new_obs})
        return deltas

    # ── Main search entry point (ADR-007 hybrid pipeline) ────────────

    async def search(  # noqa: PLR0913, C901, PLR0915, PLR0912
        self,
        query: str,
        limit: int = 5,
        project_id: str | None = None,
        offset: int = 0,
        mmr: bool = False,
        strategy: str | None = None,
        deep: bool = False,
        temporal_window_days: int = 7,
    ) -> list["SearchResult"]:
        """Search for entities using the hybrid pipeline (ADR-007).

        Default path (``strategy=None``): vector search + intent-based graph
        enrichment + RRF merge.  Explicit strategies dispatch directly.

        ``strategy='auto'`` is deprecated — logs a warning and falls through
        to the hybrid default.
        """
        if not query:
            return []

        _t0 = time.perf_counter()
        try:
            # ── Handle explicit strategies (direct dispatch) ──
            if strategy is not None:
                if strategy == "auto":
                    logger.warning("strategy='auto' is deprecated; using hybrid default")
                    strategy = None  # fall through to hybrid
                else:
                    return await self._direct_strategy_search(
                        query, strategy, limit, project_id, temporal_window_days
                    )

            # ── HYBRID DEFAULT PATH ──

            # Step 1: Vector search (always)
            vector_results = await self._execute_vector_search(
                query, limit, project_id, offset, mmr
            )

            # Step 2: FTS5 lexical search (always — complements vector)
            fts_results = await self._fts_enrichment(query, limit=limit)

            # Step 3: Intent classification → soft channel weights
            from .router import QueryIntent, QueryRouter  # noqa: PLC0415

            detected_intent = self.router.classify(query)
            weights = QueryRouter.get_channel_weights(detected_intent)

            # Step 4: Enrichment channels — skip when weight is 0
            temporal_results: list[dict[str, Any]] = []
            temporal_exhausted = False
            relational_results: list[dict[str, Any]] = []
            associative_results: list[dict[str, Any]] = []

            # Temporal
            if weights.get("temporal", 0) > 0:
                try:
                    temporal_results, temporal_exhausted = await self._temporal_enrichment(
                        query, limit, project_id, temporal_window_days
                    )
                except Exception:
                    logger.debug("Temporal enrichment failed", exc_info=True)

            # Relational
            if weights.get("relational", 0) > 0:
                try:
                    relational_results = await self._relational_enrichment(query)
                except Exception:
                    logger.debug("Relational enrichment failed", exc_info=True)

            # Associative
            if weights.get("associative", 0) > 0:
                try:
                    associative_results = await self._associative_enrichment(
                        query, vector_results, limit, project_id
                    )
                except Exception:
                    logger.debug("Associative enrichment failed", exc_info=True)

            # Entity extraction (Tier 2.2)
            entity_results: list[dict[str, Any]] = []
            if weights.get("entity", 0) > 0:
                try:
                    entity_results = await self._entity_extraction_enrichment(query)
                except Exception:
                    logger.debug("Entity extraction enrichment failed", exc_info=True)

            # Step 5: Weighted multi-channel RRF merge
            from .merge import ChannelResults, weighted_rrf_merge  # noqa: PLC0415

            channels = [
                ChannelResults("vector", vector_results, weights.get("vector", 1.0), id_key="_id"),
                ChannelResults("fts", fts_results, weights.get("fts", 0.8), id_key="_id"),
                ChannelResults("temporal", temporal_results, weights.get("temporal", 0.3)),
                ChannelResults("relational", relational_results, weights.get("relational", 0.3)),
                ChannelResults("associative", associative_results, weights.get("associative", 0.3)),
                ChannelResults("entity", entity_results, weights.get("entity", 0.6)),
            ]
            merged = weighted_rrf_merge(channels, limit=limit)

            # Step 5.5: Cross-encoder reranking (Tier 1.3)
            # Re-score merged candidates using cross-encoder for precision
            if hasattr(self, "reranker") and merged:
                rerank_dicts = [
                    {"_id": m.entity_id, "_text": _build_rerank_text(m)} for m in merged
                ]

                reranked_dicts = await self.reranker.rerank(
                    query, rerank_dicts, text_key="_text", top_k=limit
                )

                # Rebuild merged list in reranked order
                id_to_merged = {m.entity_id: m for m in merged}
                reranked_merged = []
                for rd in reranked_dicts:
                    eid = rd["_id"]
                    if eid in id_to_merged:
                        reranked_merged.append(id_to_merged[eid])
                if reranked_merged:
                    merged = reranked_merged

            # Step 6: Hydrate
            search_results = await self._hydrate_merged_results(
                merged, detected_intent, deep, vector_results
            )

            # Store temporal exhaustion info on the instance for server layer
            # NOTE: TOCTOU-unsafe under concurrent requests. These instance
            # attributes may be overwritten by a subsequent search() call
            # before the server reads them. Acceptable for single-user MCP
            # but would need request-scoped storage for multi-tenant use.
            self._last_temporal_exhausted = temporal_exhausted
            self._last_temporal_window_days = temporal_window_days
            self._last_temporal_result_count = (
                len(temporal_results) if (detected_intent == QueryIntent.TEMPORAL) else 0
            )
            self._last_detected_intent = detected_intent

            # DRIFT-002: record search stats
            from claude_memory.stats import record_search  # noqa: PLC0415

            record_search(
                getattr(self, "_stats", None),
                query=query,
                detected_intent=detected_intent.value,
                results=search_results,
                latency_ms=(time.perf_counter() - _t0) * 1000,
                temporal_exhausted=(
                    temporal_exhausted if detected_intent == QueryIntent.TEMPORAL else None
                ),
            )

            return search_results
        except (ConnectionError, TimeoutError, OSError, ValueError):
            logger.error("search failed for query=%r", query, exc_info=True)
            return []
