# Issue #22b — Migrate `test_hybrid_search.py` to `make_mock_service()` (Build Spec)

**Issue:** parent #22 — sub-chunk 22b (the first per-file migration).
**Branch:** `issue-22b/test-hybrid-search-migration` (from current master HEAD, which must contain 22a's merge commit landing `tests/_helpers/mock_factory.py`)
**Pattern:** Topographical Forcing per `14a_BUILD_SPEC.md`. Single-file migration, no helper changes.

---

## Target

Migrate `tests/unit/test_hybrid_search.py` to use `make_mock_service()` exclusively for `MemoryService` construction. Delete the autouse `_drain_orphan_coroutines` suppression sneak-around (introduced by 14c, never removed). Update the architect-injected topographical-forcing test (lines 106-125) to assert helper-correct topology (post-migration `activate` is MagicMock, not AsyncMock).

**Why this is load-bearing:** `test_hybrid_search.py` was the worst RuntimeWarning leakage file across the 14a-14e arc. If the multi-seed gate on this file post-migration returns **zero warnings across all 4 seeds**, the helper's design from 22a is vindicated and 22c/22d/22e become mechanical replication of the same pattern. If it doesn't, we have a bug in either the helper or this migration that must be fixed before any further per-file work.

**Scope:** this single file + its handoff doc. NO changes to the helper, no changes to other test files.

## Files in scope

- **Modify:** `tests/unit/test_hybrid_search.py` (the migration)
- **New:** `process/PR_ISSUE_22B_HANDOFF.md` (after the build)

That's it. Two-file diff.

## Concrete fix (architect-prescribed transformations)

### Transformation 1: DELETE the autouse suppression fixture

**Lines 30-44 (current):**

```python
@pytest.fixture(autouse=True)
def _drain_orphan_coroutines() -> None:
    """Force GC after each test to drain orphan coroutines within test boundaries.

    Without this, unawaited coroutines created by AsyncMock's internal
    _execute_mock_call are reaped at session end, producing warnings.
    Per-file fixture (branch write guard blocks conftest.py changes).
    """
    import gc
    import warnings

    yield
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        gc.collect()
```

**Post-migration:** **DELETED ENTIRELY.** The fixture was a 14c band-aid for the buggy hand-rolled fixture. The helper produces type-correct mocks → no orphan coroutines → no suppression needed. If the multi-seed gate fails after deletion, the helper or migration has a real bug — do NOT re-add the suppression to mask it. Escalate.

### Transformation 2: REPLACE the `service` fixture body

**Lines 47-77 (current):**

```python
@pytest.fixture()
def service():
    """MemoryService with all deps mocked."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING

    with patch("claude_memory.repository.FalkorDB"):
        with patch("claude_memory.lock_manager.redis.Redis"):
            with patch("claude_memory.vector_store.AsyncQdrantClient"):
                from claude_memory.tools import MemoryService

                svc = MemoryService(embedding_service=mock_embedder)

    svc.repo = AsyncMock()
    svc.repo = AsyncMock()  # ← copy-paste typo (current bug)
    svc.activation_engine.repo = svc.repo
    svc.vector_store = AsyncMock()
    svc.fts_store = MagicMock()
    svc.fts_store.search = MagicMock(return_value=[])
    svc.router = MagicMock(spec=QueryRouter)
    # Reranker: pass-through (return candidates unchanged)
    svc.reranker = MagicMock()
    svc.reranker.rerank = AsyncMock(side_effect=lambda q, c, **kw: c)
    # Soft routing: all channels fire, so mock default returns for all enrichments
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])
    svc.search_associative = AsyncMock(return_value=[])
    # Activation engine defaults
    svc.activation_engine.activate = AsyncMock(return_value={})  # ← WRONG TYPE (activate is sync)
    svc.activation_engine.spread = AsyncMock(return_value={})
    return svc
```

**Post-migration:**

```python
@pytest.fixture()
def service():
    """MemoryService with all deps mocked type-correctly via mock_factory.

    Per process/issues/22b_BUILD_SPEC.md — uses make_mock_service() to eliminate
    hand-rolled MagicMock-vs-AsyncMock decisions. Helper introspects each
    dependency class to AsyncMock async methods and MagicMock sync methods
    automatically.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService methods (not deps) — helper does not mock methods on the
    # service itself, only deps. These three are MemoryService instance methods
    # used by the search pipeline's soft-routing path.
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])
    svc.search_associative = AsyncMock(return_value=[])

    # Test-default returns/side_effects on helper-built typed deps
    svc.fts_store.search.return_value = []
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c

    return svc
```

Add this import at the top of the file (preserve existing imports):

```python
from tests._helpers.mock_factory import make_mock_service
```

**Why no `activation_engine.activate = ...` / `spread = ...` lines:** the helper already typed them correctly (activate=MagicMock per `activation.py:76`, spread=AsyncMock per `activation.py:98`). Tests that need specific return values configure them via `.return_value =` (assignment to the existing mock), NOT by replacing the mock with a new one.

### Transformation 3: UPDATE the topographical forcing test

**Lines 106-125 (current):**

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: activation_engine methods must be AsyncMock.

    Architect-injected per process/issues/14c_BUILD_SPEC.md.
    DO NOT remove or weaken this test.
    """
    from unittest.mock import AsyncMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, AsyncMock), (
        "ActivationEngine.activate is async — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is async — must be AsyncMock"
    )
```

**Post-migration:**

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Updated 22b after 22a established the mock_factory helper. The prior
    assertion at line 120 was wrong-on-purpose-to-match-buggy-fixture: it
    asserted activate is AsyncMock, but production code does NOT await activate
    (sync def at src/claude_memory/activation.py:76). Helper now types it
    correctly as MagicMock.

    Per process/issues/22b_BUILD_SPEC.md. DO NOT remove or weaken — guard
    against migrations that bypass make_mock_service() and reintroduce the
    hand-rolled bug class.
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
```

### Transformation 4: REPLACE mid-test mock surgery on `activation_engine`

**Lines 196-198 (in `test_happy_associative_intent_triggers_activation`, current):**

```python
        # Mock the activation engine methods
        service.activation_engine.activate = MagicMock(return_value={"a": 1.0, "b": 1.0})
        service.activation_engine.spread = MagicMock(return_value={"a": 1.0, "b": 0.6, "c": 0.3})
```

**Post-migration:**

```python
        # Configure return values on the helper-typed mocks (do NOT replace the
        # mocks — replacement would reintroduce the type-mismatch bug class
        # 22a/22b were built to prevent).
        service.activation_engine.activate.return_value = {"a": 1.0, "b": 1.0}
        service.activation_engine.spread.return_value = {"a": 1.0, "b": 0.6, "c": 0.3}
```

`AsyncMock.return_value = X` configures the awaited coroutine to resolve to `X`. `MagicMock.return_value = X` configures the call to return `X`. Both work as drop-in replacements; semantics match the prior test intent.

### No other in-test mock surgery should remain

Scan the whole file for any other `service.<dep> = MagicMock(...)` or `service.<dep>.<method> = AsyncMock(...)` patterns. The legitimate ones that should remain:
- `patch.object(service, "query_timeline", new_callable=AsyncMock)` — replaces a `MemoryService` method (not a dep), valid pattern, leave alone
- `service.vector_store.search.return_value = ...` — configuring return on a helper-built AsyncMock, valid, leave alone
- `service.router.classify.return_value = ...` — configuring return on a helper-built spec-mock, valid, leave alone
- `service.repo.get_subgraph.return_value = ...` — same, valid, leave alone
- `service.vector_store.retrieve_by_ids = AsyncMock(...)` (lines 439, 462, 479, 501, 545, 567) — these REPLACE the method. Acceptable IF the type matches (`retrieve_by_ids` is async per repository contract → AsyncMock is correct). Leave alone, but verify each is replacing-with-correct-type before finalizing.

If any verify FAILS — escalate to architect, do NOT silently patch.

## Verification (the multi-seed gate is the load-bearing test)

### Pre-PR baseline capture (test-first evidence)

Run on `master` (pre-migration), capture warning counts per seed:

```bash
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_hybrid_search.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -3
done
```

Expected: at least one seed produces non-zero RuntimeWarnings (this is the bug 22b is fixing). Capture the verbatim output for the handoff "Test-first evidence" section.

### Post-PR gate

Same command on the migration branch. **Required outcome:** all 4 seeds return ZERO warnings:

```text
=== seed=1 ===
N passed in T.TTs
=== seed=2 ===
N passed in T.TTs
=== seed=3 ===
N passed in T.TTs
=== seed=4 ===
N passed in T.TTs
```

If any seed still emits a RuntimeWarning, the migration is incomplete. Use `pytest-forked` (subprocess-per-test isolation) to identify the actual emitter:

```bash
python -m pytest tests/unit/test_hybrid_search.py --forked -W error 2>&1 | grep -B 2 RuntimeWarning
```

Then fix the actual mock-type bug at the named test — do NOT re-add the suppression fixture.

### Standard gates (deterministic, run last)

- `python -m pytest tests/unit/test_hybrid_search.py -v` — all tests pass (no regressions)
- `python -m pytest tests/_helpers/test_mock_factory.py -v` — 22a's helper tests still pass (helper unchanged)
- `tox -e contracts` — delta = 0 from master baseline (13)
- `python -m mypy --strict src/claude_memory` — clean (no source changes)
- `python -m ruff check src/claude_memory tests scripts` — clean
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

## The bar (Codex will verify)

- (a) `tests/unit/test_hybrid_search.py` imports `make_mock_service` from `tests._helpers.mock_factory`
- (b) `_drain_orphan_coroutines` autouse fixture is DELETED (grep for it must return empty)
- (c) `service` fixture body uses `make_mock_service(...)`; no hand-rolled `svc.repo = AsyncMock()` / `svc.vector_store = AsyncMock()` / `svc.fts_store = MagicMock()` / etc remain in the fixture
- (d) Topographical forcing test (`test_meta_fixture_topology_required`) asserts the corrected post-helper topology (activate is MagicMock, NOT AsyncMock; spread is AsyncMock)
- (e) `test_happy_associative_intent_triggers_activation` uses `.return_value =` assignment for activate/spread, NOT mock replacement
- (f) **Multi-seed gate (4 seeds) on this file returns ZERO RuntimeWarnings** — the load-bearing test
- (g) All tests in the file still pass (no regressions from the migration)
- (h) `tox -e contracts`, mypy, ruff, bandit all unchanged from master baseline
- (i) Scope discipline: only `tests/unit/test_hybrid_search.py` and `process/PR_ISSUE_22B_HANDOFF.md` in the diff
- (j) Pre-handoff checklist complete (9 items), with the pre-PR baseline capture pasted under "Test-first evidence"

## Out of scope (do NOT do in this PR)

- Do NOT modify `tests/_helpers/mock_factory.py` or any other helper file — if the helper has a bug surfaced by this migration, escalate to architect
- Do NOT migrate any other test file (22c-22e handle `test_tools_coverage.py`, `test_memory_service.py`, etc.)
- Do NOT add scanner Pattern 12 — that's 22f
- Do NOT modify `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`, or any `src/claude_memory` file
- Do NOT modify any `process/*_SPEC.md` or `process/issues/22*_HARNESS.toml`

Write-guard via `process/issues/22_HARNESS.toml` enforces these physically.

## Round 5 discipline

If the multi-seed gate fails after deletion of the suppression fixture, that is **signal, not noise**. Two failure modes:

1. **Migration incomplete** — a hand-rolled mock survived somewhere in the file. Find it with `pytest --forked` attribution, fix the type, rerun. This is the expected debug loop.
2. **Helper bug surfaced** — the helper produces a mock that still leaks. Escalate to architect immediately; do NOT patch the helper on this branch (the harness denies helper edits anyway). The architect updates 22a's helper on master in a separate PR, you rebase.

Do NOT re-add `_drain_orphan_coroutines` or any equivalent suppression. Do NOT add per-test `gc.collect()` calls. The whole point of 22b is to prove the helper eliminates the bug class structurally. Suppression masks the signal.
