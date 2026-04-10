"""Tests for LongMemEval metrics — Recall@K and NDCG@K.

3 evil, 1 sad, 1 happy per Gold Stack policy.
"""

from benchmarks.longmemeval.metrics import (
    aggregate_scores,
    ndcg_at_k,
    recall_at_k,
)

# ── Evil Tests ────────────────────────────────────────────────────────


def test_evil1_recall_empty_relevant() -> None:
    """No relevant docs → recall should be 0, not crash."""
    assert recall_at_k(["a", "b", "c"], [], k=5) == 0.0


def test_evil2_ndcg_empty_relevant() -> None:
    """No relevant docs → NDCG should be 0, not crash."""
    assert ndcg_at_k(["a", "b", "c"], [], k=5) == 0.0


def test_evil3_k_larger_than_retrieved() -> None:
    """k > len(retrieved) → should not crash, compute on available."""
    # Only 2 retrieved, k=10
    result = recall_at_k(["a", "b"], ["a", "b", "c"], k=10)
    # We retrieved 2 of 3 relevant = 2/3
    assert abs(result - 2 / 3) < 1e-9


# ── Sad Tests ─────────────────────────────────────────────────────────


def test_sad1_no_overlap() -> None:
    """Zero overlap between retrieved and relevant → all zeros."""
    assert recall_at_k(["x", "y", "z"], ["a", "b", "c"], k=3) == 0.0
    assert ndcg_at_k(["x", "y", "z"], ["a", "b", "c"], k=3) == 0.0


# ── Happy Tests ───────────────────────────────────────────────────────


def test_happy_full_pipeline() -> None:
    """Full metric computation with perfect and partial retrieval."""
    # Perfect recall
    assert recall_at_k(["a", "b", "c"], ["a", "b"], k=5) == 1.0

    # Partial recall: 1 of 2 relevant in top-2
    assert recall_at_k(["a", "x"], ["a", "b"], k=2) == 0.5

    # NDCG with perfect ranking (relevant items first)
    ndcg = ndcg_at_k(["a", "b", "x", "y"], ["a", "b"], k=4)
    assert ndcg == 1.0  # ideal ranking

    # NDCG with imperfect ranking
    ndcg_partial = ndcg_at_k(["x", "a", "y", "b"], ["a", "b"], k=4)
    assert 0.0 < ndcg_partial < 1.0  # not perfect

    # Aggregate
    scores = [
        {"recall_at_5": 1.0, "ndcg_at_10": 0.8},
        {"recall_at_5": 0.5, "ndcg_at_10": 0.6},
    ]
    agg = aggregate_scores(scores)
    assert agg["recall_at_5"] == 0.75
    assert agg["ndcg_at_10"] == 0.7

    # Empty aggregate
    assert aggregate_scores([]) == {}
