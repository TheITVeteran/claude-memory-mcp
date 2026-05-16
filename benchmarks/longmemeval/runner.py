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

from benchmarks.longmemeval.metrics import aggregate_scores, recall_any_at_k, recall_at_k

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


# Module-level flag for observation storage (toggled by --no-observations)
_STORE_OBSERVATIONS = True


async def _flush_prior_entities(service: Any) -> None:
    """Purge ALL existing entities from prior benchmark runs.

    Ensures a clean slate by deleting every entity from graph, vector,
    and FTS stores.  Errors on individual deletes are logged and skipped
    since ghost entities may only exist in one store.
    """
    try:
        all_ids = await service.vector_store.list_ids()
    except Exception:
        logger.warning("Could not list vector IDs — skipping flush", exc_info=True)
        return

    if not all_ids:
        logger.info("No existing entities found — clean slate")
        return

    logger.info("Purging %d ghost entities from prior runs", len(all_ids))
    for eid in all_ids:
        try:
            service.repo.delete_node(eid)
        except Exception:
            logger.debug("flush: graph delete skipped for %s", eid)
        try:
            await service.vector_store.delete(eid)
        except Exception:
            logger.debug("flush: vector delete skipped for %s", eid)
        if hasattr(service, "fts_store"):
            try:
                service.fts_store.remove_entity(eid)
            except Exception:
                logger.debug("flush: FTS delete skipped for %s", eid)
    logger.info("Flush complete — %d entities purged", len(all_ids))


async def ingest_sessions(
    service: Any,
    instance: dict[str, Any],
    project_id: str = "longmemeval",
) -> dict[str, str]:
    """Ingest haystack sessions for one evaluation instance.

    Each session is stored as a single entity with all turns
    concatenated as observations. Timestamps from the dataset
    are preserved.

    Args:
        service: MemoryService instance.
        instance: A single LongMemEval evaluation instance.
        project_id: Project scope for isolation.

    Returns:
        Mapping of dataset session ID → Dragon Brain entity UUID.
    """
    from claude_memory.schema import EntityCreateParams, ObservationParams

    id_map: dict[str, str] = {}  # dataset_session_id -> entity_uuid
    sessions = instance.get("haystack_sessions", [])
    session_ids = instance.get("haystack_session_ids", [])

    for i, session in enumerate(sessions):
        # Concatenate turns into a single text block (FULL content, no truncation)
        turns_text = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('content', '')}" for turn in session
        )

        # Use the dataset session ID if available, else fall back to index
        dataset_sid = session_ids[i] if i < len(session_ids) else f"session_{i}"
        entity_name = f"Session_{instance['question_id']}_{i}"
        try:
            params = EntityCreateParams(
                name=entity_name,
                node_type="Entity",
                project_id=project_id,
                properties={"description": turns_text},
            )
            result = await service.create_entity(params)
            eid = result.id if hasattr(result, "id") else ""
            if eid:
                id_map[dataset_sid] = eid

                # Store full content as observation for deep hydration (Fix #5)
                if _STORE_OBSERVATIONS:
                    try:
                        obs_params = ObservationParams(
                            entity_id=eid,
                            content=turns_text,
                        )
                        await service.add_observation(obs_params)
                    except Exception:
                        logger.debug("Observation add failed for %s", eid, exc_info=True)
        except Exception:
            logger.exception("Failed to ingest session %d for %s", i, instance["question_id"])

    return id_map


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
    from claude_memory.schema import SearchMemoryParams

    results_env = await service.search(
        SearchMemoryParams(
            query=question,
            project_id=project_id,
            limit=10,
            deep=True,
        )
    )
    results = results_env.get("results", [])

    # results is list[SearchResult] — pydantic models with .id, .name, .observations
    retrieved_ids = [r.id for r in results]

    # Build answer from top results
    answer_parts = []
    for r in results[:3]:
        obs_text = "; ".join(r.observations[:3]) if r.observations else ""
        answer_parts.append(f"{r.name}: {obs_text}" if obs_text else r.name)

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

    # ── Initial flush: purge ALL existing entities from prior runs ──
    await _flush_prior_entities(service)

    results: list[dict[str, Any]] = []
    question_scores: list[dict[str, float]] = []
    start_time = time.monotonic()

    for i, instance in enumerate(dataset):
        qid = instance["question_id"]
        logger.info("[%d/%d] Processing %s", i + 1, len(dataset), qid)

        # Ingest -- returns mapping of dataset session IDs -> entity UUIDs
        id_map = await ingest_sessions(service, instance)

        # Query
        response = await query_system(service, instance["question"])

        # Translate answer_session_ids from dataset namespace -> our UUIDs
        answer_session_ids = instance.get("answer_session_ids", [])
        expected_uuids = [id_map[sid] for sid in answer_session_ids if sid in id_map]

        retrieved = response["retrieved_ids"]
        r_all_5 = recall_at_k(retrieved, expected_uuids, k=5)
        r_all_10 = recall_at_k(retrieved, expected_uuids, k=10)
        r_any_5 = recall_any_at_k(retrieved, expected_uuids, k=5)
        r_any_10 = recall_any_at_k(retrieved, expected_uuids, k=10)

        # Diagnostic: log rank positions of expected UUIDs
        rank_positions = []
        for uuid in expected_uuids:
            if uuid in retrieved:
                rank_positions.append(retrieved.index(uuid) + 1)  # 1-indexed
            else:
                rank_positions.append(-1)  # not found

        score = {
            "recall_all_at_5": r_all_5,
            "recall_all_at_10": r_all_10,
            "recall_any_at_5": r_any_5,
            "recall_any_at_10": r_any_10,
        }
        question_scores.append(score)

        if r_any_5 < 1.0:
            logger.debug(
                "MISS %s: expected=%s ranks=%s",
                qid,
                expected_uuids,
                rank_positions,
            )

        results.append(
            {
                "question_id": qid,
                "question_type": instance.get("question_type", "unknown"),
                "question": instance["question"],
                "expected_answer": instance["answer"],
                "hypothesis": response["answer"],
                "retrieved_ids": retrieved,
                "expected_uuids": expected_uuids,
                "id_map": id_map,
                "rank_positions": rank_positions,
                "metrics": score,
            }
        )

        # Cleanup: delete ingested sessions to prevent cross-question pollution
        for eid in id_map.values():
            try:
                # Hard-delete from all stores
                service.repo.delete_node(eid)
                await service.vector_store.delete(eid)
                if hasattr(service, "fts_store"):
                    service.fts_store.remove_entity(eid)
            except Exception:
                logger.debug("Cleanup delete failed for %s", eid, exc_info=True)

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
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disable cross-encoder reranking (ablation test)",
    )
    parser.add_argument(
        "--disable-channels",
        nargs="*",
        default=None,
        help="Zero out specific channels (e.g., temporal relational associative entity)",
    )
    parser.add_argument(
        "--no-observations",
        action="store_true",
        help="Skip observation storage during ingestion (faster runs)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from claude_memory.embedding import EmbeddingService
    from claude_memory.tools import MemoryService
    from claude_memory.vector_store import QdrantVectorStore

    embedder = EmbeddingService()

    # Use an ISOLATED Qdrant collection so benchmarks never touch real memories
    bench_vector_store = QdrantVectorStore(collection="longmemeval_bench")
    service = MemoryService(embedding_service=embedder, vector_store=bench_vector_store)

    # Override FTS to use a separate SQLite file
    from claude_memory.fts_store import FTSStore

    service.fts_store = FTSStore(db_path="longmemeval_fts.db")

    # Optionally disable reranker for ablation
    if args.no_rerank and hasattr(service, "reranker"):
        logger.info("Reranker DISABLED (--no-rerank)")
        delattr(service, "reranker")

    # Optionally disable specific channels
    if args.disable_channels:
        from claude_memory.router import QueryRouter

        original_get_weights = QueryRouter.get_channel_weights
        disabled = set(args.disable_channels)
        logger.info("Channels DISABLED: %s", disabled)

        @staticmethod  # type: ignore[misc]
        def patched_weights(intent):  # type: ignore[no-untyped-def]
            base = original_get_weights(intent)
            for ch in disabled:
                if ch in base:
                    base[ch] = 0.0
            return base

        QueryRouter.get_channel_weights = patched_weights  # type: ignore[assignment]

    # Optionally skip observation storage
    if args.no_observations:
        import sys

        sys.modules[__name__]._STORE_OBSERVATIONS = False  # type: ignore[attr-defined]
        logger.info("Observation storage DISABLED (--no-observations)")

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
