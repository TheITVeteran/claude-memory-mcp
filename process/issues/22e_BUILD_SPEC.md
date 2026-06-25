# Issue #22e — Migrate 4 Remaining Service-Fixture Files to `make_mock_service()` (Build Spec)

**Issue:** parent #22 — sub-chunk 22e (final per-file migration round).
**Branch:** `issue-22e/remaining-service-fixtures` (from current master HEAD, which must contain 22a/22b/22c/22d)
**Pattern:** Topographical Forcing per `22b-22d_BUILD_SPEC.md`. Single PR, 4 files, per-file transformations.

---

## Target

Migrate the 4 remaining test files that hand-roll `MemoryService` fixtures with bug-class patterns. After 22e merges, every test file constructing a real `MemoryService` for unit testing uses `make_mock_service()`. The other 4 service-fixture files in the suite (test_router, test_list_orphans, test_locking, test_hologram) are out of scope per the architect's investigation — they use different patterns (bare MagicMock stubs, real-LockManager integration, lightweight per-test stubbing).

**Why a single PR for 4 files:** the migration pattern is well-established (4 prior successful migrations). These files are smaller and simpler than test_memory_service.py. The genuinely surprising bugs in this batch (test_entity_channel's wrong-type `spread`, test_embedding_filter's wrong-type `activate`, test_search_associative's 3× duplicate-`svc.repo` typo) deserve catching in one sweep. 4 separate audit cycles = 4× Codex overhead for the same pattern, no clear benefit.

## Files in scope

- **Modify:** `tests/unit/test_entity_channel.py`
- **Modify:** `tests/unit/test_search_associative.py`
- **Modify:** `tests/unit/test_embedding_filter.py`
- **Modify:** `tests/unit/test_channel_degradation.py`
- **New:** `process/PR_ISSUE_22E_HANDOFF.md` (after the build)

Five-file diff. Strict scope.

## Per-file transformations

Each file gets the same shape (helper import + fixture migration + topographical forcing test addition) plus file-specific cleanups.

### File 1: `tests/unit/test_entity_channel.py`

**Pre-migration fixture (lines 30-54):**

```python
@pytest.fixture
def service():
    """MemoryService with all deps mocked for entity channel testing."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING

    with patch("claude_memory.repository.FalkorDB"):
        with patch("claude_memory.lock_manager.redis.Redis"):
            with patch("claude_memory.vector_store.AsyncQdrantClient"):
                from claude_memory.tools import MemoryService
                svc = MemoryService(embedding_service=mock_embedder)

    svc.repo = AsyncMock()
    svc.activation_engine.repo = svc.repo
    svc.vector_store = AsyncMock()
    svc.router = MagicMock(spec=QueryRouter)
    svc.reranker = MagicMock()
    svc.reranker.rerank = AsyncMock(side_effect=lambda q, c, **kw: c)
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])
    svc.search_associative = AsyncMock(return_value=[])
    svc.activation_engine.activate = MagicMock(return_value={})     # correct type but bad pattern
    svc.activation_engine.spread = MagicMock(return_value={})       # ← WRONG TYPE (spread is async)
    return svc
```

**Post-migration:**

```python
@pytest.fixture
def service():
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — preserve per soft-routing path
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])
    svc.search_associative = AsyncMock(return_value=[])

    # Test-default returns on helper-built typed deps
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c
    svc.activation_engine.activate.return_value = {}    # helper-typed MagicMock
    svc.activation_engine.spread.return_value = {}      # helper-typed AsyncMock (fixes wrong-type bug)

    return svc
```

Add import at top of file:
```python
from tests._helpers.mock_factory import make_mock_service
```

### File 2: `tests/unit/test_search_associative.py`

**Pre-migration fixture (lines 41-56) — note the 3× duplicate and misleading comment:**

```python
def service() -> MemoryService:
    """MemoryService with all deps mocked."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING

    with patch("claude_memory.repository.FalkorDB"):
        with patch("claude_memory.lock_manager.redis.Redis"):
            with patch("claude_memory.vector_store.AsyncQdrantClient"):
                svc = MemoryService(embedding_service=mock_embedder)

    svc.repo = AsyncMock()
    svc.repo = AsyncMock()      # ← duplicate (typo)
    svc.repo = AsyncMock()      # ← duplicate (typo, third copy)
    svc.activation_engine.repo = svc.repo  # sync so spread() uses same mock   ← MISLEADING (spread is async)
    svc.vector_store = AsyncMock()
    return svc
```

**Post-migration:**

```python
def service() -> MemoryService:
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)
    # Helper handles activation_engine.repo wiring internally — no manual relink needed
    return svc
```

The 3 duplicate-`svc.repo` lines and the misleading "sync" comment all disappear naturally. Add helper import at top of file.

### File 3: `tests/unit/test_embedding_filter.py`

**Two migration sites:** the fixture AND an inline ad-hoc construction inside `test_sad1_create_entity_receipt_missing_embedding_key_evil` (lines 80-98).

**Pre-migration fixture (lines 21-40):**

```python
@pytest.fixture
def mock_service():
    """Build a MemoryService with all deps mocked."""
    mock_embedder = MagicMock()
    mock_vector = AsyncMock()

    with patch("claude_memory.tools.MemoryRepository"):
        service = MemoryService(embedding_service=mock_embedder, vector_store=mock_vector)
    service.repo = AsyncMock()
    service.fts_store = MagicMock()
    service.fts_store.search = MagicMock(return_value=[])
    service.reranker = MagicMock()
    service.reranker.rerank = AsyncMock(side_effect=lambda q, c, **kw: c)
    service.query_timeline = AsyncMock(return_value=[])
    service.traverse_path = AsyncMock(return_value=[])
    service.activation_engine = MagicMock()                         # ← loses helper introspection
    service.activation_engine.activate = AsyncMock(return_value={}) # ← WRONG TYPE (activate is sync)
    service.activation_engine.spread = AsyncMock(return_value={})
    return service
```

**Post-migration fixture:**

```python
@pytest.fixture
def mock_service():
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    mock_embedder = MagicMock()
    service = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — preserve
    service.query_timeline = AsyncMock(return_value=[])
    service.traverse_path = AsyncMock(return_value=[])

    # Test-default returns on helper-built typed deps
    service.fts_store.search.return_value = []
    service.reranker.rerank.side_effect = lambda q, c, **kw: c
    service.activation_engine.activate.return_value = {}    # helper-typed MagicMock (fixes wrong-type bug)
    service.activation_engine.spread.return_value = {}      # helper-typed AsyncMock
    return service
```

The pre-migration fixture passes `vector_store=mock_vector` directly to `MemoryService(...)`. The helper builds its own vector_store via introspection (typed AsyncMock). Tests in this file don't pre-configure mock_vector with specific behavior, so dropping the explicit pass and using the helper-built vector_store is behaviorally equivalent. If any test fails post-migration because it expected specific vector_store state, escalate.

**Inline ad-hoc construction at lines 80-98 (`test_sad1_create_entity_receipt_missing_embedding_key_evil`):**

```python
# Pre-migration:
async def test_sad1_create_entity_receipt_missing_embedding_key_evil():
    """Evil: what if repo returns NO embedding key? Should still work."""
    mock_embedder = MagicMock()
    mock_vector = AsyncMock()
    from unittest.mock import patch

    with patch("claude_memory.tools.MemoryRepository"):
        service = MemoryService(embedding_service=mock_embedder, vector_store=mock_vector)
    service.repo = AsyncMock()
    # ... rest of test
```

**Post-migration:**

```python
async def test_sad1_create_entity_receipt_missing_embedding_key_evil():
    """Evil: what if repo returns NO embedding key? Should still work."""
    service = make_mock_service()
    # ... rest of test (no other changes — service.repo is already helper-built AsyncMock)
```

The default `make_mock_service()` with no kwargs uses a default mock_embedder. If the test needs specific embedder behavior, pass it: `make_mock_service(embedding_service=mock_embedder)`. Scan the test body to determine which.

### File 4: `tests/unit/test_channel_degradation.py` — UNIQUE CONSTRAINT

**Pre-migration fixture (lines 26-48):**

```python
def service() -> MemoryService:
    """Creates a MemoryService with all dependencies mocked."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [0.1, 0.2, 0.3]

    with patch("claude_memory.repository.FalkorDB"):
        with patch("claude_memory.lock_manager.redis.Redis"):
            with patch("claude_memory.vector_store.AsyncQdrantClient"):
                svc = MemoryService(embedding_service=mock_embedder)

    svc.repo = AsyncMock()
    svc.vector_store = AsyncMock()
    svc.lock_manager = MagicMock()

    # Lock context manager — async API (__aenter__ / __aexit__)
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
    mock_lock.__aexit__ = AsyncMock(return_value=False)
    svc.lock_manager.lock.return_value = mock_lock

    svc.repo.get_observations_for_entity.return_value = []
    return svc
```

**Critical:** this file uses `async with` on the lock context manager (different from 22b/22c/22d's sync `with`). The mock_lock pattern is:
- Outer = `MagicMock` (constructor is sync)
- `__aenter__` = `AsyncMock(return_value=mock_lock)` (async)
- `__aexit__` = `AsyncMock(return_value=False)` (async)

**Post-migration — PRESERVE the async lock pattern:**

```python
def service() -> MemoryService:
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22e_BUILD_SPEC.md. Unique to this file: lock_manager.lock()
    is used via `async with`, so the context manager mock uses __aenter__/__aexit__
    (not __enter__/__exit__ like 22b/22c/22d).
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [0.1, 0.2, 0.3]
    svc = make_mock_service(embedding_service=mock_embedder)

    # Async lock context manager — PRESERVE the __aenter__/__aexit__ pattern
    # specific to this file's tests (they use `async with svc.lock_manager.lock(...)`)
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
    mock_lock.__aexit__ = AsyncMock(return_value=False)
    svc.lock_manager.lock.return_value = mock_lock

    # Test-default returns on helper-built typed deps
    svc.repo.get_observations_for_entity.return_value = []
    return svc
```

Do NOT replace the lock setup with the sync `__enter__`/`__exit__` pattern from 22b/22c/22d — that would break this file's tests.

## Per-file topographical forcing test addition

Each of the 4 files currently has NO topographical forcing test (only the migrated 22b/22c/22d files have one). Add a minimal forcing test to EACH file post-migration to prevent regression and document helper-correctness expectations.

**Standard forcing test (paste into each file post-fixture):**

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Added 22e to extend forcing-test coverage to all migrated files.
    DO NOT remove or weaken — guard against migrations that bypass
    make_mock_service() and reintroduce the hand-rolled bug class.

    Per process/issues/22e_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is `async def` — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, MagicMock), (
        "ActivationEngine.activate is sync `def` — must be MagicMock"
    )
    assert not isinstance(service.activation_engine.activate, AsyncMock), (
        "Guard against bare AsyncMock — production does NOT await activate"
    )
```

**Adaptations per file:**
- **test_search_associative.py:** the fixture name is `service` (not `mock_service`). Standard test works as-is.
- **test_embedding_filter.py:** the fixture name is `mock_service`. Rename the test param: `def test_meta_fixture_topology_required(mock_service) -> None:` and substitute `service` → `mock_service` throughout the body.
- **test_entity_channel.py:** fixture is `service`. Standard test works as-is.
- **test_channel_degradation.py:** fixture is `service`. Standard test works as-is. ALSO add an extra assertion specific to the async lock pattern:
  ```python
  assert hasattr(service.lock_manager.lock.return_value, '__aenter__'), (
      "lock_manager.lock() must return an async context manager (this file uses `async with`)"
  )
  ```

## Async-method-replacement scan (per file)

Per Transformation 7 discipline from 22d. For each of the 4 files, scan for any `service.<dep>.<method> = AsyncMock(...)` or `MagicMock(...)` patterns that REPLACE helper-built children. Document the scan in handoff "Discoveries" section per file:

```bash
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_entity_channel.py
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_search_associative.py
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_embedding_filter.py
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_channel_degradation.py
```

For each match: configure-on-existing-mock or escalate. Document per-file findings.

## Verification (multi-seed gate per file)

### Pre-PR baseline capture (Method B with explanatory note is acceptable here)

These files have NO `_drain_orphan_coroutines` suppression fixture, so running master-as-is should produce CLEAN output on most/all files (the bug class doesn't currently emit warnings because the test code paths happen to not exercise the wrong-type mocks in awaited contexts). Method B with note is the recommended approach:

```bash
# In a clean worktree at master
git worktree add ../22e-pre-pr master
cd ../22e-pre-pr
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
cd - && git worktree remove --force ../22e-pre-pr
```

Paste all outputs verbatim in handoff. Add explanatory note: "Pre-PR baseline shows mostly clean output across files — these files lack the `_drain_orphan_coroutines` suppression but their hand-rolled fixtures have wrong-type mocks (test_entity_channel.spread, test_embedding_filter.activate) that don't currently emit warnings because the test code paths don't exercise the bug class in awaited contexts. The migration replaces wrong-type mocks with helper-introspected correct types AND adds forcing tests that would fail-loud on any regression — defense in depth."

### Post-PR multi-seed gate per file

```bash
git worktree add ../22e-post-pr issue-22e/remaining-service-fixtures
cd ../22e-post-pr
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
```

**Required:** ALL 4 files × 4 seeds = 16 runs return zero RuntimeWarnings and all tests pass.

### Standard gates — SAME clean worktree

```bash
# Still in ../22e-post-pr
python -m pytest tests/unit/test_entity_channel.py tests/unit/test_search_associative.py tests/unit/test_embedding_filter.py tests/unit/test_channel_degradation.py -v --tb=short
python -m pytest tests/_helpers/test_mock_factory.py -v
tox -e contracts
python -m mypy --strict src/claude_memory
python -m ruff check src/claude_memory tests scripts          # CANONICAL — no --exclude
python -m bandit -r src/claude_memory -ll
cd - && git worktree remove ../22e-post-pr
```

## The bar (Codex will verify)

- (a) All 4 files import `make_mock_service` from `tests._helpers.mock_factory`
- (b) All 4 fixtures use `make_mock_service(...)`; no hand-rolled `svc.repo = AsyncMock()`, `svc.vector_store = AsyncMock()`, `svc.fts_store = MagicMock()` (where applicable), `svc.lock_manager = MagicMock()` (where applicable), `svc.reranker = MagicMock()` (where applicable), `svc.activation_engine = MagicMock()` (where applicable) survive in any fixture
- (c) test_search_associative.py: 3 duplicate `svc.repo = AsyncMock()` lines AND the misleading "sync so spread()" comment are GONE
- (d) test_entity_channel.py: `svc.activation_engine.spread = MagicMock(...)` (wrong type) is GONE — verify with grep: `grep -n "activation_engine.spread = MagicMock" tests/unit/test_entity_channel.py` must be empty
- (e) test_embedding_filter.py: `service.activation_engine.activate = AsyncMock(` (wrong type) is GONE; the inline ad-hoc `MemoryService(...)` construction in `test_sad1_create_entity_receipt_missing_embedding_key_evil` is replaced with `make_mock_service()`
- (f) test_channel_degradation.py: the async lock context manager pattern (`__aenter__`/`__aexit__`) is PRESERVED — verify the post-migration fixture still has both attributes set
- (g) All 4 files have a `test_meta_fixture_topology_required` test asserting helper-correct topology; test_channel_degradation.py's variant additionally asserts the async lock context manager pattern
- (h) **Multi-seed gate (4 seeds × 4 files = 16 runs) returns ZERO RuntimeWarnings** — load-bearing
- (i) All tests in all 4 files pass; test count preserved per file against master baseline
- (j) `tox -e contracts`, mypy, CANONICAL ruff (no `--exclude`), bandit all unchanged from master baseline
- (k) Scope discipline: only `process/PR_ISSUE_22E_HANDOFF.md` + the 4 migrated test files in the diff
- (l) Pre-handoff checklist complete (9 items) with real evidence from a clean worktree; **pre-PR baseline shows all 4 seed outputs per file (16 total)**; ruff command is canonical full-scope

## Out of scope (do NOT do in this PR)

- Do NOT modify `tests/_helpers/mock_factory.py`
- Do NOT migrate test_router.py, test_list_orphans.py, test_locking.py, test_hologram.py — they use different patterns (architect-verified, see investigation in conversation log)
- Do NOT touch already-migrated files (test_hybrid_search.py, test_tools_coverage.py, test_memory_service.py)
- Do NOT add scanner Pattern 12 (that's 22f)
- Do NOT modify `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`, or any `src/claude_memory` file
- Do NOT modify any `process/*_SPEC.md` or `process/issues/22*_HARNESS.toml`

Write-guard via `process/issues/22_HARNESS.toml` enforces these physically.

## Round 5 discipline

Same as 22b-22d. If multi-seed gate fails on any file, attribution-diagnose with `pytest --forked`. Fix underlying mock-type bug; do NOT add suppression. If spec-mock attribute access fails after a deletion, the test was calling a non-existent method — escalate.

**Specific to this PR:** if test_embedding_filter.py's inline ad-hoc test fails after migration, the test might rely on specific `mock_vector` pre-configuration that I missed in the architect inventory. Escalate with specifics — do not silently re-add hand-rolled construction.

If test_channel_degradation.py's async lock context manager pattern doesn't work after migration, the helper's introspection of LockManager might be misclassifying it. Escalate — do NOT switch to sync `__enter__`/`__exit__` to "make it work" (that would break the test semantics).

## Hygiene (hardened per 22a/22b/22c/22d/22d round-1 lessons)

**Run ALL evidence commands in a SINGLE fresh worktree.** Five PRs in a row had checklist hygiene drift; the structural fix in 22f will be a pre-commit hook. For 22e, the discipline is manual: single worktree, every command, canonical ruff, all 16 seed outputs in handoff.

Push with `--force-with-lease` not `--force`.
