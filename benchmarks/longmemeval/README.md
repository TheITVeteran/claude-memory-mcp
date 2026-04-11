# LongMemEval Benchmark for Dragon Brain

[LongMemEval](https://arxiv.org/abs/2410.10813) (ICLR 2025) is the industry-standard benchmark for evaluating AI memory systems. It tests session-document retrieval across 500 questions in 6 categories.

## Quick Start

```bash
# 1. Ensure Dragon Brain infrastructure is running
docker compose up -d

# 2. Run the benchmark (downloads dataset automatically)
python -m benchmarks.longmemeval.runner --dataset oracle --limit 10   # pilot (10 questions)
python -m benchmarks.longmemeval.runner --dataset oracle              # full (500 questions)

# 3. Results are saved to benchmarks/longmemeval/results/
```

## Dataset Variants

| Variant | Description | File |
|---------|-------------|------|
| `oracle` | Ground-truth sessions only (smallest, fastest) | `longmemeval_oracle.json` |
| `small` | Small haystack per question | `longmemeval_s_cleaned.json` |
| `medium` | Medium haystack per question | `longmemeval_m_cleaned.json` |

The dataset is automatically downloaded from [HuggingFace](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) and cached in `benchmarks/longmemeval/data/`.

## Options

```
python -m benchmarks.longmemeval.runner --help

--dataset {oracle,small,medium}   Dataset variant (default: oracle)
--limit N                         Max instances to evaluate (default: all)
--output PATH                     Custom output path for results JSON
```

## How It Works

1. **Download** the LongMemEval dataset (cached after first run)
2. **Ingest** each question's haystack sessions as Dragon Brain entities
3. **Query** the system with the evaluation question using `search_memory`
4. **Evaluate** retrieval Recall@5 and Recall@10 against ground truth
5. **Aggregate** scores and save results JSON

## Metrics

- **Recall@K**: Fraction of ground-truth relevant sessions found in top-K results
- Results are broken down by question type for detailed analysis

## Current Results

See [RESULTS.md](RESULTS.md) for the full breakdown.

| Metric | Score |
|--------|-------|
| R@5 | 61.3% |
| R@10 | 69.9% |
| Time | 20.8 min (500 questions) |

## Files

| File | Purpose |
|------|---------|
| `runner.py` | Main benchmark pipeline (ingest → query → evaluate) |
| `metrics.py` | Recall@K and NDCG@K implementations |
| `RESULTS.md` | Published benchmark scores |
| `data/` | Cached datasets (gitignored) |
| `results/` | Output JSON files (gitignored) |
