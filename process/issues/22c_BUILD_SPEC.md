# Issue #22c — Migrate `test_tools_coverage.py` to `make_mock_service()` (Build Spec)

**Issue:** parent #22 — sub-chunk 22c (second per-file migration).
**Branch:** `issue-22c/test-tools-coverage-migration` (from current master HEAD, which must contain 22a's helper AND 22b's hybrid-search migration)
**Pattern:** identical Topographical Forcing pattern as `22b_BUILD_SPEC.md`. Mechanical replication on a bigger file.

---

## Target

Migrate `tests/unit/test_tools_coverage.py` to use `make_mock_service()` exclusively for `MemoryService` construction. Same surgical pattern as 22b: delete the autouse `_drain_orphan_coroutines` suppression sneak-around, replace the hand-rolled `service` fixture body with the helper call, update the topographical-forcing test to assert helper-correct topology, fix mid-test mock surgery that replaces helper-built mocks with bare MagicMocks.

**Why this file is next:** test_tools_coverage.py has the largest dep surface area of any test file in the suite (lock_manager with context-manager semantics, ontology, context_manager, activation_engine, plus all the standard async deps). If the helper pattern holds here, it holds everywhere. 28+ tests in this file currently rely on the buggy hand-rolled fixture.

**Scope:** this single file + its handoff doc. NO changes to the helper, no changes to other test files.

## Files in scope

- **Modify:** `tests/unit/test_tools_coverage.py` (the migration)
- **New:** `process/PR_ISSUE_22C_HANDOFF.md` (after the build)

That's it. Two-file diff.

## Concrete fix (architect-prescribed transformations)

### Transformation 1: DELETE the autouse suppression fixture

**Lines 93-111 (current):**

```python
@pytest.fixture(autouse=True)
def _drain_orphan_coroutines() -> None:
    """Force GC after each test to drain orphan coroutines within test boundaries.

    Without this, unawaited coroutines created by AsyncMock's internal
    _execute_mock_call are reaped by Python's cyclic GC at session end,
    producing PytestUnraisableExceptionWarning. Forcing gc.collect() inside
    a catch_warnings context drains them silently within each test's scope.

    Per-file fixture (not in conftest.py) because the branch write guard
    blocks conftest changes on issue-14a branches.
    """
    import gc
    import warnings

    yield
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        gc.collect()
```

**Post-migration:** **DELETED ENTIRELY.** Same reasoning as 22b. If the post-migration multi-seed gate fails, do NOT re-add this fixture — the failure is signal that a mock-type bug survives. Use `pytest --forked` for attribution.

### Transformation 2: REPLACE the `service` fixture body

**Lines 114-161 (current):**

```python
@pytest.fixture()
def service() -> MemoryService:
    """Creates a MemoryService with all dependencies mocked."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING

    with patch("claude_memory.repository.FalkorDB"):
        with patch("claude_memory.lock_manager.redis.Redis"):
            with patch("claude_memory.vector_store.AsyncQdrantClient"):
                svc = MemoryService(embedding_service=mock_embedder)

    # Replace repo, vector_store, lock_manager with mocks
    svc.repo = AsyncMock()
    svc.repo.get_subgraph.return_value = {"nodes": [], "edges": []}
    svc.vector_store = AsyncMock()
    svc.fts_store = MagicMock()
    svc.fts_store.search = MagicMock(return_value=[])
    svc.lock_manager = MagicMock()

    # Soft routing defaults
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])

    # Reranker pass-through
    svc.reranker = MagicMock()
    svc.reranker.rerank = AsyncMock(side_effect=lambda q, c, **kw: c)

    # Activation engine defaults
    svc.activation_engine = MagicMock()              # ← replaces helper-built type-correct mock
    svc.activation_engine.activate = AsyncMock(return_value={})   # ← WRONG TYPE (activate is sync)
    svc.activation_engine.spread = AsyncMock(return_value={})

    # Lock context manager mock — AsyncMock prevents phantom async children
    # from MagicMock parent's internal _mock_children cleanup (GC-time warnings).
    mock_lock = AsyncMock()
    mock_lock.__enter__ = MagicMock(return_value=mock_lock)
    mock_lock.__exit__ = MagicMock(return_value=False)
    svc.lock_manager.lock.return_value = mock_lock

    # Prevent _fire_salience_update from creating orphan asyncio.create_task()
    # coroutines. The real method calls asyncio.create_task(repo.increment_salience(...))
    # which, with an AsyncMock repo, produces unawaited coroutines at GC time.
    svc._fire_salience_update = MagicMock()

    # Default async_repo returns for _compute_entity_embedding_text
    svc.repo.get_observations_for_entity.return_value = []

    return svc
```

**Post-migration:**

```python
@pytest.fixture()
def service() -> MemoryService:
    """Creates a MemoryService with all dependencies mocked type-correctly via mock_factory.

    Per process/issues/22c_BUILD_SPEC.md — uses make_mock_service() to eliminate
    hand-rolled MagicMock-vs-AsyncMock decisions. Helper introspects each
    dependency class to AsyncMock async methods and MagicMock sync methods
    automatically.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — helper does not mock methods on
    # the service itself, only deps. Preserve these per the soft-routing path.
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])

    # Prevent _fire_salience_update from creating orphan asyncio.create_task()
    # coroutines. The real method calls asyncio.create_task(repo.increment_salience(...))
    # which, with an AsyncMock repo, produces unawaited coroutines at GC time.
    # This is a MemoryService instance method, not a dep — helper does not mock it.
    svc._fire_salience_update = MagicMock()

    # Test-default returns/side_effects on helper-built typed deps
    svc.repo.get_subgraph.return_value = {"nodes": [], "edges": []}
    svc.repo.get_observations_for_entity.return_value = []
    svc.fts_store.search.return_value = []
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c

    # Per-test default return values on activation_engine. Per 22b's
    # AG-reported discovery (AsyncMock chain semantics): without explicit
    # return values, awaited results are bare AsyncMocks whose attribute access
    # (e.g. spread_map.keys()) returns coroutines → TypeError + RuntimeWarning.
    svc.activation_engine.activate.return_value = {}   # helper-typed MagicMock (sync)
    svc.activation_engine.spread.return_value = {}     # helper-typed AsyncMock (async)

    # Lock context manager mock — lock_manager.lock() returns a context manager
    # used with `with`. Helper builds lock_manager via inspect; configure .lock
    # to return the context manager mock.
    mock_lock = AsyncMock()
    mock_lock.__enter__ = MagicMock(return_value=mock_lock)
    mock_lock.__exit__ = MagicMock(return_value=False)
    svc.lock_manager.lock.return_value = mock_lock

    return svc
```

Add this import at the top of the file (preserve existing imports):

```python
from tests._helpers.mock_factory import make_mock_service
```

**Critical: do NOT write `svc.activation_engine = MagicMock()`** anywhere. The helper builds activation_engine with per-method introspection (activate=MagicMock since sync, spread=AsyncMock since async). Replacing it with a bare MagicMock destroys the type-correctness and reintroduces the bug class.

**Critical: do NOT write `svc.lock_manager = MagicMock()`** anywhere. The helper builds lock_manager via inspect. Configure `.lock.return_value` on the existing helper-built mock, do not replace.

### Transformation 3: UPDATE the topographical forcing test

**Lines 174-194 (current):**

```python
def test_meta_fixture_topology_required(service: MemoryService) -> None:
    """Topographical forcing: fixture must use AsyncMock for async-target attributes.

    Architect-injected per process/issues/14a_BUILD_SPEC.md.
    DO NOT remove this test; DO NOT modify this test to use suppression patterns.

    The strict-gate suite passes iff all async-target mocks are AsyncMock AND
    every async-target CALL is properly awaited in the test bodies below.
    """
    from unittest.mock import AsyncMock

    assert isinstance(service.repo, AsyncMock), (
        "svc.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "svc.vector_store has async methods — must be AsyncMock"
    )
    # Note: svc.lock_manager itself is MagicMock (its .lock() method is sync),
    # but the mock_lock it returns must have async __aenter__/__aexit__.
    # Verified at fixture lines 148-149.
```

**Post-migration:**

```python
def test_meta_fixture_topology_required(service: MemoryService) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Updated 22c after 22a established the mock_factory helper and 22b
    validated the pattern. DO NOT remove or weaken — guard against migrations
    that bypass make_mock_service() and reintroduce the hand-rolled bug class.

    Per process/issues/22c_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    # Pure-async deps → AsyncMock
    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )

    # ActivationEngine is mixed (async spread + sync activate) — helper
    # introspects per-method via inspect.iscoroutinefunction()
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is `async def` (activation.py:98) — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, MagicMock), (
        "ActivationEngine.activate is sync `def` (activation.py:76) — must be MagicMock"
    )
    assert not isinstance(service.activation_engine.activate, AsyncMock), (
        "Guard against bare AsyncMock — production does NOT await activate"
    )

    # Sync deps → MagicMock
    assert isinstance(service.fts_store, MagicMock), (
        "service.fts_store has only sync methods — must be MagicMock"
    )
    assert isinstance(service.lock_manager, MagicMock), (
        "service.lock_manager.lock() returns a context manager (sync API) — must be MagicMock"
    )
```

### Transformation 4: REPLACE bare-MagicMock surgery on helper-built deps

Three sites in this file replace helper-built mocks with bare `MagicMock()`. Each must change to configure-on-existing-mock instead.

**Site 1: `test_happy_create_memory_type` (line 749):**

```python
# Before:
service.ontology = MagicMock()

# After:
# Delete this line entirely. Helper-built service.ontology is already a
# MagicMock(spec=OntologyManager). The test below uses .add_type which
# spec=OntologyManager will allow if OntologyManager has that method;
# if not, the test was always broken silently — escalate.
```

**Site 2: `test_sad12_create_memory_type_defaults` (line 764):**

```python
# Same as Site 1 — delete the bare MagicMock replacement.
service.ontology = MagicMock()  # ← DELETE
```

**Site 3: `test_happy_get_hologram_with_non_dict_nodes` (line 823):**

```python
# Before:
service.context_manager = MagicMock()
service.context_manager.optimize.return_value = [
    {"id": ENTITY_ID, "name": ENTITY_NAME},
]

# After:
# Delete the replacement line. Configure on the helper-built mock instead.
service.context_manager.optimize.return_value = [
    {"id": ENTITY_ID, "name": ENTITY_NAME},
]
```

If any of these sites fail post-migration with `AttributeError` because the spec-mock rejects the method access, that means the test was calling a method that doesn't exist on the real class — escalate to architect. Do NOT silently work around by re-adding bare MagicMock.

### Transformation 5: LEAVE THE REAL-METHOD REBIND SITES ALONE

Three sites use the real `MemoryService.traverse_path` method (unmocking the helper-built AsyncMock to test the actual implementation):

```python
service.traverse_path = MemoryService.traverse_path.__get__(service)
```

These appear at lines 463, 473, 483. **Preserve them as-is.** This is a legitimate "unmock to test real implementation" pattern — replacing the AsyncMock with the bound real method is intentional. Same goes for the `with patch.object(service, "search", ...)` at line 814.

### Transformation 6: VERIFY async-method-replacement sites are type-correct

The file has several `service.<dep>.<method> = AsyncMock(...)` patterns (e.g. `service.repo.execute_cypher.side_effect = ...` lines 615, 636, 661 are configuring not replacing — those are fine). Scan for any line matching `service\.\w+\.\w+ = AsyncMock\(` or `service\.\w+\.\w+ = MagicMock\(` and verify each is type-correct against the underlying class. Most should be configure-via-`.return_value`/`.side_effect` instead. Document the scan in the handoff.

## Verification (the multi-seed gate is the load-bearing test)

### Pre-PR baseline capture (test-first evidence)

Run on `master` (pre-migration) **in a clean worktree** (per 22b round-2 lesson — AG's main working directory has accumulated scratch that bleeds into evidence runs):

```bash
git worktree add ../22c-pre-pr master
cd ../22c-pre-pr
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_tools_coverage.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
done
cd - && git worktree remove ../22c-pre-pr
```

Expected: at least one seed produces non-zero RuntimeWarnings. Capture verbatim for handoff "Test-first evidence" section.

### Post-PR gate

Same command on migration branch in a clean worktree:

```bash
git worktree add ../22c-post-pr issue-22c/test-tools-coverage-migration
cd ../22c-post-pr
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_tools_coverage.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
done
cd - && git worktree remove ../22c-post-pr
```

**Required:** all 4 seeds return zero RuntimeWarnings and all tests pass.

If any seed emits RuntimeWarning, use `pytest --forked` for attribution. Fix the actual mock-type bug. Do NOT re-add suppression.

### Standard gates — RUN ALL IN A CLEAN WORKTREE

Per 22a/22b round-2 lesson, ruff and contracts evidence must come from a clean worktree to avoid scratch-file pollution. Use the `../22c-post-pr` worktree from above for these:

- `python -m pytest tests/unit/test_tools_coverage.py -v` — all tests pass
- `python -m pytest tests/_helpers/test_mock_factory.py -v` — helper tests still pass
- `tox -e contracts` — delta = 0 from master baseline (13)
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical command, no `--exclude` flags**
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

Paste output verbatim into handoff checklist items.

## The bar (Codex will verify)

- (a) `tests/unit/test_tools_coverage.py` imports `make_mock_service` from `tests._helpers.mock_factory`
- (b) `_drain_orphan_coroutines` autouse fixture is DELETED (grep returns empty)
- (c) `service` fixture body uses `make_mock_service(...)`; no hand-rolled `svc.repo = AsyncMock()`, `svc.vector_store = AsyncMock()`, `svc.fts_store = MagicMock()`, `svc.lock_manager = MagicMock()`, `svc.reranker = MagicMock()`, `svc.activation_engine = MagicMock()` survive in the fixture
- (d) Topographical forcing test asserts post-helper topology (activate=MagicMock NOT AsyncMock; spread=AsyncMock)
- (e) `test_happy_create_memory_type`, `test_sad12_create_memory_type_defaults`, `test_happy_get_hologram_with_non_dict_nodes` no longer contain `service.ontology = MagicMock()` or `service.context_manager = MagicMock()` lines (sites 1, 2, 3 from Transformation 4)
- (f) **Multi-seed gate (4 seeds) on this file returns ZERO RuntimeWarnings** — load-bearing
- (g) All tests in the file pass (no regressions); test count preserved against master baseline
- (h) `tox -e contracts`, mypy, ruff (CANONICAL command no `--exclude`), bandit all unchanged from master baseline
- (i) Scope discipline: only `tests/unit/test_tools_coverage.py` and `process/PR_ISSUE_22C_HANDOFF.md` in the diff
- (j) Pre-handoff checklist complete (9 items) with real evidence from a clean worktree, ruff command is the canonical full-scope form

## Out of scope (do NOT do in this PR)

- Do NOT modify `tests/_helpers/mock_factory.py` or any helper file
- Do NOT migrate any other test file (22d/22e handle the rest)
- Do NOT add scanner Pattern 12 (that's 22f)
- Do NOT modify `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`, or any `src/claude_memory` file
- Do NOT modify any `process/*_SPEC.md` or `process/issues/22*_HARNESS.toml`
- Do NOT touch the real-method rebind sites (lines 463, 473, 483 — legitimate `traverse_path` unmock pattern)

Write-guard via `process/issues/22_HARNESS.toml` enforces these physically.

## Round 5 discipline

Same as 22b. If the multi-seed gate fails after deletion of the suppression fixture, that's signal — find the underlying mock-type bug with `pytest --forked` attribution. Do NOT re-add `_drain_orphan_coroutines`. Do NOT add per-test `gc.collect()`.

If a spec-mock attribute access fails on the bare-MagicMock-replacement sites (Transformation 4), do NOT silently re-add the bare MagicMock — the test was calling a method that doesn't exist on the real class, which is a separate bug. Escalate to architect for spec refinement before patching.

If the helper itself appears buggy (some site behaves differently than expected), escalate immediately — denied by harness from patching it on this branch anyway.

## Hygiene reminder (from 22a/22b round-2 lessons)

**Run ALL checklist commands in a fresh worktree**, not your main working directory. Two PRs in a row failed checklist hygiene because the main directory had accumulated scratch (multi_seed_sweep.sh, per_file_scan_logs/, etc.) that bled into ruff/lint runs. The worktree pattern in the Verification section above is the standard for this arc going forward.

Use `--force-with-lease` not `--force` when pushing branch updates.
