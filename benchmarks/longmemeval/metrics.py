"""Metrics for LongMemEval benchmark evaluation.

Implements Recall@K and NDCG@K as used in the LongMemEval paper.
LongMemEval's primary metric is LLM-as-judge QA accuracy, but we
also compute retrieval metrics to measure Dragon Brain's recall.
"""

from __future__ import annotations

import math


def recall_at_k(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    k: int = 5,
) -> float:
    """Compute Recall@K — fraction of relevant items in top-K results.

    Args:
        retrieved_ids: IDs ranked by retrieval score (best first).
        relevant_ids: Ground-truth relevant IDs.
        k: Cutoff rank.

    Returns:
        Recall value in [0, 1]. Returns 0 if relevant_ids is empty.
    """
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    relevant = set(relevant_ids)
    return len(top_k & relevant) / len(relevant)


def ndcg_at_k(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    k: int = 10,
) -> float:
    """Compute NDCG@K — normalized discounted cumulative gain.

    Uses binary relevance (1 if in relevant set, 0 otherwise).

    Args:
        retrieved_ids: IDs ranked by retrieval score (best first).
        relevant_ids: Ground-truth relevant IDs.
        k: Cutoff rank.

    Returns:
        NDCG value in [0, 1]. Returns 0 if relevant_ids is empty.
    """
    if not relevant_ids:
        return 0.0

    relevant = set(relevant_ids)

    # DCG@K
    dcg = sum(
        1.0 / math.log2(i + 2)  # 1-indexed: position i+1 → log2(i+2)
        for i, rid in enumerate(retrieved_ids[:k])
        if rid in relevant
    )

    # IDCG@K — best possible ranking
    n_relevant = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def aggregate_scores(
    question_scores: list[dict[str, float]],
) -> dict[str, float]:
    """Aggregate per-question metrics into overall benchmark scores.

    Args:
        question_scores: List of dicts, each with metric names as keys
            (e.g., ``recall_at_5``, ``ndcg_at_10``, ``qa_accuracy``).

    Returns:
        Dict with the average of each metric across all questions.
    """
    if not question_scores:
        return {}

    keys = question_scores[0].keys()
    return {
        key: sum(q.get(key, 0.0) for q in question_scores) / len(question_scores) for key in keys
    }
