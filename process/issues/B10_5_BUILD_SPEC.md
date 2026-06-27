# B10.5 — Native Async Migration (Build Spec)

**Epic:** B10.5 (deferred from original Audit Remediation Round 1, May 2026)
**Branch:** `b10-5/native-async-migration` (from current master HEAD post-22-arc)
**Pattern:** Single-PR Pattern A — replace `asyncio.to_thread` wrapper with direct `falkordb.asyncio.FalkorDB` usage. Public API of `AsyncMemoryRepository` unchanged → mixin code doesn't change.

---

## Target

Migrate `AsyncMemoryRepository` from "thin wrapper over sync `MemoryRepository` via `asyncio.to_thread`" to "native async repository using `falkordb.asyncio.FalkorDB` directly." Preserves sync `MemoryRepository` as a diagnostic/CLI fallback (Director call — x-ray vision).

**Why now:** Issue #22 arc closed 2026-06-26 (bug class structurally eliminated, 5-layer enforcement live, trifecta calibrated and warm). B10.5 sitting in deferred-items every shutdown is mental tax that closing eliminates. Wrapper indirection has real costs (deeper stack traces, harder async debugging) even with zero performance change.

## Pre-Flight (Architect-Verified Pre-Spec)

- **`falkordb.asyncio.FalkorDB` is importable** from the current install (verified 2026-06-27 via `from falkordb.asyncio import FalkorDB`)
- **`pyproject.toml` allows v1.4+** via `falkordb>=1.0.0,<2.0.0` (we tighten to `>=1.4.0` in this PR to make the dependency explicit)
- **Migration surface is concentrated:** 26 `asyncio.to_thread` calls all in `src/claude_memory/repository_async.py` (single file)
- **One production construction site:** `src/claude_memory/tools.py:82` — `self.repo = AsyncMemoryRepository(MemoryRepository(host, port, password))`
- **Test coverage available:** `tests/integration/test_db_kill_scenarios.py` (6 tests, real testcontainers gated behind `RUN_INTEGRATION=1`) — the load-bearing behavioral safety net

## Files in scope

- **NEW:** `src/claude_memory/cypher_queries.py` — extracted Cypher strings as module constants (eliminates query divergence risk between sync + async paths)
- **REWRITE:** `src/claude_memory/repository_async.py` — from wrapper pattern to native async implementation
- **MINIMAL TOUCH:** `src/claude_memory/repository.py` — switch to use extracted Cypher constants (no behavior change)
- **MINIMAL TOUCH:** `src/claude_memory/repository_queries.py` — same (use extracted constants)
- **MINIMAL TOUCH:** `src/claude_memory/repository_traversal.py` — same (use extracted constants)
- **UPDATE:** `src/claude_memory/tools.py` line 82 — construction simplifies to `AsyncMemoryRepository(host, port, password)`
- **REWRITE:** `tests/unit/test_repository_async.py` — from delegation tests to behavioral tests
- **UPDATE:** `pyproject.toml` — `falkordb>=1.4.0,<2.0.0` AND `redis>=7.1.0,<8.0.0` (falkordb v1.4.0 dependency cascade)
- **NEW:** `process/PR_B10_5_HANDOFF.md`

### Test infrastructure scope (ADDED 2026-06-27 after B10.5 R2 audit)

Original 9-file scope was incomplete — missed the test-infrastructure dependency on the changed production construction path. Per oracle correction discipline (substance test passes: AG was NOT semantically required to update test infra under original spec; the migration's "no test regression" intent REQUIRES test infrastructure to track production path changes):

- **UPDATE:** `tests/_helpers/mock_factory.py` — add `patch("claude_memory.repository_async.FalkorDB")` to the patch tuple in `make_mock_service`. The 22-arc helper patches `claude_memory.repository.FalkorDB` (sync) which the new construction path no longer uses. Without the additional patch, helper-built services hit the real async FalkorDB constructor and tests fail with "MagicMock can't be used in 'await' expression."

- **UPDATE:** `tests/unit/test_mutant_dict_crud.py`, `tests/unit/test_mutant_dict_services.py`, `tests/unit/test_mutant_temporal.py` — update each file's `_build()` factory (or equivalent constructor patch tuple) to patch the new async construction path. Replace `patch("claude_memory.tools.MemoryRepository", return_value=r)` with `patch("claude_memory.repository_async.FalkorDB")` (or analogous — the patches must intercept the actual production construction).

  Critical: these are Category D files (intentional patterns); the modification preserves the mutant-testing factory pattern but updates the patch target to match the new production path. The architectural intent is unchanged.

### Scope summary

**13 files total** (9 original + 4 test-infrastructure additions). Stretched beyond initial scope to satisfy "no test regression" — flag this in handoff Discoveries with the cite to B10.5 R2 audit (oracle correction). Production code change. Higher reversibility cost than #22 — handle accordingly.

## Concrete Transformations

### Transformation 1: Extract Cypher to `cypher_queries.py`

Survey `repository.py`, `repository_queries.py`, `repository_traversal.py` for inline Cypher strings. Move each to a module-level constant in a new file `src/claude_memory/cypher_queries.py`:

```python
"""Canonical Cypher query templates shared by sync and async repository impls.

Per process/issues/B10_5_BUILD_SPEC.md — extracted here so sync MemoryRepository
(diagnostics) and async AsyncMemoryRepository (production) cannot drift apart.
Any new query MUST be added here, not inlined in either implementation.
"""

# ─── Node operations ─────────────────────────────────────────────────
CREATE_NODE = """MERGE (n:{label}:Entity {{id: $id}})
SET n += $properties
RETURN n
"""

GET_NODE_BY_ID = """MATCH (n:Entity {id: $id})
RETURN n
"""

# ... (one constant per query found in the survey)
```

Then update `repository.py` and friends to reference the constants:

```python
# Before:
result = self.graph.query("MERGE (n:Entity {id: $id}) ...", {"id": node_id, ...})

# After:
result = self.graph.query(CREATE_NODE.format(label=label), {"id": node_id, ...})
```

**Why first:** establishes the canonical query layer that both sync and native-async impls will reference. Eliminates the divergence risk.

### Transformation 2: Rewrite `repository_async.py`

The current file is a 200-line wrapper. The new file is a native async implementation. Same class name (`AsyncMemoryRepository`), same public method signatures → mixin code doesn't change.

Shape:

```python
"""Native async repository using falkordb.asyncio.FalkorDB.

Replaces the asyncio.to_thread wrapper pattern (B10 Phase 1) with direct
native async (B10.5). Uses falkordb.asyncio.FalkorDB backed by
redis.asyncio.Redis for non-blocking I/O.

Per process/issues/B10_5_BUILD_SPEC.md — closes the B10.5 epic deferred from
the original Audit Remediation Round 1 (May 2026).

Sync MemoryRepository (in repository.py) is preserved for diagnostics + CLI
ops scripts — x-ray vision into the same query layer via cypher_queries.py.
"""

import asyncio
from typing import Any

from falkordb.asyncio import FalkorDB

from claude_memory.cypher_queries import (
    CREATE_NODE, GET_NODE_BY_ID, # ... etc
)


class AsyncMemoryRepository:
    """Native async repository over FalkorDB.

    Same public API as the prior wrapper (B10.A) — drop-in replacement for
    mixin code calling `await self.repo.X(...)`.
    """

    def __init__(self, host: str, port: int, password: str | None = None) -> None:
        """Connect to FalkorDB via native async client."""
        self._client = FalkorDB(host=host, port=port, password=password)
        self._graph_name = "claude_memory"
        self._connect_retries = 5
        self._connect_backoff = 0.5  # seconds

    @property
    async def graph(self) -> Any:
        """Return the active FalkorDB graph handle (async)."""
        # ... native async equivalent of select_graph

    async def _connect_with_retry(self) -> None:
        """Async equivalent of repository.py's sync retry logic.

        Required: same retry semantics (5 attempts, exponential backoff)
        but using async sleep + async client probe.
        """
        # ... implementation

    # ── Mirror every public method from prior wrapper ────────────────
    # Same signatures, same return types, same exception contract.
    # Implementations use `await self._graph.query(CYPHER_CONSTANT, params)`
    # instead of `await asyncio.to_thread(self._sync_repo.X, ...)`.

    async def create_node(self, label: str, properties: dict[str, Any]) -> dict[str, Any]:
        graph = await self.graph
        result = await graph.query(CREATE_NODE.format(label=label), properties)
        # ... convert result to dict per existing contract

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        graph = await self.graph
        result = await graph.query(GET_NODE_BY_ID, {"id": node_id})
        # ... etc

    # ... (one method per item in the existing wrapper — full inventory below)
```

**Required public method coverage (26 methods, from the existing wrapper inventory):**

Core (from `repository.py`):
- `select_graph`, `ensure_indices`, `create_node`, `get_node`, `update_node`, `delete_node`, `create_edge`, `delete_edge`, `execute_cypher`

Query mixin (from `repository_queries.py`):
- `query_timeline`, `get_temporal_neighbors`, `create_temporal_edge`, `get_bottles`, `get_graph_health`, `list_orphans`, `get_all_edges`, `get_all_node_ids`, `get_observations_for_entity`

Traversal mixin (from `repository_traversal.py`):
- `get_subgraph`, `get_all_nodes`, `get_total_node_count`, `increment_salience`, `get_most_recent_entity`, `shortest_path_length`

Plus the `client` property/setter for testing/diagnostics (preserved for API compat).

### Transformation 3: Preserve `MemoryRepository` (sync) as diagnostic

`src/claude_memory/repository.py` stays. Its class still exists. It still inherits from the mixins. It still uses sync FalkorDB client. **Only change:** use extracted Cypher constants from `cypher_queries.py` instead of inline strings (Transformation 1 already covers this).

Add a docstring note at the top of `repository.py` explaining its post-B10.5 role:

```python
"""FalkorDB sync data access layer — Cypher queries, CRUD, index management.

Post-B10.5 role: PRESERVED for diagnostics + CLI ops scripts (e.g.
scripts/heal_graph.py, scripts/recover_graph.py). Production async path
goes through AsyncMemoryRepository (native async) in repository_async.py.
Both share canonical Cypher templates via cypher_queries.py.
"""
```

### Transformation 4: Update construction in `tools.py:82`

Before:
```python
self.repo = AsyncMemoryRepository(MemoryRepository(host, port, password))
```

After:
```python
self.repo = AsyncMemoryRepository(host, port, password)
```

The new constructor signature takes connection params directly (no more wrapping a sync repo).

### Transformation 5: Rewrite `tests/unit/test_repository_async.py`

The existing file has 26 parameterized delegation tests verifying `asyncio.to_thread` is called with the right sync delegate. Post-migration there IS no delegation — the tests need to change shape.

New test shape: behavioral tests with mocked `falkordb.asyncio.FalkorDB`:

```python
"""Tests for AsyncMemoryRepository (B10.5 native async).

Verifies:
- Each async method dispatches to the native async client correctly
- Cypher queries match the canonical templates in cypher_queries.py
- Arguments forwarded with correct parameter binding
- Return values parsed correctly from FalkorDB result format
- Exceptions propagate transparently (SearchError contract preserved)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from claude_memory.repository_async import AsyncMemoryRepository
from claude_memory.cypher_queries import CREATE_NODE, GET_NODE_BY_ID  # etc


@pytest.fixture
def mock_falkordb():
    """Mock falkordb.asyncio.FalkorDB with async graph + query methods."""
    mock_graph = MagicMock()
    mock_graph.query = AsyncMock()
    mock_client = MagicMock()
    mock_client.select_graph = AsyncMock(return_value=mock_graph)
    return mock_client, mock_graph


@pytest.fixture
def repo(mock_falkordb):
    """AsyncMemoryRepository with mocked native async client."""
    mock_client, _ = mock_falkordb
    with patch("claude_memory.repository_async.FalkorDB", return_value=mock_client):
        repo = AsyncMemoryRepository("localhost", 6379, None)
    return repo


# ─── Behavioral tests per public method ───────────────────────────────


async def test_create_node_uses_canonical_cypher(repo, mock_falkordb):
    """create_node dispatches the CREATE_NODE cypher template with bound params."""
    _, mock_graph = mock_falkordb
    mock_graph.query.return_value = MagicMock(result_set=[[{"id": "n1"}]])

    result = await repo.create_node("Entity", {"id": "n1", "name": "Test"})

    mock_graph.query.assert_awaited_once()
    cypher_used = mock_graph.query.call_args[0][0]
    # Verify the canonical template was used (with label interpolation)
    assert "MERGE (n:Entity:Entity" in cypher_used or "MERGE (n:Entity" in cypher_used


# ... (one behavioral test per public method — 26 tests minimum)

# ─── Contract preservation tests ──────────────────────────────────────


async def test_search_error_propagates_on_falkordb_failure(repo, mock_falkordb):
    """When falkordb.asyncio raises, SearchError contract is preserved."""
    _, mock_graph = mock_falkordb
    mock_graph.query.side_effect = ConnectionError("falkordb down")

    from claude_memory.exceptions import SearchError
    with pytest.raises(SearchError):
        await repo.get_node("n1")
```

Per-method count: ≥26 behavioral tests (one per public method), plus contract preservation tests for SearchError, plus retry-logic tests (verify `_connect_with_retry` async equivalent works).

### Transformation 6: `pyproject.toml` dependency tightening

```toml
# Before:
"falkordb>=1.0.0,<2.0.0",

# After:
"falkordb>=1.4.0,<2.0.0",
```

Makes the native-async requirement explicit.

## Verification

### Pre-PR baseline (Method A — capture sync wrapper behavior)

Before migrating, run the integration test suite on master to capture baseline behavior:

```bash
git worktree add ../b10-5-pre-pr master
cd ../b10-5-pre-pr
RUN_INTEGRATION=1 python -m pytest tests/integration/test_db_kill_scenarios.py -v --tb=short 2>&1 | tee /tmp/b10-5-pre-pr-integration.log
cd - && git worktree remove --force ../b10-5-pre-pr
```

Paste all 6 test outputs verbatim in handoff under "Pre-PR baseline." Expected: all 6 pass (this is master, the wrapper works).

### Post-PR — load-bearing gate

In a clean worktree on the migration branch:

```bash
git worktree add ../b10-5-post-pr b10-5/native-async-migration
cd ../b10-5-post-pr

# (1) LOAD-BEARING: integration tests must pass on native async
RUN_INTEGRATION=1 python -m pytest tests/integration/test_db_kill_scenarios.py -v --tb=short
# Expected: all 6 pass. Any fail = STOP, native async has a behavioral regression.

# (2) New behavioral tests pass
python -m pytest tests/unit/test_repository_async.py -v --tb=short
# Expected: ≥26 tests pass

# (3) Helper still works
python -m pytest tests/_helpers/test_mock_factory.py -v
# Expected: 8 pass

# (4) Standard gates
tox -e contracts                                           # baseline 13 holds
python -m mypy --strict src/claude_memory                  # clean
python -m ruff check src/claude_memory tests scripts       # canonical
python -m bandit -r src/claude_memory -ll                  # only B104

cd - && git worktree remove ../b10-5-post-pr
```

## The bar (Codex will verify)

- (a) `src/claude_memory/cypher_queries.py` exists with extracted Cypher constants; survey of `repository.py`/`repository_queries.py`/`repository_traversal.py` shows no inline Cypher strings remain (all use constants from `cypher_queries`)
- (b) `src/claude_memory/repository_async.py` uses `falkordb.asyncio.FalkorDB`; grep for `asyncio.to_thread` returns **empty** in this file (all 26 wrapper sites eliminated)
- (c) `src/claude_memory/repository.py` (sync `MemoryRepository`) preserved + importable; docstring updated to explain diagnostic role
- (d) `src/claude_memory/tools.py:82` construction simplified (no longer wraps sync repo)
- (e) `tests/unit/test_repository_async.py` rewritten — no test function names matching `test_*_delegates_via_to_thread` survive; new behavioral tests use mocked `falkordb.asyncio.FalkorDB`
- (f) `tests/integration/test_db_kill_scenarios.py` with `RUN_INTEGRATION=1` → all 6 pass on native async **(load-bearing)**
- (g) Unit test count + new helper tests pass; no regression in adjacent test files (the 22-arc-migrated test files still pass under `-W error`)
- (h) `tox -e contracts` baseline 13 unchanged; mypy strict clean; ruff canonical clean (no `--exclude`); bandit only B104
- (i) `pyproject.toml` updated to `falkordb>=1.4.0,<2.0.0`
- (j) Scope discipline: 9 files in diff, no surprise files (especially no `tests/_helpers/*`, no `process/*_SPEC.md` except the new B10_5 handoff)
- (k) Pre-handoff checklist complete (9 items) — `verify_handoff_completeness.py` pre-commit hook will auto-enforce 4-seed evidence + canonical ruff + no `N/A`. Pre-PR baseline + post-PR result both pasted.

## Out of scope (do NOT do in this PR)

- Do NOT delete sync `MemoryRepository` — preserved per Director call (diagnostic / x-ray vision)
- Do NOT migrate mixin files (`crud.py`, `search.py`, etc.) to call native async client directly — they keep calling `await self.repo.X(...)` which now resolves to native async via the new wrapper-free implementation
- Do NOT add new audit dimensions to `trace_contracts_dragon.py` — that's a separate epic
- Do NOT modify any `tests/_helpers/*`
- Do NOT modify `process/*_SPEC.md` except creating the new handoff
- Do NOT touch the 5-layer enforcement infrastructure (`scripts/hooks/*`, `.pre-commit-config.yaml`)

## Round 5 discipline

If `falkordb.asyncio.FalkorDB` API has subtle semantic differences from sync (transaction handling, error types, connection cleanup), escalate to architect for spec refinement BEFORE inventing workarounds. The integration tests are the safety net — if they reveal divergence, that's signal worth surfacing.

If retry logic + connection pool semantics need restructuring beyond what the spec anticipates, escalate. The spec assumes a 1:1 mapping; real-world async may need different patterns (e.g., separate connection pools, async context managers for transactions).

If `tests/integration/test_db_kill_scenarios.py` fails on any of the 6 tests post-migration, that's the load-bearing signal — STOP, diagnose with `pytest --forked` if needed, fix the actual behavioral bug. Do NOT add suppressions or skip tests to make the gate pass.

## Hygiene

Run ALL evidence commands in a single fresh worktree (same pattern as 22 arc — `verify_handoff_completeness.py` now auto-enforces this at commit time). Push with `--force-with-lease`.
