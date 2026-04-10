# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Diff Mode** (`e7da6aa`) — `diff_knowledge_state` MCP tool for time-based
  knowledge graph diffs. Shows added/removed/evolved entities and relationships
  between two timestamps. Supports `include_observations` for per-entity
  observation diffs.
- **Entity Embedding Quality Fix** (`dcbab40`) — Write-time observation-aware
  embeddings. `_compute_entity_embedding_text()` centralizes embedding text
  generation; `add_observation` triggers parent entity re-embedding for richer
  semantic matching.
- **Semantic Radar Dashboard Tab** (`fb07392`, `12b1293`) — New "Radar" tab in
  Streamlit dashboard with `radar_viz.py` for interactive relationship discovery
  visualization. Includes entity name resolution fix.
- **LongMemEval Benchmark Infrastructure** — `benchmarks/longmemeval/` with
  `runner.py` and `metrics.py` for standardized benchmark evaluation.
- `scripts/reembed_entities.py` — Migration script to re-embed all existing
  entities with observation-aware vectors.

### Fixed

- Dashboard test cross-file mock leakage (`a8ebabb`) — Purge all `dashboard.*`
  modules from `sys.modules` before reimport to prevent stale mock references
  when `test_dashboard.py` runs before `test_dashboard_app.py`.
- Redundant `noqa` directives in benchmarks (`51e5870`).
- Gold Stack green — format, docstrings, codespell, CVE remediation (`16e6567`).
- mypy + bandit — 6 type errors, `nosec B110`, hammer isolation (`b6df7f2`).
- `nest-asyncio` added to `pyproject.toml` — dashboard `app.py` imports it,
  CI was missing it (`efb6b16`).

### Changed

- Total test suite: 1,166 tests (1,027 unit + 139 gauntlet) across 76 files.
- MCP tools: 33 → **34** (added `diff_knowledge_state`).
- Test remediation consolidated stale tests after Hybrid Search Unification —
  unit count decreased from 1,147 to 1,027 while total coverage increased.


- **E-1: Bottle Reader with Content** (`bd2df89`) — `include_content` parameter
  in `BottleQueryParams` and `get_bottles()` to hydrate bottles with observation
  content in a single call.
- **E-2: Deep Search** (`1f3a1e5`) — `deep: bool` parameter on `search()` that
  hydrates results with associated observations and relationships.
- **E-3: Observation Vectorization** (`9f31e12`) — Automatic embedding of
  observation content upon creation; vectors upserted to Qdrant.
- **E-4: Session Reconnect** (`0588888`) — `reconnect()` method returning a
  structured briefing (recent entities, graph health, time window) for returning
  agents.
- **E-5: System Diagnostics** (`028fa3f`) — Unified `system_diagnostics()` method
  with graph health, vector store count, and split-brain detection.
- **E-6: Procedural Memory** (`ec588ab`) — `Procedure` entity type added to the
  ontology with step-based structure.
- **E-7: E2E Script Enhancement** (`907b5dc`) — `argparse` CLI (`--phase`,
  `--skip-cleanup`, `--strict`, `--verbose`), 8 new E2E phases (19–26), and
  per-phase latency threshold warnings (5s).
- `scripts/validate_brain.py` — 9-check live brain health validator (split-brain,
  bottle chain, temporal completeness, obs vectors, maxmemory, ghost graphs,
  orphan vectors, indices, HNSW threshold).
- `scripts/purge_ghost_vectors.py` (`6167ae6`) — Utility to remove orphan Qdrant
  vectors with no matching graph entity.

### Fixed

- `requirements.lock` — Bumped `tomli` 2.0.2 → 2.2.1 to resolve hard conflict
  with `pip-audit==2.10.0` (which requires `tomli>=2.2.1`).
- `requirements.lock` + `pyproject.toml` — Removed `semgrep==1.151.0` (pins
  `rich~=13.5.2`, irreconcilable with 12+ packages needing `rich>=14`). Semgrep
  was never wired into tox or CI — unused dev dependency.
- Dead dependency audit — removed 9 unused packages from lockfile: `black`
  (replaced by ruff), `crosshair-tool` (never wired), `hypothesis-graphql`,
  `hypothesis-jsonschema`, `isort` (handled by ruff), `mutmut` (not in tox),
  `safety` + `safety-schemas` (replaced by pip-audit), `schemathesis`.
  Also removed `crosshair-tool` from `pyproject.toml` dev deps.
- Removed `graphiti-core` from production deps and lockfile — zero imports in
  `src/`, was a planned integration that was never implemented.
- Created `vulture_whitelist.py` for `tox -e reaper` dead code detection tier.
- Docs cascade — corrected Gold Stack tiers (forge→reaper) across 6 docs.
- Restored comprehensive README (lost during force push) + SEO optimization.
- **P0-0** (`6167ae6`) — Re-embedded all 464 entities after vector store rebuild.
- **P0-1** (`eea3ed8`) — Surface `PRECEDED_BY` errors in `EntityCommitReceipt.warnings`.
- **P0-2** (`26d7870`) — Set FalkorDB `maxmemory 1GB` + `noeviction` via `REDIS_ARGS`.
- **P0-3** (`7b9276f`) — Wrap `search()` and `search_associative()` in error handling.
- **P0-4** (`370919b`) — Add Qdrant `UnexpectedResponse` + `RpcError` to
  `retry_on_transient`.
- **P0-5** (`3976b65`) — Remove phantom dependencies (`graphiti-core`, `neo4j`, `pandas`).
- **P0-6** (`b8c4d34`) — Ghost graph cleanup, temporal backfill, FalkorDB query fix.
- `traverse_path` shortestPath FalkorDB compatibility (`f33ab01`).
- `get_bottles` label query fix (`f33ab01`).
- Custom Louvain replaced with NetworkX + `log2` salience bug fix (`54dcaec`).
- `OntologyManager` CWD-relative path fix (`6c7e616`).
- Bare `except Exception` catches narrowed to specific types across 7 files.

### Changed

- E2E test suite expanded from 18 to 26 phases.
- Unit test suite: 1,121 tests across 77 files, 0 failures.
- Test naming convention: all unit tests now follow `test_evil{N}_`/`test_sad{N}_`/`test_happy_`
  pattern (725 functions renamed via automated script).
- Gauntlet test suite: recovered 9 files (concurrent, contracts, fuzz, golden
  queries, hypothesis, invariants, performance) from pre-force-push history.
- `scripts/internal/`: recovered 27 scripts lost during force-push.
- Source modules: recovered 4 lost files (`merge.py`, `stats.py`,
  `update_check.py`, `analysis_maintenance.py`).
- Documentation: recovered 10 docs, 1 ADR, 3 root files (LICENSE, VERSION,
  CONTRIBUTING.md, CLAUDE.md) lost during force-push.
- Lockfile bloat cleanup: removed 17 orphaned transitive dependencies
  (from removed semgrep, graphiti-core, crosshair-tool, schemathesis, black).
- Branch protection enabled on `master` (force-push + deletion blocked).
- `docs/dashboard.png`: real live screenshot (500 max nodes, 1592 nodes, 3114
  relationships) replacing AI-generated placeholder.
- Pre-commit hooks: ruff, ruff-format, codespell, detect-secrets all passing.
