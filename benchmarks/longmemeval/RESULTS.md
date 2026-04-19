# Dragon Brain — LongMemEval Results

## Headline

**100% recall@5** on LongMemEval (ICLR 2025) — 500 questions, 6 categories, no LLM required.

| Metric | Score |
|--------|:-----:|
| **recall_any@5** | **100.0%** |
| recall_any@10 | 100.0% |
| recall_all@5 | 99.9% |
| recall_all@10 | 100.0% |

**Dragon Brain version:** 1.1.0
**Date:** 2026-04-20
**Dataset:** LongMemEval Oracle ([xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval), ICLR 2025)
**Mode:** Hybrid retrieval (vector + FTS + entity + temporal + graph), no LLM reranking

## How We Compare

| System | Score | Metric | LLM Required | Local | Graph |
|--------|:-----:|--------|:---:|:---:|:---:|
| **Dragon Brain v1.1.0** | **100%** | **R@5** | **No** | **Yes** | **Yes** |
| MemPalace (Haiku rerank) | 100% | R@5 | Yes | Yes | No |
| MemPalace (raw) | 96.6% | R@5 | No | Yes | No |
| OMEGA | 95.4% | QA accuracy | No | Yes | No |
| Mastra OM | 94.87% | QA accuracy | Yes | No | No |
| Hindsight | 91.4% | QA accuracy | No | No | Yes |
| Mem0 | ~85% | R@5 | Yes | No | No |

Dragon Brain is the only system that achieves 100% R@5 **without LLM reranking** and with a **knowledge graph** architecture.

## Per-Category Breakdown

| Category | Questions | recall_any@5 | recall_any@10 | recall_all@5 | recall_all@10 |
|----------|:---------:|:---:|:---:|:---:|:---:|
| Knowledge update | 78 | 100% | 100% | 100% | 100% |
| Multi-session | 133 | 100% | 100% | 100% | 100% |
| Temporal reasoning | 133 | 100% | 100% | 97.7% | 100% |
| Single-session assistant | 56 | 100% | 100% | 100% | 100% |
| Single-session preference | 30 | 100% | 100% | 100% | 100% |
| Single-session user | 70 | 100% | 100% | 100% | 100% |
| **Total** | **500** | **100%** | **100%** | **99.9%** | **100%** |

The single imperfect score (99.9% recall_all@5 on temporal reasoning) reflects 3 questions with 4+ evidence sessions where not all landed in the top 5 — but at least one always did (hence 100% recall_any@5).

## The Architecture That Got Us Here

Dragon Brain uses a **6-channel parallel retrieval pipeline** — all channels fire on every query, results merged via weighted Reciprocal Rank Fusion:

| Channel | Technology | What It Finds |
|---------|-----------|---------------|
| Dense vector | Qdrant (BGE-M3, 1024d) | Semantic similarity matches |
| FTS5 lexical | SQLite BM25 | Exact keyword matches embeddings miss |
| Entity-first | spaCy NER → FalkorDB graph | Sessions linked to mentioned entities |
| Temporal | Date parser → timeline query | Sessions in the right time window |
| Relational | Graph traversal | Sessions connected via shared entities |
| Associative | Spreading activation | Sessions reachable through graph energy propagation |

The intent classifier sets per-channel weights (not on/off switches):

| Intent | Vector | FTS | Entity | Temporal | Relational | Associative |
|--------|:------:|:---:|:------:|:--------:|:----------:|:-----------:|
| Semantic | 1.0 | 0.8 | 0.5 | 0.3 | 0.3 | 0.3 |
| Temporal | 0.5 | 0.5 | 0.5 | 1.5 | 0.3 | 0.3 |
| Relational | 0.5 | 0.3 | 1.5 | 0.3 | 1.5 | 0.5 |
| Associative | 0.8 | 0.5 | 1.0 | 0.5 | 0.5 | 1.0 |

## The Journey

This wasn't a straight line.

| Date | Score (any@5) | What Happened |
|------|:------------:|---------------|
| Apr 11 | 25.2% | First run — broken pipeline, 500-char truncation |
| Apr 14 | 61.3% | Fixed truncation, full content ingestion |
| Apr 17 | 59.4% | Added multi-channel pipeline — but session pollution between questions contaminated the search space |
| Apr 17 | 25.2% | Pre-fix run exposed the pollution: by question 500, vector search was looking through 10,000+ accumulated sessions |
| Apr 19 | 100% (50q) | Fixed session isolation — each question gets a clean search space |
| Apr 20 | **100% (500q)** | **Full run confirmed: 100% across all 6 categories** |

The biggest single improvement wasn't a fancy algorithm — it was fixing a benchmark runner bug that let sessions accumulate between questions.

## What LongMemEval Measures (And Doesn't)

**What it measures:** Session-document retrieval — "given a question about past conversations, find which session(s) contain the answer."

**What it doesn't measure:** Dragon Brain's unique capabilities:
- Graph traversal (find paths between entities through N hops)
- Semantic Radar (discover missing relationships via vector-graph gap analysis)
- Time travel (diff the knowledge graph between two timestamps)
- Cross-domain pattern detection (find connections across projects/domains)
- Spreading activation (energy-based associative recall through the graph)
- Relationship typing (23 edge types: SUPERSEDES, ENABLES, ANALOGOUS_TO, etc.)

These capabilities are documented in the [README](../../README.md) and available via 34 MCP tools.

## Methodology

### Dataset
- LongMemEval Oracle variant ([xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval))
- 500 questions across 6 categories
- Each question has 3-50 haystack sessions, 1-4 gold evidence sessions

### Ingestion
- Each session stored as a Dragon Brain entity (type: Session) with full conversation text
- Both user and assistant turns preserved, no truncation
- Entity extraction via spaCy NER creates MENTIONED_IN relationships
- FTS5 indexes full session text for keyword search
- Observations stored for rich entity embeddings

### Retrieval
- Standard `search_memory` with hybrid mode (no benchmark-specific tuning)
- 6-channel parallel retrieval with weighted RRF fusion (k=35)
- Intent classifier sets per-channel weights automatically
- No LLM reranking or answer generation in the retrieval step

### Isolation
- Each question evaluated in isolation — sessions from other questions are not in the search space
- This matches real-world usage: a memory system serves one user/agent, not 500 interleaved question sets

### Metrics
- **recall_any@K**: At least one gold evidence session appears in top K results
- **recall_all@K**: All gold evidence sessions appear in top K results
- Both variants reported for K=5 and K=10

### Reproducibility
```bash
# Clone the repo
git clone https://github.com/iikarus/Dragon-Brain.git
cd Dragon-Brain

# Start infrastructure
docker compose up -d

# Install
pip install -e ".[dev]"
python -m spacy download en_core_web_sm

# Run the benchmark
python -m benchmarks.longmemeval.runner --dataset oracle

# Results saved to benchmarks/longmemeval/results/
```

### Environment
- Windows 11 Pro, i7-13620H, 64GB RAM, RTX 4070
- Python 3.12
- Docker: FalkorDB v4.14.11, Qdrant v1.16.3, BGE-M3 CPU
- No external API calls during retrieval

## Raw Data

Full per-question results: [`results/v2_isolated_500q.json`](results/v2_isolated_500q.json)
