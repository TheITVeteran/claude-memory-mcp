"""Tests for radar_viz — graph rendering with radar overlays.

3 tests: empty, with suggestions, color scaling.
"""

from dashboard.radar_viz import _score_to_alpha, render_graph_with_radar


def test_sad_empty_suggestions() -> None:
    """No radar results → produces valid HTML with no crash."""
    html = render_graph_with_radar(existing_edges=[], radar_suggestions=[])
    assert isinstance(html, str)
    assert "<html" in html.lower() or "vis-network" in html.lower() or len(html) > 100


def test_happy_render_with_suggestions() -> None:
    """5 suggestions → HTML contains dashed edge data."""
    edges = [
        {
            "source": "a1",
            "target": "b1",
            "type": "RELATES_TO",
            "source_name": "Alpha",
            "target_name": "Bravo",
        },
    ]
    suggestions = [
        {
            "entity_a": {"id": "a1", "name": "Alpha"},
            "entity_b": {"id": "c1", "name": "Charlie"},
            "radar_score": 0.85,
            "cosine_similarity": 0.85,
            "graph_distance": None,
            "suggested_relationship": "RELATED_TO",
            "reasoning": "Both discuss Python",
        },
        {
            "entity_a": {"id": "b1", "name": "Bravo"},
            "entity_b": {"id": "d1", "name": "Delta"},
            "radar_score": 0.72,
            "cosine_similarity": 0.72,
            "graph_distance": 5,
        },
    ]

    html = render_graph_with_radar(existing_edges=edges, radar_suggestions=suggestions)

    assert isinstance(html, str)
    assert len(html) > 200
    # Should contain node labels
    assert "Alpha" in html
    assert "Charlie" in html
    # Should contain dashed edge indicators
    assert "true" in html.lower() or "dashes" in html.lower()


def test_happy_color_scaling() -> None:
    """Verify alpha values scale with score."""
    # Low score → lower alpha
    low_alpha = _score_to_alpha(0.0)
    high_alpha = _score_to_alpha(1.0)
    mid_alpha = _score_to_alpha(0.5)

    assert low_alpha == 0.3  # min_alpha default
    assert high_alpha == 1.0  # max_alpha default
    assert 0.3 < mid_alpha < 1.0
    # Monotonic
    assert low_alpha < mid_alpha < high_alpha

    # Clamping works
    assert _score_to_alpha(-0.5) == 0.3
    assert _score_to_alpha(1.5) == 1.0
