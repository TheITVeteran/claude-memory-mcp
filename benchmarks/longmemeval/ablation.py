"""Ablation study runner for the hybrid search pipeline.

Measures the marginal contribution of each retrieval channel by
running the benchmark with one channel zeroed out at a time.

Usage:
    python -m benchmarks.longmemeval.ablation --limit 50

Generates a per-channel recall delta table showing which channels
contribute most to retrieval quality.
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

# All retrieval channels in the pipeline
ALL_CHANNELS = ["vector", "fts", "entity", "temporal", "relational", "associative"]

# Ablation configurations: name → channels to DISABLE
ABLATION_CONFIGS: dict[str, list[str]] = {
    "baseline": [],  # All channels active — control group
    "no_fts": ["fts"],
    "no_entity": ["entity"],
    "no_temporal": ["temporal"],
    "no_relational": ["relational"],
    "no_associative": ["associative"],
    "no_graph": ["temporal", "relational", "associative"],  # Vector+FTS+Entity only
    "vector_only": ["fts", "entity", "temporal", "relational", "associative"],
}


def build_weight_override(disabled_channels: list[str]) -> dict[str, float]:
    """Build a weight dict with disabled channels zeroed out.

    Args:
        disabled_channels: Channel names to set to 0.0 weight.

    Returns:
        Weight dict suitable for QueryRouter.get_channel_weights override.
    """
    from claude_memory.router import QueryIntent, QueryRouter

    # Start from a neutral intent's weights
    weights = QueryRouter.get_channel_weights(QueryIntent.SEMANTIC)
    for ch in disabled_channels:
        if ch in weights:
            weights[ch] = 0.0
    return weights


async def run_single_ablation(
    service: Any,
    dataset: list[dict[str, Any]],
    config_name: str,
    disabled_channels: list[str],
    project_prefix: str = "ablation",
) -> dict[str, Any]:
    """Run the benchmark with specific channels disabled.

    Args:
        service: MemoryService instance.
        dataset: LongMemEval dataset instances.
        config_name: Name of this ablation config (e.g., "no_fts").
        disabled_channels: Channels to zero out.
        project_prefix: Project ID prefix for isolation.

    Returns:
        Dict with config name, aggregate metrics, and per-question scores.
    """
    from benchmarks.longmemeval.runner import ingest_sessions, query_system

    project_id = f"{project_prefix}_{config_name}"
    logger.info(
        "═══ Ablation: %s (disabled: %s) ═══",
        config_name,
        disabled_channels or "none",
    )

    # Monkey-patch get_channel_weights for this run
    from claude_memory.router import QueryRouter

    original_get_weights = QueryRouter.get_channel_weights

    @staticmethod  # type: ignore[misc]
    def patched_weights(intent: Any) -> dict[str, float]:
        base = original_get_weights(intent)
        for ch in disabled_channels:
            if ch in base:
                base[ch] = 0.0
        return base

    QueryRouter.get_channel_weights = patched_weights  # type: ignore[assignment]

    question_scores: list[dict[str, float]] = []
    per_question: list[dict[str, Any]] = []
    t0 = time.monotonic()

    try:
        for i, instance in enumerate(dataset):
            qid = instance["question_id"]

            # Ingest into an isolated project
            id_map = await ingest_sessions(service, instance, project_id=project_id)

            # Query
            response = await query_system(service, instance["question"], project_id=project_id)

            # Evaluate
            answer_session_ids = instance.get("answer_session_ids", [])
            expected_uuids = [id_map[sid] for sid in answer_session_ids if sid in id_map]
            retrieved = response["retrieved_ids"]

            score = {
                "recall_all_at_5": recall_at_k(retrieved, expected_uuids, k=5),
                "recall_all_at_10": recall_at_k(retrieved, expected_uuids, k=10),
                "recall_any_at_5": recall_any_at_k(retrieved, expected_uuids, k=5),
                "recall_any_at_10": recall_any_at_k(retrieved, expected_uuids, k=10),
            }
            question_scores.append(score)
            per_question.append({"question_id": qid, "metrics": score})

            if (i + 1) % 10 == 0:
                partial = aggregate_scores(question_scores)
                logger.info(
                    "  [%d/%d] %s R@5=%.1f%%",
                    i + 1,
                    len(dataset),
                    config_name,
                    partial["recall_any_at_5"] * 100,
                )
    finally:
        # Restore original weights
        QueryRouter.get_channel_weights = original_get_weights  # type: ignore[assignment]

    elapsed = time.monotonic() - t0
    aggregated = aggregate_scores(question_scores)

    return {
        "config": config_name,
        "disabled_channels": disabled_channels,
        "instances": len(dataset),
        "elapsed_seconds": round(elapsed, 2),
        "aggregate_metrics": aggregated,
        "per_question": per_question,
    }


def format_ablation_table(results: list[dict[str, Any]]) -> str:
    """Format ablation results as a markdown table.

    Args:
        results: List of per-config result dicts.

    Returns:
        Markdown table string.
    """
    baseline = None
    for r in results:
        if r["config"] == "baseline":
            baseline = r
            break

    lines = [
        "| Config | Disabled | R@5 (any) | R@10 (any) | R@5 (all) | Δ R@5 |",
        "|--------|----------|-----------|------------|-----------|-------|",
    ]

    for r in results:
        m = r["aggregate_metrics"]
        r5 = m["recall_any_at_5"] * 100
        r10 = m["recall_any_at_10"] * 100
        r5_all = m["recall_all_at_5"] * 100
        delta = ""
        if baseline and r["config"] != "baseline":
            base_r5 = baseline["aggregate_metrics"]["recall_any_at_5"] * 100
            diff = r5 - base_r5
            delta = f"{diff:+.1f}pp"

        disabled = ", ".join(r["disabled_channels"]) or "—"
        lines.append(
            f"| {r['config']} | {disabled} | {r5:.1f}% | {r10:.1f}% | {r5_all:.1f}% | {delta} |"
        )

    return "\n".join(lines)


async def run_ablation_study(
    service: Any,
    variant: str = "oracle",
    limit: int | None = None,
    configs: dict[str, list[str]] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full ablation study across all configurations.

    Args:
        service: MemoryService instance.
        variant: Dataset variant.
        limit: Max instances per config.
        configs: Override default ablation configs.
        output_path: Where to save results JSON.

    Returns:
        Combined results dict with all configs.
    """
    from benchmarks.longmemeval.runner import download_dataset

    if configs is None:
        configs = ABLATION_CONFIGS

    dataset = download_dataset(variant)
    if limit:
        dataset = dataset[:limit]

    logger.info("Starting ablation study: %d configs x %d instances", len(configs), len(dataset))

    all_results: list[dict[str, Any]] = []
    for config_name, disabled in configs.items():
        result = await run_single_ablation(service, dataset, config_name, disabled)
        all_results.append(result)

    # Build summary table
    table = format_ablation_table(all_results)
    logger.info("\n\nAblation Results:\n%s\n", table)

    output = {
        "study": "ablation",
        "variant": variant,
        "instances_per_config": len(dataset),
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "configs": all_results,
        "summary_table": table,
    }

    if output_path is None:
        output_path = Path(__file__).parent / "results" / "ablation_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info("Ablation results saved to %s", output_path)
    return output


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run ablation study")
    parser.add_argument("--dataset", choices=["oracle", "small", "medium"], default="oracle")
    parser.add_argument("--limit", type=int, default=50, help="Instances per config")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument(
        "--configs",
        nargs="*",
        default=None,
        help="Specific configs to run (default: all)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from claude_memory.embedding import EmbeddingService
    from claude_memory.tools import MemoryService

    embedder = EmbeddingService()
    service = MemoryService(embedding_service=embedder)

    configs = None
    if args.configs:
        configs = {k: ABLATION_CONFIGS[k] for k in args.configs if k in ABLATION_CONFIGS}

    output_path = Path(args.output) if args.output else None
    asyncio.run(
        run_ablation_study(
            service=service,
            variant=args.dataset,
            limit=args.limit,
            configs=configs,
            output_path=output_path,
        )
    )


if __name__ == "__main__":
    main()
