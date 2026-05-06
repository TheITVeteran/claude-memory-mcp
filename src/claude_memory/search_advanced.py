"""Advanced search operations — spreading activation and hologram.

Extracted from search.py to keep each file under 300 lines.
Mixed into SearchMixin at runtime.
"""

import logging
from typing import TYPE_CHECKING, Any

from .schema import SearchAssociativeParams, SearchMemoryParams, SemanticRadarParams

if TYPE_CHECKING:  # pragma: no cover
    from .schema import GetHologramParams, SearchResult

logger = logging.getLogger(__name__)


class SearchAdvancedMixin:
    """Associative search and hologram retrieval — mixed into SearchMixin.

    Expects the host class to provide: ``embedder``, ``vector_store``,
    ``activation_engine``, ``repo``, ``context_manager``,
    ``_fire_salience_update()``, and ``search()``.
    """

    async def search_associative(
        self,
        params: SearchAssociativeParams,
    ) -> list["SearchResult"]:
        """Spreading-activation search: vector → graph spread → composite rank.

        1. Vector search to find initial seed nodes.
        2. Activate seeds and spread energy through the graph.
        3. Hydrate candidate entities from graph.
        4. Composite rank with configurable weights (env var / per-query).
        """
        query = params.query
        limit = params.limit
        decay = params.decay
        max_hops = params.max_hops
        w_sim = params.w_sim
        w_act = params.w_act
        w_sal = params.w_sal
        w_rec = params.w_rec
        from .schema import SearchResult  # noqa: PLC0415

        if not query:
            return []

        # 1. Vector search for seed nodes
        try:
            vec = self.embedder.encode(query)  # type: ignore[attr-defined]
            search_filter: dict[str, Any] | None = None
            if params.project_id:
                search_filter = {"project_id": params.project_id}

            vector_results = await self.vector_store.search(  # type: ignore[attr-defined]
                vector=vec, limit=limit, filter=search_filter
            )
            if not vector_results:
                return []

            seed_ids = [item["_id"] for item in vector_results]
            vector_scores = {item["_id"]: item["_score"] for item in vector_results}

            # 2. Spreading activation
            activation_map = self.activation_engine.activate(seed_ids)  # type: ignore[attr-defined]
            activation_map = self.activation_engine.spread(  # type: ignore[attr-defined]
                activation_map, decay=decay, max_hops=max_hops
            )

            # 3. Gather all candidate IDs (seeds + spread targets)
            all_ids = list(set(seed_ids) | set(activation_map.keys()))
            graph_data = self.repo.get_subgraph(all_ids, depth=0)  # type: ignore[attr-defined]
            nodes_map = {n["id"]: n for n in graph_data["nodes"]}

            # Fire-and-forget salience update for associative search too
            result_ids = list(nodes_map.keys())
            self._fire_salience_update(result_ids)  # type: ignore[attr-defined]

            # Build salience map from graph properties (pre-update values)
            salience_map = {
                nid: props.get("salience_score", 0.0) for nid, props in nodes_map.items()
            }

            # 4. Composite ranking
            candidates = list(nodes_map.values())
            ranked = self.activation_engine.rank(  # type: ignore[attr-defined]
                candidates,
                vector_scores,
                activation_map,
                salience_map,
                w_sim=w_sim,
                w_act=w_act,
                w_sal=w_sal,
                w_rec=w_rec,
            )

            # 5. Convert to SearchResult
            results = []
            for entity in ranked[:limit]:
                eid = entity.get("id", "")
                results.append(
                    SearchResult(
                        id=eid,
                        name=entity.get("name", "Unknown"),
                        node_type=entity.get("node_type", "Entity"),
                        project_id=entity.get("project_id", "unknown"),
                        content=entity.get("description", ""),
                        score=entity.get("composite_score", 0.0),
                        distance=1.0 - vector_scores.get(eid, 0.0),
                        salience_score=salience_map.get(eid, 0.0),
                    )
                )
            return results
        except (ConnectionError, TimeoutError, OSError) as exc:
            from .exceptions import SearchError  # noqa: PLC0415

            logger.error(
                "search_associative: infrastructure error for query=%r", query, exc_info=True
            )
            raise SearchError("Memory retrieval unavailable") from exc

    async def get_hologram(self, params: "GetHologramParams") -> dict[str, Any]:
        """Retrieves a 'Hologram' (connected subgraph) relevant to the query.

        Algorithm:
        1. Search for top entities (Anchors).
        2. Expand outward from Anchors by 'depth'.
        3. Return the consolidated subgraph.
        """
        logger.info("Generating Hologram for: %s", params.query)

        # 1. Get Anchors
        anchors = await self.search(SearchMemoryParams(query=params.query, limit=5))  # type: ignore[attr-defined]

        if not anchors:
            return {"nodes": [], "edges": []}

        anchor_ids = [a.id for a in anchors]

        # 2. Expand Subgraph
        hologram = self.repo.get_subgraph(anchor_ids, params.depth)  # type: ignore[attr-defined]

        # 3. Assemble and Optimize
        raw_nodes = hologram.get("nodes", [])
        raw_edges = hologram.get("edges", [])

        # Sanitization: Strip embeddings to prevent context flood
        for n in raw_nodes:
            if isinstance(n, dict):
                n.pop("embedding", None)

        # Optimize using Token Budget
        optimized_nodes = self.context_manager.optimize(  # type: ignore[attr-defined]
            raw_nodes, max_tokens=params.max_tokens
        )

        # Filter edges: only keep edges where both nodes are in the optimized set
        final_node_ids = {n["id"] for n in optimized_nodes}

        optimized_edges = [
            e for e in raw_edges if e["source"] in final_node_ids and e["target"] in final_node_ids
        ]

        return {
            "query": params.query,
            "anchors": [a.model_dump() for a in anchors],
            "nodes": optimized_nodes,
            "edges": optimized_edges,
            "stats": {
                "total_nodes": len(optimized_nodes),
                "total_edges": len(optimized_edges),
                "original_node_count": len(raw_nodes),
                "pruned": len(raw_nodes) > len(optimized_nodes),
            },
        }

    # ── Semantic Radar (Layer 2) ─────────────────────────────────────

    async def semantic_radar(
        self,
        params: SemanticRadarParams,
    ) -> dict[str, Any]:
        """Discover potential relationships for an entity.

        Compares vector similarity with graph distance to identify
        bridge opportunities — entities that are semantically related
        but poorly connected in the graph.

        Returns suggestions only — does NOT commit edges.
        """
        entity_id = params.entity_id
        limit = params.limit
        similarity_threshold = params.similarity_threshold
        import math  # noqa: PLC0415
        import os  # noqa: PLC0415

        max_dist_factor = float(os.getenv("RADAR_MAX_DISTANCE_FACTOR", "5.0"))

        # Fetch source entity
        source_node = self.repo.get_node(entity_id)  # type: ignore[attr-defined]
        if not source_node:
            return {"error": f"Entity {entity_id} not found", "suggestions": []}

        source_name = source_node.get("name", "Unknown")
        source_type = source_node.get("node_type", "Entity")
        source_project = source_node.get("project_id", "")

        # Step 1: Find vector-similar entities (over-fetch for filtering)
        similar = await self.vector_store.find_similar_by_id(  # type: ignore[attr-defined]
            entity_id,
            limit=limit * 2,
            threshold=similarity_threshold,
        )

        if not similar:
            return {
                "entity_id": entity_id,
                "entity_name": source_name,
                "suggestions": [],
                "stats": {"candidates_scanned": 0, "already_connected": 0, "disconnected": 0},
            }

        # Step 2-4: Compute graph distance + radar score
        suggestions: list[dict[str, Any]] = []
        already_connected = 0
        disconnected = 0

        for candidate in similar:
            cid = candidate["_id"]
            cosine_sim = candidate["_score"]

            graph_dist = self.repo.shortest_path_length(entity_id, cid)  # type: ignore[attr-defined]

            if graph_dist is not None and graph_dist <= 1:
                already_connected += 1
                continue

            if graph_dist is None:
                radar_score = cosine_sim * math.log(1 + max_dist_factor * 10)
                disconnected += 1
            else:
                radar_score = cosine_sim * math.log(1 + graph_dist)

            # Get candidate details from payload
            payload = candidate.get("payload", {})
            cand_name = payload.get("name", "Unknown")
            cand_type = payload.get("node_type", "Entity")
            cand_project = payload.get("project_id", "")

            rel_type = self._infer_relationship_type(
                source_type, cand_type, source_project, cand_project
            )

            # Build reasoning
            if graph_dist is None:
                reasoning = (
                    f"High semantic similarity ({cosine_sim:.2f}) but no graph path "
                    f"— potential bridge (scored as distance {max_dist_factor * 10:.0f})"
                )
            else:
                reasoning = (
                    f"Semantic similarity ({cosine_sim:.2f}) with graph distance "
                    f"{graph_dist} — under-connected"
                )

            suggestions.append(
                {
                    "candidate_id": cid,
                    "candidate_name": cand_name,
                    "candidate_type": cand_type,
                    "cosine_similarity": round(cosine_sim, 4),
                    "graph_distance": graph_dist,
                    "radar_score": round(radar_score, 4),
                    "suggested_relationship": rel_type,
                    "reasoning": reasoning,
                }
            )

        # Step 5: Sort and limit
        suggestions.sort(key=lambda s: s["radar_score"], reverse=True)
        suggestions = suggestions[:limit]

        return {
            "entity_id": entity_id,
            "entity_name": source_name,
            "suggestions": suggestions,
            "stats": {
                "candidates_scanned": len(similar),
                "already_connected": already_connected,
                "disconnected": disconnected,
            },
        }

    @staticmethod
    def _infer_relationship_type(
        source_type: str,
        candidate_type: str,
        source_project: str,
        candidate_project: str,
    ) -> str:
        """Heuristic relationship type inference from node types.

        Covers Dragon Brain node types: Entity, Concept, Session,
        Breakthrough, Tool, Decision, Bottle, Analogy, Issue, Project,
        Procedure, Person.
        """
        # Cross-project → bridge (highest priority)
        if source_project and candidate_project and source_project != candidate_project:
            return "BRIDGES_TO"

        types = frozenset({source_type, candidate_type})

        # Analogous patterns
        if types in ({"Concept"}, {"Breakthrough"}) or ("Concept" in types and "Analogy" in types):
            return "ANALOGOUS_TO"

        # Specific pairings
        if "Tool" in types and "Procedure" in types:
            return "ENABLES"

        # Single-type priority rules
        for node_type, rel in (
            ("Decision", "DECIDED_IN"),
            ("Session", "MENTIONED_IN"),
            ("Person", "CREATED_BY"),
        ):
            if node_type in types:
                return rel

        # Fallback
        return "RELATED_TO"
