"""Radar visualization — graph with dashed suggestion overlays.

Renders a pyvis graph showing existing edges as solid lines and
semantic radar suggestions as dashed red lines with score labels.
"""

from __future__ import annotations

from typing import Any

from pyvis.network import Network


def render_graph_with_radar(
    existing_edges: list[dict[str, Any]],
    radar_suggestions: list[dict[str, Any]],
    max_nodes: int = 200,
) -> str:
    """Render an HTML graph showing existing edges + radar suggestions.

    Args:
        existing_edges: List of dicts with 'source', 'target', 'type' keys.
        radar_suggestions: List of radar opportunity dicts from
            ``find_semantic_opportunities``.
        max_nodes: Cap on total nodes rendered.

    Returns:
        HTML string for embedding in Streamlit via ``components.html()``.
    """
    net = Network(
        height="600px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="#e0e0e0",
        notebook=False,
        directed=False,
    )
    net.repulsion(node_distance=150, spring_length=200)

    seen_nodes: set[str] = set()
    node_count = 0

    def _add_node(node_id: str, label: str, *, force: bool = False) -> None:
        """Add a node if not already present and under the cap.

        Args:
            force: If True, add node even if max_nodes is exceeded.
                   Required for radar endpoints to avoid pyvis errors.
        """
        nonlocal node_count
        if node_id in seen_nodes:
            return
        if not force and node_count >= max_nodes:
            return
        seen_nodes.add(node_id)
        node_count += 1
        net.add_node(node_id, label=label, color="#4a90d9", size=15)

    # ── Existing edges (solid gray) ──
    for edge in existing_edges:
        src = str(edge.get("source", edge.get("src", "")))
        dst = str(edge.get("target", edge.get("dst", "")))
        rel_type = str(edge.get("type", edge.get("relation", "")))
        if not src or not dst:
            continue
        _add_node(src, edge.get("source_name", src[:8]))
        _add_node(dst, edge.get("target_name", dst[:8]))
        net.add_edge(src, dst, title=rel_type, color="#555555", width=1)

    # ── Radar suggestions (dashed red) ──
    for suggestion in radar_suggestions:
        # Support both flat format (entity_a_id) and nested (entity_a.id)
        entity_a = suggestion.get("entity_a", {})
        entity_b = suggestion.get("entity_b", {})
        a_id = str(suggestion.get("entity_a_id", entity_a.get("id", "")))
        b_id = str(suggestion.get("entity_b_id", entity_b.get("id", "")))
        if not a_id or not b_id:
            continue

        score = suggestion.get("radar_score", suggestion.get("cosine_similarity", 0.5))
        alpha = _score_to_alpha(score)
        color = f"rgba(255, 71, 87, {alpha})"

        a_label = suggestion.get("entity_a_name", entity_a.get("name", a_id[:8]))
        b_label = suggestion.get("entity_b_name", entity_b.get("name", b_id[:8]))
        _add_node(a_id, a_label, force=True)
        _add_node(b_id, b_label, force=True)

        net.add_edge(
            a_id,
            b_id,
            title=f"Radar: {score:.2f}",
            label=f"{score:.2f}",
            color=color,
            width=2,
            dashes=True,
        )

    return net.generate_html()


def _score_to_alpha(score: float, min_alpha: float = 0.3, max_alpha: float = 1.0) -> float:
    """Convert a 0-1 score to an alpha value for edge coloring.

    Higher scores → more opaque (more visible).

    Args:
        score: Radar score between 0 and 1.
        min_alpha: Minimum alpha for lowest scores.
        max_alpha: Maximum alpha for highest scores.

    Returns:
        Alpha value clamped to [min_alpha, max_alpha].
    """
    clamped = max(0.0, min(1.0, score))
    return min_alpha + clamped * (max_alpha - min_alpha)
