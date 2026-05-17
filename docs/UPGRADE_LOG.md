# Upgrade Log: V2 Intelligence Layer

> Tracks what was added, changed, or upgraded from the Phase 3 baseline (Feb 6, 2026) through the current V2 build (Feb 14, 2026).

---

## Baseline (Phase 3 — `7e135bb`, Feb 6)

The system at Phase 3 completion had:

| Metric         | Value                                     |
| -------------- | ----------------------------------------- |
| MCP Tools      | 17                                        |
| Source Modules | 14                                        |
| Unit Tests     | 255                                       |
| Coverage       | 100%                                      |
| Test Files     | 15                                        |
| Scripts        | 12                                        |
| Tox Tiers      | 4 (pulse, gate, hammer, polish)           |
| Search         | Vector-only (Qdrant cosine similarity)    |
| Retrieval      | Hologram (BFS subgraph expansion)         |
| Maintenance    | Librarian (cluster + consolidate + prune) |

---

## Phase 10: Qdrant + Salience (`0580f04`, `2a9f763`)

**What changed:**

| Before                     | After                                                               |
| -------------------------- | ------------------------------------------------------------------- |
| Basic cosine search        | **MMR diversity search** (`mmr=True` flag)                          |
| Default HNSW threshold     | **Optimized HNSW** indexing (threshold: 5000)                       |
| No payload index on `name` | **Full-text payload index** on `name` field                         |
| No salience scoring        | **Salience scoring** — nodes gain weight on access, decay over time |
| 255 tests                  | 271 tests                                                           |

**New modules:** None
**New MCP tools:** None (salience is transparent to consumers)

---

## Phase 11: Temporal Graph Layer (`c52a69c` → `2ddf17c`)

**What changed:**

| Before                      | After                                                                |
| --------------------------- | -------------------------------------------------------------------- |
| No time awareness           | **`occurred_at` timestamp** on all entities                          |
| No temporal edges           | **`PRECEDED_BY`** and **`CONCURRENT_WITH`** edges                    |
| No timeline queries         | **`query_timeline(start, end)`** — chronological retrieval           |
| No temporal neighbors       | **`get_temporal_neighbors(id, direction)`** — before/after traversal |
| No time-travel search       | **`point_in_time_query(query, as_of)`** — historical search          |
| No message bottles          | **`get_bottles()`** — timestamped notes to future self               |
| Sessions are plain entities | **Sessions as temporal anchors** — automatic PRECEDED_BY linking     |
| 271 tests                   | 313 tests                                                            |

**New modules:** None (temporal logic embedded in `repository.py`, `tools.py`, `schema.py`)
**New MCP tools:** `query_timeline`, `get_temporal_neighbors`, `get_bottles` (+3)
**New scripts:** `scripts/backfill_temporal.py` (migration)

---

## Phase 12: Spreading Activation Retrieval (`a3eb081`, `6a6d09b`)

**What changed:**

| Before                   | After                                                                     |
| ------------------------ | ------------------------------------------------------------------------- |
| Vector-only search       | **Spreading activation** — energy propagation through graph edges         |
| No associative retrieval | **`search_associative()`** — combines vector + graph + salience + recency |
| Fixed scoring            | **Configurable score weights** (env vars + per-query overrides)           |
| 313 tests                | 340+ tests                                                                |

**New modules:** `activation.py` (ActivationEngine)
**New MCP tools:** `search_associative` (+1)

---

## Phase 13: Adaptive Query Routing (`4423b79`, `6649c42`)

**What changed:**

| Before                          | After                                                                              |
| ------------------------------- | ---------------------------------------------------------------------------------- |
| All queries go to vector search | **Automatic intent classification** → appropriate strategy                         |
| No query routing                | **`QueryRouter`** — classifies `SEMANTIC`, `ASSOCIATIVE`, `TEMPORAL`, `RELATIONAL` |
| No strategy override            | **`strategy` param** on `search_memory()` MCP tool                                 |
| Manual search selection         | **`search(strategy='auto')`** — router picks best path                             |

**New modules:** `router.py` (QueryRouter)
**New MCP tools:** None (wired into existing `search_memory`)

---

## Testing Directive Audit (`0b45a9b`, `a971589`)

**What changed:**

| Before                            | After                                                       |
| --------------------------------- | ----------------------------------------------------------- |
| 4 tox tiers                       | **5 tox tiers** — added `forge` (focused unit tests)        |
| Some implementation-coupled tests | **11 impl assertions removed** — tests verify behavior only |
| 3 overly-deep mock tests          | **Dropped and replaced** with pragmatic alternatives        |
| 1 pure-branch test                | **Deleted** — didn't catch real bugs                        |

---

## Phase 14: Embedding Evaluation (`8e58f24`, `0b1fcf9`)

**What changed:**

| Before                  | After                                                                          |
| ----------------------- | ------------------------------------------------------------------------------ |
| No embedding benchmarks | **`scripts/embedding_eval.py`** — 3-stage eval harness                         |
| Assumed BGE-M3 is best  | **Benchmarked**: BGE-M3 (r@10=0.926, 14.4ms) vs MiniLM (r@10=0.923, 0.8ms)     |
| No model decision       | **Decision: STAY with BGE-M3** — marginal recall advantage, acceptable latency |

**New scripts:** `scripts/embedding_eval.py`

---

## Phase 15: Structural Gap Analysis (`87a2906` → `0dfa554`)

**What changed:**

| Before                     | After                                                                          |
| -------------------------- | ------------------------------------------------------------------------------ |
| No graph health metrics    | **`graph_health()`** — nodes, edges, density, orphans, communities, avg degree |
| No gap detection           | **`detect_gaps()`** — finds disconnected but similar knowledge clusters        |
| No research prompts        | **Auto-generated research prompts** per detected gap                           |
| No knowledge gap MCP tool  | **`find_knowledge_gaps()`** MCP tool                                           |
| Librarian: cluster + prune | Librarian: cluster + prune + **gap detection + GapReport entities**            |

**New MCP tools:** `graph_health`, `find_knowledge_gaps` (+2)

---

## Hotfix: Logging to stderr (`1f36e09`)

**What changed:**

| Before                            | After                                                  |
| --------------------------------- | ------------------------------------------------------ |
| Logging handler used `sys.stdout` | **`sys.stderr`** — stdout is reserved for MCP JSON-RPC |

**Impact**: All MCP clients (Desktop, CLI, VS Code, Antigravity) failed with "Unexpected non-whitespace character after JSON" because log messages corrupted the stdio transport.

---

## Post-Production Audit (`3052347` → `06aafec` → `c4ddb52`, Feb 11)

### Phase 1 — WILL BITE YOU (`3052347`)

| Before                          | After                                                  |
| ------------------------------- | ------------------------------------------------------ |
| cp1252 crashes headless scripts | **`PYTHONUTF8=1`** in subprocess calls                 |
| Silent upsert failures          | **`ON CREATE SET` / `ON MATCH SET`** — explicit Cypher |
| Raw f-string Cypher injection   | **Parameterized `$params`** for all user inputs        |

### Phase 2 — SHOULD FIX (`06aafec`)

| Before                             | After                                                       |
| ---------------------------------- | ----------------------------------------------------------- |
| No connection retry                | **Exponential backoff** (3 attempts, `_connect_with_retry`) |
| FalkorDB unbounded memory          | **`--maxmemory 256mb`** in docker-compose                   |
| LockManager uses FALKORDB\_\* only | **REDIS\_\* takes precedence** over FALKORDB\_\*            |
| Duplicate `_fire_salience_update`  | **Deduplicated** — MRO resolves to CrudMixin                |
| No system health probe             | **`scripts/healthcheck.ps1`** (FalkorDB, Qdrant, Embedding) |

### Phase 3 — Backup & Restore (Operational)

| Before              | After                                                      |
| ------------------- | ---------------------------------------------------------- |
| No scheduled backup | **`ExocortexBackup`** task at 3:00 AM daily                |
| Backup untested     | **Live tested**: 858 KB + 4773 KB, Google Drive synced     |
| Restore untested    | **Restore verified**: 695 nodes intact, containers healthy |
| No live e2e test    | **`scripts/e2e_test.py`** — 14-check lifecycle (`c4ddb52`) |

---

## Phase 2 — WILL BITE YOU (`e7dd19c`, Feb 11)

### W1 — Alerting

| Before                    | After                                                       |
| ------------------------- | ----------------------------------------------------------- |
| No backup status tracking | **`last_run_status.json`** written by `scheduled_backup.py` |
| Health check: infra only  | **`healthcheck.ps1`** now monitors backup age + status      |

### W2 — FalkorDB Memory

| Before              | After                                         |
| ------------------- | --------------------------------------------- |
| `--maxmemory 256mb` | **`--maxmemory 1gb`** in `docker-compose.yml` |

### W3 — Strict Consistency (Split-Brain Prevention)

| Before                          | After                                                                      |
| ------------------------------- | -------------------------------------------------------------------------- |
| Qdrant write failures → warning | **Raises exception** by default (`EXOCORTEX_STRICT_CONSISTENCY=true`)      |
| Split-brain possible            | **Fail-loudly** prevents silent data divergence                            |
| `delete_entity` C901 complexity | **Extracted `_safe_vector_delete`** helper to reduce cyclomatic complexity |

### W4/W5 — Scheduled Tasks

| Before                          | After                                                                    |
| ------------------------------- | ------------------------------------------------------------------------ |
| Manual backup/health management | **`setup_scheduled_tasks.ps1`** — idempotent Task Scheduler registration |
| No health check schedule        | **ExocortexHealthCheck** every 15 minutes                                |

### E2E UAT (`tests/e2e_functional.py`)

| Before                        | After                                                  |
| ----------------------------- | ------------------------------------------------------ |
| 14-check legacy e2e script    | **52-check exhaustive UAT** — 18 phases, 43.8s runtime |
| No strict consistency testing | **W3 verified live** (strict + lenient modes)          |
| No vector verification        | **Qdrant point verification** per entity               |

---

## Docker Migration + Bug Fixes (`54dcaec`, `f33ab01`, Feb 13)

### Docker Image Pinning

| Before                     | After                                                   |
| -------------------------- | ------------------------------------------------------- |
| `falkordb/falkordb:latest` | **`falkordb/falkordb:v4.14.11`** — pinned for stability |
| `qdrant/qdrant:v1.13.2`    | **`qdrant/qdrant:v1.16.3`** — +134 recovered vectors    |

### Performance Fix: Louvain O(n²) → NetworkX

| Before                     | After                                              |
| -------------------------- | -------------------------------------------------- |
| Custom pure-Python Louvain | **NetworkX `louvain_communities()`** — C-optimized |
| E2E hung 15+ minutes       | **< 1 second** for 695-node graph                  |

### Bug Fixes

| Bug                         | Cause                                                     | Fix (commit)                                 |
| --------------------------- | --------------------------------------------------------- | -------------------------------------------- |
| Salience never updated      | FalkorDB doesn't support `log2()`                         | `log(x)/log(2)` (`54dcaec`)                  |
| `traverse_path` crashed     | `shortestPath` in MATCH clause (FalkorDB-incompatible)    | Moved to WITH clause (`f33ab01`)             |
| `get_bottles` returned `[]` | Queried property `n.node_type='Bottle'` instead of label  | Changed to `MATCH (n:Bottle)` (`f33ab01`)    |
| `tox -e forge` crashed      | mutatest 3.1.0 passes `set` to `random.sample()` (Py3.12) | Wrapper script `run_mutatest.py` (`f33ab01`) |

---

## Cumulative Summary

| Metric                | Phase 3 (Baseline) | Current (V2)                                       | Delta |
| --------------------- | ------------------ | -------------------------------------------------- | ----- |
| **MCP Tools**         | 17                 | 29                                                 | +12   |
| **Source Modules**    | 14                 | 29                                                 | +15   |
| **Unit Tests**        | 255                | 463                                                | +208  |
| **Test Files**        | 15                 | 46                                                 | +31   |
| **Scripts**           | 12                 | 42                                                 | +30   |
| **Tox Tiers**         | 4                  | 5                                                  | +1    |
| **Search Strategies** | 1 (vector)         | 4 (semantic, associative, temporal, relational)    | +3    |
| **Graph Features**    | Basic CRUD         | Temporal edges, salience, activation, gap analysis | —     |
| **Graph Data**        | —                  | 700 nodes, 1253 edges                              | —     |
| **E2E Phases**        | —                  | 31 phases, 74 checks                               | —     |

### New Source Modules (V2)

- `activation.py` — Spreading activation engine
- `analysis.py` — AnalysisMixin (graph health, gaps, stale, consolidation)
- `crud.py` — CrudMixin (entity/relationship/observation CRUD)
- `search_advanced.py` — Advanced search helpers (hologram, activation wiring)
- `temporal.py` — TemporalMixin (sessions, breakthroughs, timeline)
- `tools_extra.py` — Extra MCP tool registrations
- `repository_queries.py` — Query builder helpers for repository
- `router.py` — Query intent classification
- `context_manager.py` — Session context management
- `ontology.py` — Runtime type system (existed but undocumented)
- `retry.py` — `@retry_on_transient` decorator
- `crud_maintenance.py` — CrudMaintenanceMixin (observation CRUD, salience updates)

### New MCP Tools (V2)

1. `search_associative` — Graph-aware associative search
2. `query_timeline` — Chronological time-window queries
3. `get_temporal_neighbors` — Before/after temporal traversal
4. `get_bottles` — Message-in-a-bottle retrieval
5. `graph_health` — Graph health metrics
6. `find_knowledge_gaps` — Structural gap detection
7. `search_memory` (upgraded) — `strategy` and `mmr` params added
8. `create_entity` (upgraded) — Auto-links `PRECEDED_BY` edges
9. `reconnect` — Session reconnect briefing (E-4)
10. `system_diagnostics` — Unified backend health check (E-5)

---

## Audit Remediation (`2b34df1` → `b3c8d4f` → `dd27ded`, Feb 13)

### Phase 3a — WILL BITE YOU (`2b34df1`)

| Before                                               | After                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------ |
| Observation vector upsert failure silently swallowed | **Raises exception** — prevents split-brain (TDD: Red→Green) |

### Phase 3b — SHOULD FIX (`b3c8d4f`)

| Before                                   | After                                                                                   |
| ---------------------------------------- | --------------------------------------------------------------------------------------- |
| 16 bare `except Exception` catches       | **Narrowed** to specific types (`FalkorDBError`, `QdrantException`, `RedisError`, etc.) |
| Bare `# type: ignore` in `repository.py` | **Scoped** to `# type: ignore[no-any-return]`                                           |
| `shell=True` in `dashboard/app.py`       | **Removed** — security fix                                                              |
| No `requirements.lock`                   | **Generated** `requirements.lock`                                                       |

### Phase 3c — COSMETIC (`dd27ded`)

| Before                                   | After                                       |
| ---------------------------------------- | ------------------------------------------- |
| `sys.path.append` hack in dashboard      | **Removed** — package installed via pip     |
| `app.py` monolithic `main()` (C901)      | **Extracted** 4 renderer functions          |
| Globals undocumented in `tools_extra.py` | **Documented** with module-level docstrings |

---

## Audit Remediation Round 2 (May 13-17, 2026, v1.2.0 → v1.2.1)

Codex 5.5 added as a formal **Auditor seat** in the AI Council trifecta. Codex independently caught three production bugs the prior trifecta (Architect + Builder only) missed across 10 batches of Round 1 remediation. Full process docs in `process/`.

### PR-1: Cypher Label Injection Guard (`56f888d`)

| Before                                                                       | After                                                                                          |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `MERGE (n:{label}:Entity ...)` interpolated unvalidated user input           | **Pydantic validator** on `CreateMemoryTypeParams.name` — regex `[A-Z][A-Za-z0-9_]{0,63}`      |
| No defense-in-depth at repo layer                                            | **Defensive `assert`** on `label` in `repository.create_node` — catches future-bypass paths    |
| Memory type names could corrupt graph schema silently                        | Invalid names raise `ValidationError` at MCP boundary; `AssertionError` at repo on direct call |

### PR-2: Point-in-Time `created_at` Payload Contract (`1489886`)

| Before                                                                | After                                                                                            |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `point_in_time_query` filtered Qdrant on `created_at` field           | **`created_at` written to payload** at all three sites (create_entity, add_observation, re-embed) |
| Qdrant payload only had `name`, `node_type`, `project_id`             | Existing points repaired via `scripts/backfill_created_at_payload.py`                            |
| Filter silently returned wrong answers (everything or empty)          | Live-safe, zero-downtime, idempotent backfill (~2228 points in <2 min)                           |

### PR-3: Temporal Direction Enum Drift (`21b097a`)

| Before                                                                | After                                                                                  |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Schema accepted `forward`/`backward`/`both`                           | Schema accepts `before`/`after`/`both`/`forward`/`backward` — all four spellings first-class |
| Repo only branched on `before`/`after` — others fell through to "both" | Repo treats `before`=`backward` (past) and `after`=`forward` (future) as semantic equivalents |
| `direction="forward"` was a silent wrong-answer bug                   | No DeprecationWarning, no churn — both naming conventions accepted permanently         |

### PR-4: Observation Cross-Store Compensation (`e3a1ca8`)

| Before                                                                | After                                                                                  |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `add_observation` graph-write success + Qdrant failure → orphan obs   | **Qdrant failure triggers graph `DETACH DELETE`** + raises `SearchError`               |
| Asymmetric with `create_entity` (which DID compensate)                | Now symmetric — same pattern, same `SearchError` class, same log message format        |
| Integration tests didn't exercise Qdrant-kill-mid-`add_observation`   | New `test_kill_qdrant_mid_add_observation_compensates` with real `container.kill()`    |

### PR-5: Channel Degradation Surfaced Through MCP (`d1f2bd2` → `dd26413`)

| Before                                                                | After                                                                                  |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Per-channel health computed but discarded                             | **`search_memory(include_meta=True).metadata.channels`** exposes all 6 channels        |
| Shared `self._last_*` instance attrs (TOCTOU between concurrent calls) | **Per-call dict return shape** — no shared state, no crosstalk                         |
| `MemoryService.search()` returned `list[SearchResult]`                | Service returns `dict` with `results` + `metadata`; MCP boundary strips when `include_meta=False` |
| All internal callers used positional args                             | Service signature: `params: SearchMemoryParams` (Pydantic); ~10 internal sites updated |
| 6 audit rounds to clear (caught real defects: test bug, scope creep, dashboard breakage) | Final clean landing with full test-first evidence + complete caller sweep              |

### PR-6: Contract Scanner Precision (`e1e0318`)

| Before                                                                | After                                                                                  |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Pattern 10 flagged `self.repo.X(...)` inside async def without checking `await` | **Await-detection** — `awaited_calls` set built from AST; awaited calls exempt from Pattern 10 |
| 62 false positives from properly-migrated B10 wrapper calls           | Scanner reports actual baseline: **13 violations** (down from 75)                      |
| CI gate silently failing since B10                                    | CI gate green at absolute baseline 13                                                  |
| PR-4 also added `is_allowlisted(node)` honoring (out-of-spec scope creep, accepted) | Both mechanisms coexist: manual noqa markers + automatic await detection               |

### Cumulative changes (Round 2)

| Metric                      | Round 1 close (v1.2.0) | Round 2 close (v1.2.1) |
| --------------------------- | ---------------------- | ---------------------- |
| Unit tests                  | 1,166                  | 1,278                  |
| Integration tests           | 5                      | 7 (added PIT + observation compensation) |
| Contract scanner violations | 75 (with 62 FPs)       | 13 (true baseline)     |
| MCP tools                   | 34                     | 34 (no new tools; behavior fixes) |
| Process artifacts location  | root                   | `process/`             |
| AI Council seats formalized | 3 (Architect/Builder/Director) | 4 (+ Auditor)  |

### New scripts

- `scripts/backfill_created_at_payload.py` — one-shot live-safe backfill for PR-2's Qdrant payload contract change

### Files reorganized

- `REMEDIATION_BUILD_SPEC.md`, `REMEDIATION_AUDIT_SPEC.md`, `PR_1_HANDOFF.md` through `PR_6_HANDOFF.md` moved from repo root into `process/`
- New `process/README.md` explaining the directory and the AI Council trifecta workflow
