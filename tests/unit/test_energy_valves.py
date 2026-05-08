from __future__ import annotations

"""Gold Stack tests for SUPERSEDES energy valves (Tier 2.3).

TDD Red phase — tests written BEFORE implementation.

Energy valves control how much activation energy flows through
different edge types. SUPERSEDES/REJECTED_FOR edges should dampen
energy flow, while SUPPORTS/RELATES_TO propagate normally.
"""


from typing import Any
from unittest.mock import AsyncMock

import pytest

from claude_memory.activation import EDGE_WEIGHTS, ActivationEngine

# ── Helpers ──────────────────────────────────────────────────────────


def _make_subgraph(
    node_ids: list[str],
    edges: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """Build a mock subgraph with typed edges.

    Args:
        node_ids: List of entity IDs.
        edges: List of (source, target, edge_type) tuples.
    """
    return {
        "nodes": [{"id": nid, "name": f"Node-{nid}"} for nid in node_ids],
        "edges": [
            {"source": src, "target": tgt, "type": edge_type} for src, tgt, edge_type in edges
        ],
    }


@pytest.fixture()
def engine() -> ActivationEngine:
    repo = AsyncMock()
    return ActivationEngine(repo)


# ═══════════════════════════════════════════════════════════════
#  Edge-weighted spread: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestEdgeWeightedSpread:
    """Gold Stack tests for edge-type-aware energy propagation."""

    @pytest.mark.asyncio
    async def test_happy_supersedes_dampens_energy(self, engine) -> None:
        """SUPERSEDES edge carries less energy than RELATES_TO."""
        # A -> B via SUPERSEDES (damped)
        # A -> C via RELATES_TO (normal)
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B", "C"],
            [("A", "B", "SUPERSEDES"), ("A", "C", "RELATES_TO")],
        )

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # B (via SUPERSEDES) should get less energy than C (via RELATES_TO)
        assert result["B"] < result["C"]

    @pytest.mark.asyncio
    async def test_happy_supports_full_propagation(self, engine) -> None:
        """SUPPORTS edge propagates at full weight."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"],
            [("A", "B", "SUPPORTS")],
        )

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # SUPPORTS should have weight >= 1.0
        expected_energy = 1.0 * 0.6 * EDGE_WEIGHTS.get("SUPPORTS", 1.0)
        assert abs(result["B"] - expected_energy) < 0.001

    @pytest.mark.asyncio
    async def test_happy_edge_weights_dict_has_required_types(self) -> None:
        """EDGE_WEIGHTS dict contains entries for dampening edge types."""
        assert "SUPERSEDES" in EDGE_WEIGHTS
        assert "REJECTED_FOR" in EDGE_WEIGHTS
        assert "PRECEDED_BY" in EDGE_WEIGHTS

        # Dampening edges should have weight < 1.0
        assert EDGE_WEIGHTS["SUPERSEDES"] < 1.0
        assert EDGE_WEIGHTS["REJECTED_FOR"] < 1.0

    @pytest.mark.asyncio
    async def test_sad1_unknown_edge_type_gets_default_weight(self, engine) -> None:
        """Unknown edge type → default weight of 1.0 (full propagation)."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"],
            [("A", "B", "CUSTOM_EDGE_TYPE")],
        )

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # Default weight = 1.0, so B gets exactly seed * decay * 1.0
        assert abs(result["B"] - 0.6) < 0.001

    @pytest.mark.asyncio
    async def test_sad1_no_edges_returns_seeds_only(self, engine) -> None:
        """No edges → only seed nodes in result."""
        engine.repo.get_subgraph.return_value = _make_subgraph(["A"], [])

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        assert "A" in result
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_evil1_supersedes_chain_energy_drops_fast(self, engine) -> None:
        """Chain of SUPERSEDES edges: energy should decay rapidly."""
        # A -> B -> C -> D, all SUPERSEDES
        engine.repo.get_subgraph.side_effect = [
            _make_subgraph(
                ["A", "B", "C", "D"],
                [("A", "B", "SUPERSEDES")],
            ),
            _make_subgraph(
                ["A", "B", "C", "D"],
                [("B", "C", "SUPERSEDES")],
            ),
            _make_subgraph(
                ["A", "B", "C", "D"],
                [("C", "D", "SUPERSEDES")],
            ),
        ]

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=3)

        # Each hop: energy *= decay * SUPERSEDES_weight
        # D should have very little energy compared to B
        if "D" in result and "B" in result:
            assert result["D"] < result["B"]

    @pytest.mark.asyncio
    async def test_evil1_mixed_paths_correct_accumulation(self, engine) -> None:
        """Node reachable via both SUPERSEDES and RELATES_TO accumulates both."""
        # A -> B via SUPERSEDES (damped)
        # A -> B via RELATES_TO (full) — two edges to same node
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"],
            [("A", "B", "SUPERSEDES"), ("A", "B", "RELATES_TO")],
        )

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # B should have accumulated energy from BOTH paths
        supersedes_energy = 1.0 * 0.6 * EDGE_WEIGHTS["SUPERSEDES"]
        relates_energy = 1.0 * 0.6 * EDGE_WEIGHTS.get("RELATES_TO", 1.0)
        expected = supersedes_energy + relates_energy
        assert abs(result["B"] - expected) < 0.001

    @pytest.mark.asyncio
    async def test_evil1_contradicts_severely_dampened(self, engine) -> None:
        """CONTRADICTS edge should heavily dampen energy (epistemic conflict)."""
        engine.repo.get_subgraph.return_value = _make_subgraph(
            ["A", "B"],
            [("A", "B", "CONTRADICTS")],
        )

        seeds = engine.activate(["A"])
        result = await engine.spread(seeds, decay=0.6, max_hops=1)

        # CONTRADICTS should have a low weight
        assert EDGE_WEIGHTS["CONTRADICTS"] < 0.5
        # Very little energy reaches B
        assert result.get("B", 0) < 0.3
