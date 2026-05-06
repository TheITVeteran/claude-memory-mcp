"""Spreading Activation Engine for associative memory retrieval.

Implements biologically-inspired spreading activation over the knowledge graph.
Energy propagates from seed nodes through edges, decaying at each hop, with
lateral inhibition to keep only the top-K activated nodes per wave.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from claude_memory.repository import MemoryRepository

logger = logging.getLogger(__name__)

# Edge-type energy multipliers (Tier 2.3: SUPERSEDES Energy Valves)
# Controls how much activation energy flows through each edge type.
# Values < 1.0 dampen flow; values >= 1.0 preserve or amplify it.
EDGE_WEIGHTS: dict[str, float] = {
    # Core relationships — full propagation
    "RELATES_TO": 1.0,
    "DEPENDS_ON": 1.0,
    "CONTAINS": 1.0,
    "PART_OF": 1.0,
    # Temporal — dampened (older context less relevant)
    "EVOLVED_FROM": 0.5,
    "SUPERSEDES": 0.3,
    "PRECEDED_BY": 0.4,
    "CONCURRENT_WITH": 0.8,
    # Epistemic — heavily dampened (conflicting/rejected info)
    "CONTRADICTS": 0.1,
    "REJECTED_FOR": 0.2,
    "SUPPORTS": 1.2,
    "REVISITED_BECAUSE": 0.6,
    # Boosters
    "ENABLES": 1.1,
    "BLOCKS": 0.5,
}

# Directional edges: energy only flows forward (src -> tgt), not backward.
# If A SUPERSEDES B, querying A should NOT boost B's activation.
DIRECTIONAL_EDGES: frozenset[str] = frozenset(
    {
        "SUPERSEDES",
        "PRECEDED_BY",
        "REJECTED_FOR",
        "EVOLVED_FROM",
        "CONTRADICTS",
    }
)


class ActivationEngine:
    """Spreading activation over the knowledge graph.

    Usage::

        engine = ActivationEngine(repo)
        seeds = engine.activate(["entity-1", "entity-2"])
        activation = engine.spread(seeds, decay=0.6, max_hops=3)
        ranked = engine.rank(candidates, vector_scores, activation, salience_scores)
    """

    def __init__(self, repo: MemoryRepository) -> None:
        """Initialise with a graph repository for subgraph queries."""
        self.repo = repo

    # ------------------------------------------------------------------
    # Step 1: Seed activation
    # ------------------------------------------------------------------

    def activate(
        self,
        seed_ids: list[str],
        initial_energy: float = 1.0,
    ) -> dict[str, float]:
        """Set initial activation energy on seed nodes.

        Args:
            seed_ids: Entity IDs to activate.
            initial_energy: Starting energy for each seed.

        Returns:
            Mapping ``{entity_id: energy}``.
        """
        if not seed_ids:
            return {}
        return {sid: initial_energy for sid in seed_ids}

    # ------------------------------------------------------------------
    # Step 2: BFS spread with decay + lateral inhibition
    # ------------------------------------------------------------------

    def spread(
        self,
        activation_map: dict[str, float],
        decay: float = 0.6,
        max_hops: int = 3,
        lateral_inhibition_k: int = 10,
    ) -> dict[str, float]:
        """Propagate activation energy through the graph via BFS.

        At each hop the energy reaching a neighbor is
        ``parent_energy * decay``.  Energy **accumulates** when a node
        is reachable via multiple paths.  After each hop only the top-K
        nodes (by energy) propagate further (lateral inhibition).

        Args:
            activation_map: Initial ``{id: energy}`` (output of :meth:`activate`).
            decay: Multiplicative decay per hop (0-1).
            max_hops: Maximum number of graph traversal hops.
            lateral_inhibition_k: Only top-K nodes per hop continue spreading.

        Returns:
            Full ``{entity_id: accumulated_energy}`` across all hops.
        """
        if not activation_map:
            return {}

        # Accumulated energy for every node touched
        total: dict[str, float] = dict(activation_map)

        # Frontier = nodes whose energy propagates this hop
        frontier = dict(activation_map)

        for _hop in range(max_hops):
            if not frontier:
                break

            next_frontier: dict[str, float] = {}
            frontier_ids = list(frontier.keys())

            # Fetch 1-hop neighbors for the entire frontier
            subgraph = self.repo.get_subgraph(frontier_ids, depth=1)
            edges = subgraph.get("edges", [])

            for edge in edges:
                src = edge.get("source")
                tgt = edge.get("target")
                if src is None or tgt is None:
                    continue

                # Edge-type-aware energy multiplier (Tier 2.3)
                edge_type = edge.get("type", "")
                edge_weight = EDGE_WEIGHTS.get(edge_type, 1.0)
                is_directional = edge_type in DIRECTIONAL_EDGES

                # Forward direction: src -> tgt
                if src in frontier:
                    energy = frontier[src] * decay * edge_weight
                    next_frontier[tgt] = next_frontier.get(tgt, 0.0) + energy
                    total[tgt] = total.get(tgt, 0.0) + energy

                # Reverse direction: tgt -> src (blocked for directional edges)
                if tgt in frontier and not is_directional:
                    energy = frontier[tgt] * decay * edge_weight
                    next_frontier[src] = next_frontier.get(src, 0.0) + energy
                    total[src] = total.get(src, 0.0) + energy

            # Lateral inhibition: only top-K continue
            if len(next_frontier) > lateral_inhibition_k:
                sorted_items = sorted(next_frontier.items(), key=lambda x: x[1], reverse=True)
                next_frontier = dict(sorted_items[:lateral_inhibition_k])

            frontier = next_frontier

        return total

    # ------------------------------------------------------------------
    # Step 3: Composite ranking
    # ------------------------------------------------------------------

    @staticmethod
    def _recency_score(entity: dict[str, Any]) -> float:
        """Compute a 0-1 recency score from occurred_at or created_at.

        More recent entities score closer to 1.0.  Uses an exponential
        decay with a 30-day half-life.
        """
        ts_str = entity.get("occurred_at") or entity.get("created_at")
        if not ts_str:
            return 0.0
        try:
            ts = datetime.fromisoformat(str(ts_str))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - ts).total_seconds() / 86400.0
            # Exponential decay: half-life = 30 days
            return float(2.0 ** (-age_days / 30.0))
        except ValueError:  # noqa: contract
            return 0.0

    def rank(  # noqa: PLR0913
        self,
        candidates: list[dict[str, Any]],
        vector_scores: dict[str, float],
        activation_scores: dict[str, float],
        salience_scores: dict[str, float],
        *,
        w_sim: float | None = None,
        w_act: float | None = None,
        w_sal: float | None = None,
        w_rec: float | None = None,
    ) -> list[dict[str, Any]]:
        """Merge scores into a composite rank and return sorted candidates.

        Weights default to ``SCORE_WEIGHT_*`` env vars, then to
        ``0.4 / 0.3 / 0.2 / 0.1``.  Per-query overrides take precedence.

            composite = similarity*w_sim + activation*w_act
                      + salience*w_sal + recency*w_rec

        Args:
            candidates: Entity dicts (must have ``"id"`` key).
            vector_scores: ``{id: similarity_score}``.
            activation_scores: ``{id: activation_energy}``.
            salience_scores: ``{id: salience_score}``.
            w_sim: Weight for similarity.
            w_act: Weight for activation.
            w_sal: Weight for salience.
            w_rec: Weight for recency.

        Returns:
            Candidates sorted by composite score descending, each enriched
            with a ``"composite_score"`` key.
        """
        if not candidates:
            return []

        # Resolve weights: per-query > env var > hardcoded default
        w_sim = w_sim if w_sim is not None else float(os.getenv("SCORE_WEIGHT_SIMILARITY", "0.4"))
        w_act = w_act if w_act is not None else float(os.getenv("SCORE_WEIGHT_ACTIVATION", "0.3"))
        w_sal = w_sal if w_sal is not None else float(os.getenv("SCORE_WEIGHT_SALIENCE", "0.2"))
        w_rec = w_rec if w_rec is not None else float(os.getenv("SCORE_WEIGHT_RECENCY", "0.1"))

        # Normalize activation scores to 0-1 range
        max_act = max(activation_scores.values()) if activation_scores else 1.0
        max_act = max_act if max_act > 0 else 1.0

        scored = []
        for entity in candidates:
            eid = entity.get("id", "")
            sim = vector_scores.get(eid, 0.0)
            act = activation_scores.get(eid, 0.0) / max_act
            sal = salience_scores.get(eid, 0.0)
            rec = self._recency_score(entity)

            composite = (w_sim * sim) + (w_act * act) + (w_sal * sal) + (w_rec * rec)
            enriched = dict(entity)
            enriched["composite_score"] = round(composite, 6)
            scored.append(enriched)

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Semantic Radar Layer 3: Weak connection detection
    # ------------------------------------------------------------------

    def detect_weak_connections(
        self,
        seed_ids: list[str],
        activation_map: dict[str, float],
        vector_scores: dict[str, float],
        similarity_threshold: float = 0.3,
    ) -> dict[str, list[dict[str, Any]]]:
        """Analyze activation results to find structural anomalies.

        Standalone utility — called after ``search_associative`` which
        produces both ``activation_map`` and ``vector_scores``.

        Returns:
            ``bridge_opportunities``: vector-similar but no activation
            (graph-unreachable).
            ``questionable_edges``: activated (graph-close) but low
            vector similarity.
        """
        seed_set = set(seed_ids)

        # Partition into activated and similar sets
        activated_set = {
            eid for eid, energy in activation_map.items() if energy > 0 and eid not in seed_set
        }
        similar_set = {
            eid
            for eid, score in vector_scores.items()
            if score > similarity_threshold and eid not in seed_set
        }

        # Bridge opportunities: similar but NOT activated (graph-unreachable)
        bridge_ids = similar_set - activated_set
        bridges = sorted(
            [
                {
                    "entity_id": eid,
                    "vector_score": round(vector_scores[eid], 4),
                    "reason": "Semantically similar but graph-unreachable",
                }
                for eid in bridge_ids
            ],
            key=lambda x: x.get("vector_score", 0.0),  # type: ignore[arg-type,return-value]
            reverse=True,
        )

        # Questionable edges: activated but NOT similar
        questionable_ids = activated_set - similar_set
        questionable = sorted(
            [
                {
                    "entity_id": eid,
                    "activation_energy": round(activation_map[eid], 4),
                    "vector_score": round(vector_scores.get(eid, 0.0), 4),
                    "reason": "Graph-connected but semantically dissimilar",
                }
                for eid in questionable_ids
            ],
            key=lambda x: x.get("activation_energy", 0.0),  # type: ignore[arg-type,return-value]
            reverse=True,
        )

        return {
            "bridge_opportunities": bridges,
            "questionable_edges": questionable,
        }
