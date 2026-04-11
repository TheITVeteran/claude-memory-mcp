# Dragon Brain — LongMemEval Results

**Dataset:** LongMemEval Oracle (xiaowu0162/LongMemEval, ICLR 2025)
**Dragon Brain version:** 1.0.1
**Date:** 2026-04-11
**Mode:** hybrid (default `search_memory`, no benchmark-specific tuning)

## Headline

- **R@5:** 61.3%
- **R@10:** 69.9%
- **500 questions** across 6 types, completed in 20.8 minutes

## Per-Question-Type Breakdown

| Question Type | Count | R@5 | R@10 |
|---|---|---|---|
| Single-session assistant | 56 | **92.9%** | **94.6%** |
| Multi-session | 133 | **68.7%** | **79.1%** |
| Temporal reasoning | 133 | 60.9% | 72.7% |
| Knowledge update | 78 | 56.4% | 66.0% |
| Single-session preference | 30 | 43.3% | 53.3% |
| Single-session user | 70 | 35.7% | 38.6% |
| **Total** | **500** | **61.3%** | **69.9%** |

## How We Compare

| System | R@5 | Requires LLM | Local | Graph Reasoning |
|--------|-----|--------------|-------|----|
| MemPalace (raw) | 96.6% | No | Yes | No |
| MemPalace (hybrid+rerank) | 100% | Yes | Yes | No |
| **Dragon Brain (hybrid)** | **61.3%** | **No** | **Yes** | **Yes** |
| Mem0 | ~85% | Yes | No | No |

## Honest Assessment

Dragon Brain scores 61.3% R@5 against MemPalace's 96.6%. This gap is real and is explained by two factors:

### 1. Ingestion Strategy (fixable)

The current benchmark runner ingests each session as a single entity with a **500-character truncated description**. LongMemEval conversations often have thousands of tokens per session — we're discarding most of the content. MemPalace was purpose-built for session-document retrieval and ingests full conversation text.

**Impact:** This truncation directly hurts `single-session-user` (35.7%) and `single-session-preference` (43.3%) — question types that depend on granular details within sessions.

### 2. Architectural Mismatch (by design)

LongMemEval measures **session-document retrieval** — "given a question, find which conversation contained the answer." This is a pure information retrieval task that rewards flat document search.

Dragon Brain's architecture was designed for **structural reasoning** — understanding how knowledge entities relate to each other, discovering missing connections, tracking concept evolution. These capabilities (semantic radar, spreading activation, graph traversal) are invisible to LongMemEval.

### Where Dragon Brain Excels

The **92.9% R@5 on assistant-style questions** and **68.7% on multi-session questions** show that Dragon Brain's hybrid search (vector + graph enrichment) is strong when the retrieval task aligns with its entity-centric model.

## Methodology

- Sessions ingested as entities with truncated description (500 chars) + embedding
- Standard `search_memory` used — no benchmark-specific tuning
- Full dataset: 500 questions across 6 types (oracle variant)
- No LLM used for reranking or answer generation
- No dataset-specific prompt engineering
- Test environment: Windows, Python 3.12, Docker (FalkorDB + Qdrant + BGE-M3 CPU)

## Reproduce

```bash
# Start Dragon Brain infrastructure
docker compose up -d

# Run the benchmark (full dataset, ~21 minutes)
python -m benchmarks.longmemeval.runner --dataset oracle

# Results saved to benchmarks/longmemeval/results/results_oracle.json
```
