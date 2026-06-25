# Issue #22d — Migrate `test_memory_service.py` to `make_mock_service()` (Build Spec)

**Issue:** parent #22 — sub-chunk 22d (third per-file migration, **last suppression-fixture killer**).
**Branch:** `issue-22d/test-memory-service-migration` (from current master HEAD, which must contain 22a/22b/22c)
**Pattern:** Topographical Forcing per `22b/22c_BUILD_SPEC.md`. Same shape, bigger file, more mid-test surgery sites.

---

## Target

Migrate `tests/unit/test_memory_service.py` to use `make_mock_service()`. This is the **last file with the `_drain_orphan_coroutines` suppression fixture** — after 22d merges, every suppression sneak-around from the 14a-14e arc is dead.

The file is 2078 lines but the migration diff is bounded: fixture body (identical to 22c's transformation), topographical test (needs expansion), suppression deletion, and 10 mid-test surgery sites (6 bare-MagicMock replacements to delete + 4 method-level replacements to convert).

**Scope:** this single file + its handoff doc. NO changes to the helper, no changes to other test files.

## Files in scope

- **Modify:** `tests/unit/test_memory_service.py` (the migration)
- **New:** `process/PR_ISSUE_22D_HANDOFF.md` (after the build)

Two-file diff.

## Concrete fix (architect-prescribed transformations)

### Transformation 1: DELETE the autouse suppression fixture (lines 93-107)

Same shape as 22b/22c. The fixture body identical to test_tools_coverage's:

```python
@pytest.fixture(autouse=True)
def _drain_orphan_coroutines() -> None:
    """Force GC after each test to drain orphan coroutines within test boundaries...."""
    import gc
    import warnings
    yield
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        gc.collect()
```

**Post-migration:** DELETED ENTIRELY. If post-migration multi-seed gate fails, do NOT re-add. Use `pytest --forked` for attribution.

### Transformation 2: REPLACE the `service` fixture body (lines 110-157)

The pre-migration fixture is IDENTICAL to test_tools_coverage.py's pre-22c fixture (verified by diff). Apply the EXACT same transformation as 22c's Transformation 2.

**Post-migration shape:**

```python
@pytest.fixture()
def service() -> MemoryService:
    """Creates a MemoryService with all dependencies mocked type-correctly via mock_factory.

    Per process/issues/22d_BUILD_SPEC.md — uses make_mock_service() to eliminate
    hand-rolled MagicMock-vs-AsyncMock decisions. Same pattern as 22b/22c.
    """
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = MOCK_EMBEDDING
    svc = make_mock_service(embedding_service=mock_embedder)

    # MemoryService instance methods (not deps) — preserve per soft-routing path.
    svc.query_timeline = AsyncMock(return_value=[])
    svc.traverse_path = AsyncMock(return_value=[])

    # Prevent _fire_salience_update from creating orphan asyncio.create_task() coroutines.
    svc._fire_salience_update = MagicMock()

    # Test-default returns/side_effects on helper-built typed deps
    svc.repo.get_subgraph.return_value = {"nodes": [], "edges": []}
    svc.repo.get_observations_for_entity.return_value = []
    svc.fts_store.search.return_value = []
    svc.reranker.rerank.side_effect = lambda q, c, **kw: c

    # Per-test default return values on activation_engine (22b's AG-reported AsyncMock-chain discovery).
    svc.activation_engine.activate.return_value = {}
    svc.activation_engine.spread.return_value = {}

    # Lock context manager mock — same pattern as 22c.
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

**Critical: same prohibitions as 22c.** Do NOT write `svc.activation_engine = MagicMock()` (loses per-method introspection). Do NOT write `svc.lock_manager = MagicMock()` (configure `.lock.return_value` on the helper-built mock instead).

### Transformation 3: UPDATE the topographical forcing test (lines 170-183)

**Pre-migration (current — weaker than 22c's, only checks repo+vector_store):**

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: fixture must use AsyncMock for async-target attributes.

    Architect-injected per process/issues/14b_BUILD_SPEC.md.
    DO NOT remove or weaken this test.
    """
    from unittest.mock import AsyncMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
```

**Post-migration (expand to match 22c's strength):**

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: helper must produce type-correct deps.

    Updated 22d after 22a established the mock_factory helper, 22b validated
    the pattern, and 22c expanded coverage to all mixed-async deps. DO NOT
    remove or weaken — guard against migrations that bypass make_mock_service()
    and reintroduce the hand-rolled bug class.

    Per process/issues/22d_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    # Pure-async deps → AsyncMock
    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )

    # ActivationEngine is mixed (async spread + sync activate) — helper introspects per-method
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

### Transformation 4: DELETE 5 bare-MagicMock-replacement sites on `service.ontology`

Five sites replace the helper-built `service.ontology` with a bare `MagicMock()`. Each must be deleted; if the test needs to configure `is_valid_type` (or similar), do it on the existing helper-built mock.

**Sites:**

| Line | Pattern | Fix |
|------|---------|-----|
| 929  | `service.ontology = MagicMock()` | DELETE the line entirely |
| 943  | `service.ontology = MagicMock()` | DELETE the line entirely |
| 1039 | `service.ontology = MagicMock()` (followed by `service.ontology.is_valid_type.return_value = True` on line 1040) | DELETE line 1039 only; keep 1040 |
| 1717 | `service.ontology = MagicMock()` (followed by `service.ontology.is_valid_type.return_value = True` on line 1718) | DELETE line 1717 only; keep 1718 |

(That's 4 lines in the surgery table — five originally listed in the file scan; verify count empirically. If you find a 5th site I missed, escalate.)

If any test fails post-deletion with `AttributeError` because spec=OntologyManager rejects an attribute access, the test was calling a non-existent method on OntologyManager — escalate, do NOT silently re-add the bare MagicMock.

### Transformation 5: DELETE 1 bare-MagicMock-replacement site on `service.context_manager`

**Line 1002 (with line 1003 follow-up):**

```python
service.context_manager = MagicMock()                        # ← DELETE
service.context_manager.optimize.return_value = [             # ← KEEP
    {"id": ENTITY_ID, "name": ENTITY_NAME},
]
```

Delete only line 1002; keep the `.optimize.return_value =` configuration on line 1003+.

### Transformation 6: CONVERT 4 method-level mock replacements to configure-on-existing-mock

Four sites replace specific methods on helper-built deps with new mock objects. Each should be converted to `.return_value =` assignment on the existing mock.

**Sites:**

| Line | Current | Post-migration |
|------|---------|----------------|
| 1326 | `service.ontology.is_valid_type = MagicMock(return_value=True)` | `service.ontology.is_valid_type.return_value = True` |
| 1333 | `service.vector_store.upsert = AsyncMock()` | DELETE the line — helper already configures upsert as AsyncMock by introspection (`upsert` is `async def` per VectorStore). The bare `AsyncMock()` replacement actually LOSES the spec binding. If the test needs to configure upsert behavior, use `.return_value =` or `.side_effect =` on the existing helper-built mock. |
| 1355 | same as 1326 | same conversion |
| 1361 | same as 1333 | same fix |

For sites 1333 and 1361, verify by inspection: if the test elsewhere accesses `service.vector_store.upsert.assert_awaited_once()` or similar, the helper-built AsyncMock supports the same API. If something breaks, it's signal — escalate.

### Transformation 7: VERIFY async-method-replacement scan

Per master spec discipline (added after 22c's verify-async-method scan). Scan for any remaining lines matching:

```bash
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_memory_service.py
```

Each match must be:
- A configure-on-existing-mock that just happens to use the constructor for clarity (acceptable IF type matches the underlying class)
- Or a legitimate method replacement (uncommon; should be rare)
- Or escalate as a bug

Document the scan in handoff "Discoveries" section: "Scanned N sites; M are configure-on-existing-mock with correct type; P are escalation candidates."

## Verification (the multi-seed gate is the load-bearing test)

### Pre-PR baseline capture (spec disambiguation per 22c R1 lesson)

**Critical:** master-as-is contains the `_drain_orphan_coroutines` suppression fixture. Running the canonical 4-seed sweep against master-as-is will likely produce CLEAN output across all seeds because the suppression masks the bug class. That's not the meaningful baseline.

To capture a baseline that demonstrates what the PR actually fixes, you need to run against a version of master where the suppression fixture has been removed. Two ways:

**Method A — disposable copy of master with suppression stripped:**

```bash
# Set up a clean worktree at master, then strip the suppression
git worktree add ../22d-pre-pr master
cd ../22d-pre-pr
# Remove the suppression fixture from the disposable copy (DO NOT commit)
python -c "
import re
with open('tests/unit/test_memory_service.py', 'r') as f:
    src = f.read()
# Delete the autouse fixture (lines 93-107 approx) — between '@pytest.fixture(autouse=True)' and the next '@pytest.fixture()'
pattern = re.compile(r'@pytest\.fixture\(autouse=True\)\s*\ndef _drain_orphan_coroutines.*?(?=@pytest\.fixture\(\))', re.DOTALL)
src2 = pattern.sub('', src)
with open('tests/unit/test_memory_service.py', 'w') as f:
    f.write(src2)
"
# Now run the multi-seed sweep against the bug-exposed version
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_memory_service.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
done
cd - && git worktree remove --force ../22d-pre-pr
```

Expected: at least one seed produces non-zero RuntimeWarnings/sentinel matches. **Paste all 4 seed outputs verbatim in handoff** under "Test-first evidence" with a note explaining: "captured against a disposable copy of master with the `_drain_orphan_coroutines` fixture stripped, to expose the warning class the migration fixes."

**Method B — run against master-as-is, document the clean baseline:**

If you prefer not to mess with disposable copies, run the canonical 4-seed sweep against master-as-is and paste all 4 seed outputs verbatim. Expected: clean across all 4 seeds because the suppression masks warnings. Add a note: "master-as-is produces clean output across all 4 seeds; the suppression fixture (lines 93-107) masks the warning class. The post-PR multi-seed gate against the migration validates the helper-typed mocks produce no warnings even WITHOUT the suppression."

**Either method requires pasting all 4 seed outputs.** Single-seed-only fails criterion (j).

### Post-PR gate

In a clean worktree on the migration branch:

```bash
git worktree add ../22d-post-pr issue-22d/test-memory-service-migration
cd ../22d-post-pr
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_memory_service.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
done
```

**Required:** all 4 seeds return zero RuntimeWarnings and all tests pass.

If any seed fails, use `pytest --forked` for attribution. Fix the actual mock-type bug. Do NOT re-add suppression.

### Standard gates — RUN ALL IN THE SAME CLEAN WORKTREE

Per 22a/22b/22c round-1 hygiene lessons (three PRs in a row hit checklist drift). Use the `../22d-post-pr` worktree from above for ALL evidence commands, not just the seed sweep:

```bash
# Still in ../22d-post-pr
python -m pytest tests/unit/test_memory_service.py -v --tb=short      # No regressions
python -m pytest tests/_helpers/test_mock_factory.py -v               # Helper still passes
tox -e contracts                                                       # Delta = 0 from baseline 13
python -m mypy --strict src/claude_memory                              # Clean
python -m ruff check src/claude_memory tests scripts                   # CANONICAL — NO --exclude
python -m bandit -r src/claude_memory -ll                              # Only B104
cd - && git worktree remove ../22d-post-pr
```

Paste output verbatim into handoff checklist items.

## The bar (Codex will verify)

- (a) `tests/unit/test_memory_service.py` imports `make_mock_service` from `tests._helpers.mock_factory`
- (b) `_drain_orphan_coroutines` autouse fixture is DELETED (grep returns empty)
- (c) `service` fixture body uses `make_mock_service(...)`; no hand-rolled `svc.repo = AsyncMock()`, `svc.vector_store = AsyncMock()`, `svc.fts_store = MagicMock()`, `svc.lock_manager = MagicMock()`, `svc.reranker = MagicMock()`, `svc.activation_engine = MagicMock()` survive in the fixture
- (d) Topographical forcing test asserts post-helper topology (activate=MagicMock NOT AsyncMock; spread=AsyncMock; fts_store=MagicMock; lock_manager=MagicMock)
- (e) Five `service.ontology = MagicMock()` lines deleted (verify count empirically); one `service.context_manager = MagicMock()` line deleted; four method-level `is_valid_type` / `upsert` replacements converted to `.return_value =` or deleted
- (f) **Multi-seed gate (4 seeds) on this file returns ZERO RuntimeWarnings** — load-bearing
- (g) All tests pass; test count preserved against master baseline
- (h) `tox -e contracts`, mypy, **CANONICAL** ruff (no `--exclude`), bandit all unchanged from master baseline
- (i) Scope discipline: only `tests/unit/test_memory_service.py` and `process/PR_ISSUE_22D_HANDOFF.md` in the diff
- (j) Pre-handoff checklist complete (9 items) with real evidence from a clean worktree; **pre-PR baseline shows all 4 seed outputs** (whether dirty via Method A or clean via Method B, with explanatory note); ruff command is canonical full-scope

## Out of scope (do NOT do in this PR)

- Do NOT modify `tests/_helpers/mock_factory.py`
- Do NOT migrate any other test file (22e/22f follow)
- Do NOT add scanner Pattern 12 (that's 22f)
- Do NOT modify `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`, or any `src/claude_memory` file
- Do NOT modify any `process/*_SPEC.md` or `process/issues/22*_HARNESS.toml`
- Do NOT touch test files already migrated (test_hybrid_search.py, test_tools_coverage.py)

Write-guard via `process/issues/22_HARNESS.toml` enforces these physically.

## Round 5 discipline

Same as before. If multi-seed gate fails post-suppression-deletion, attribution-diagnose with `pytest --forked` and fix the underlying mock-type bug. If a spec-mock attribute access fails on the bare-MagicMock-deletion sites (Transformations 4-6), the test was calling a non-existent method — escalate, do NOT re-add bare MagicMock.

If the helper appears buggy on some site, escalate immediately — harness denies patching it on this branch anyway.

## Hygiene rule (HARDENED from 22a/22b/22c round-1 lessons)

**Run ALL evidence commands in the SAME fresh worktree**, not your main working directory. The pattern across all three prior PRs in this micro-arc:
- 22a R1: ruff hit dirty scratch (`Found 26 errors`)
- 22b R1: AG added `--exclude` to filter dirty scratch
- 22c R1: pre-PR baseline pasted only seed 1

Single fresh worktree → single source of evidence → no contamination.

Push with `--force-with-lease` not `--force`.
