"""LongMemEval benchmark runner for Dragon Brain.

Downloads the dataset, ingests sessions as memory, queries the system,
and evaluates answers against ground truth.

Usage:
    python -m benchmarks.longmemeval.runner --dataset oracle --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.longmemeval.metrics import aggregate_scores, recall_at_k

logger = logging.getLogger(__name__)

DATASET_BASE_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main"
DATASET_FILES = {
    "oracle": "longmemeval_oracle.json",
    "small": "longmemeval_s_cleaned.json",
    "medium": "longmemeval_m_cleaned.json",
}


def download_dataset(
    variant: str = "oracle",
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Download and cache a LongMemEval dataset variant.

    Args:
        variant: One of 'oracle', 'small', 'medium'.
        cache_dir: Where to cache the downloaded file.
            Defaults to ``benchmarks/longmemeval/data/``.

    Returns:
        List of evaluation instances.
    """
    import urllib.request

    if cache_dir is None:
        cache_dir = Path(__file__).parent / "data"
    cache_dir.mkdir(parents=True, exist_ok=True)

    filename = DATASET_FILES.get(variant, DATASET_FILES["oracle"])
    filepath = cache_dir / filename

    if not filepath.exists():
        url = f"{DATASET_BASE_URL}/{filename}"
        logger.info("Downloading %s → %s", url, filepath)
        urllib.request.urlretrieve(url, filepath)
    else:
        logger.info("Using cached dataset: %s", filepath)

    with filepath.open(encoding="utf-8") as f:
        return json.load(f)


async def ingest_sessions(
    service: Any,
    instance: dict[str, Any],
    project_id: str = "longmemeval",
) -> list[str]:
    """Ingest haystack sessions for one evaluation instance.

    Each session is stored as a single entity with all turns
    concatenated as observations. Timestamps from the dataset
    are preserved.

    Args:
        service: MemoryService instance.
        instance: A single LongMemEval evaluation instance.
        project_id: Project scope for isolation.

    Returns:
        List of entity IDs created during ingestion.
    """
    entity_ids: list[str] = []
    sessions = instance.get("haystack_sessions", [])

    for i, session in enumerate(sessions):
        # Concatenate turns into a single text block
        turns_text = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('content', '')}" for turn in session
        )

        # Create entity for this session
        entity_name = f"Session_{instance['question_id']}_{i}"
        try:
            result = await service.create_entity(
                name=entity_name,
                entity_type="ChatSession",
                observations=[turns_text],
                project_id=project_id,
            )
            eid = result.get("id", "") if isinstance(result, dict) else ""
            if eid:
                entity_ids.append(eid)
        except Exception:
            logger.exception("Failed to ingest session %d for %s", i, instance["question_id"])

    return entity_ids


async def query_system(
    service: Any,
    question: str,
    project_id: str = "longmemeval",
) -> dict[str, Any]:
    """Query the memory system and return search results.

    Args:
        service: MemoryService instance.
        question: The evaluation question.
        project_id: Project scope.

    Returns:
        Dict with 'answer' (top result text) and 'retrieved_ids'.
    """
    results = await service.search(
        query=question,
        project_id=project_id,
        limit=10,
    )

    entities = results.get("entities", [])
    retrieved_ids = [e.get("id", "") for e in entities]

    # Build answer from top results
    answer_parts = []
    for entity in entities[:3]:
        name = entity.get("name", "")
        obs = entity.get("observations", [])
        obs_text = "; ".join(obs[:3]) if obs else ""
        answer_parts.append(f"{name}: {obs_text}" if obs_text else name)

    return {
        "answer": " | ".join(answer_parts) if answer_parts else "No results found.",
        "retrieved_ids": retrieved_ids,
    }


async def run_benchmark(
    service: Any,
    variant: str = "oracle",
    limit: int | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full LongMemEval benchmark pipeline.

    1. Download dataset
    2. For each instance: ingest sessions → query → evaluate
    3. Aggregate metrics

    Args:
        service: Initialized MemoryService.
        variant: Dataset variant ('oracle', 'small', 'medium').
        limit: Max instances to evaluate (None = all 500).
        output_path: Where to save results JSON.

    Returns:
        Dict with per-question scores and aggregate metrics.
    """
    dataset = download_dataset(variant)
    if limit:
        dataset = dataset[:limit]

    logger.info("Running LongMemEval (%s) on %d instances", variant, len(dataset))

    results: list[dict[str, Any]] = []
    question_scores: list[dict[str, float]] = []
    start_time = time.monotonic()

    for i, instance in enumerate(dataset):
        qid = instance["question_id"]
        logger.info("[%d/%d] Processing %s", i + 1, len(dataset), qid)

        # Ingest
        entity_ids = await ingest_sessions(service, instance)

        # Query
        response = await query_system(service, instance["question"])

        # Evaluate retrieval
        answer_session_ids = instance.get("answer_session_ids", [])
        r_at_5 = recall_at_k(response["retrieved_ids"], answer_session_ids, k=5)
        r_at_10 = recall_at_k(response["retrieved_ids"], answer_session_ids, k=10)

        score = {
            "recall_at_5": r_at_5,
            "recall_at_10": r_at_10,
        }
        question_scores.append(score)

        results.append(
            {
                "question_id": qid,
                "question_type": instance.get("question_type", "unknown"),
                "question": instance["question"],
                "expected_answer": instance["answer"],
                "hypothesis": response["answer"],
                "retrieved_ids": response["retrieved_ids"],
                "ingested_entity_ids": entity_ids,
                "metrics": score,
            }
        )

    elapsed = time.monotonic() - start_time
    aggregated = aggregate_scores(question_scores)

    output = {
        "benchmark": "LongMemEval",
        "variant": variant,
        "instances_evaluated": len(dataset),
        "elapsed_seconds": round(elapsed, 2),
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "aggregate_metrics": aggregated,
        "per_question": results,
    }

    if output_path is None:
        output_path = Path(__file__).parent / "results" / f"results_{variant}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info("Benchmark complete: %d instances in %.1fs", len(dataset), elapsed)
    logger.info("Aggregate metrics: %s", aggregated)
    logger.info("Results saved to %s", output_path)

    return output


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run LongMemEval benchmark")
    parser.add_argument(
        "--dataset",
        choices=["oracle", "small", "medium"],
        default="oracle",
        help="Dataset variant to evaluate against",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of instances to evaluate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for results JSON",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Import here to avoid import-time side effects
    from claude_memory.tools import MemoryService

    service = MemoryService()

    output_path = Path(args.output) if args.output else None
    asyncio.run(
        run_benchmark(
            service=service,
            variant=args.dataset,
            limit=args.limit,
            output_path=output_path,
        )
    )


if __name__ == "__main__":
    main()
