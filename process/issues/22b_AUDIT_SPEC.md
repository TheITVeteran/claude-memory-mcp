# Issue #22b — Audit Spec (first per-file migration to make_mock_service)

**Issue:** parent #22 — sub-chunk 22b
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22b_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (the load-bearing multi-seed gate)

```bash
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_hybrid_search.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
done
```

**Required outcome:** all 4 seeds return zero RuntimeWarnings and all tests pass:

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

Any seed showing `RuntimeWarning: coroutine '...' was never awaited` = **FAIL**. Use `pytest --forked` for attribution diagnosis if you need to identify which test is the actual emitter (often differs from the test pytest attributes the warning to due to GC nondeterminism).

This is the primary load-bearing criterion. The other criteria below verify the migration is structurally correct; this one verifies it actually works.

## Per-criterion verification

### (a) Helper import added

```bash
grep -n "from tests._helpers.mock_factory import make_mock_service" tests/unit/test_hybrid_search.py
```

Must return exactly one match (one import statement).

### (b) Suppression fixture deleted

```bash
grep -n "_drain_orphan_coroutines\|gc.collect" tests/unit/test_hybrid_search.py
```

Must return **empty**. If any match, FAIL — the 14c band-aid is still present. Even partial matches (a comment referencing the old fixture, or an isolated `gc.collect()`) are blocking.

### (c) `service` fixture uses helper exclusively

The fixture body must call `make_mock_service(...)` for `MemoryService` construction. Verify by inspection of lines 47-77 (approximate; line numbers may shift).

Forbidden patterns inside the `service` fixture body (grep within the fixture function):
- `svc.repo = AsyncMock()` — helper handles this
- `svc.vector_store = AsyncMock()` — helper handles this
- `svc.fts_store = MagicMock()` — helper handles this
- `svc.router = MagicMock(spec=QueryRouter)` — helper handles this
- `svc.reranker = MagicMock()` — helper handles this
- `svc.activation_engine.repo = svc.repo` — helper does this internally
- `svc.activation_engine.activate = AsyncMock(...)` — helper types this correctly (MagicMock)
- `svc.activation_engine.spread = AsyncMock(...)` — helper types this correctly (AsyncMock)
- Any `with patch("claude_memory.repository.FalkorDB"):` or sibling patches — helper handles infrastructure patching

Allowed patterns inside the fixture body:
- `svc.query_timeline = AsyncMock(return_value=[])` — instance method on MemoryService, not a dep
- `svc.traverse_path = AsyncMock(return_value=[])` — same
- `svc.search_associative = AsyncMock(return_value=[])` — same
- `svc.fts_store.search.return_value = []` — configuring return on helper-built mock
- `svc.reranker.rerank.side_effect = lambda ...` — configuring side_effect on helper-built mock

### (d) Topographical forcing test updated correctly

```bash
python -c "
import ast, sys
with open('tests/unit/test_hybrid_search.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'test_meta_fixture_topology_required':
        src = ast.unparse(node)
        assert 'MagicMock' in src, 'forcing test must import MagicMock for activate assertion'
        assert 'activation_engine.activate' in src, 'forcing test must assert on activate'
        # The fail-loud assertion: activate must be MagicMock, NOT AsyncMock
        assert 'isinstance(service.activation_engine.activate, MagicMock)' in src, \
            'forcing test must assert activate is MagicMock (post-22a-correct topology)'
        assert 'not isinstance(service.activation_engine.activate, AsyncMock)' in src, \
            'forcing test must guard against bare AsyncMock on activate'
        print('PASS: forcing test updated to helper-correct topology')
        sys.exit(0)
print('FAIL: forcing test missing'); sys.exit(1)
"
```

Must print `PASS: forcing test updated to helper-correct topology`.

### (e) Mid-test mock surgery replaced with `.return_value =` assignment

In `test_happy_associative_intent_triggers_activation` (approximately lines 187-207), verify the `activate`/`spread` mock configuration uses assignment, not replacement:

```bash
python -c "
import ast
with open('tests/unit/test_hybrid_search.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'test_happy_associative_intent_triggers_activation':
        src = ast.unparse(node)
        # Forbidden: replacing the mock with a new one
        forbidden = [
            'service.activation_engine.activate = MagicMock(',
            'service.activation_engine.activate = AsyncMock(',
            'service.activation_engine.spread = MagicMock(',
            'service.activation_engine.spread = AsyncMock(',
        ]
        for pattern in forbidden:
            assert pattern not in src, f'FAIL: forbidden mock-replacement pattern still present: {pattern}'
        # Required: configuring return on the helper-built mock
        assert 'service.activation_engine.activate.return_value' in src, \
            'FAIL: activate must use .return_value = assignment'
        assert 'service.activation_engine.spread.return_value' in src, \
            'FAIL: spread must use .return_value = assignment'
        print('PASS: mock surgery replaced with return_value assignment')
        break
else:
    print('FAIL: target test not found')
"
```

### (f) Multi-seed gate — the canonical pass/fail above

Already specified at the top of this file. Must be zero warnings across all 4 seeds. This is the load-bearing criterion.

### (g) No test regressions

```bash
python -m pytest tests/unit/test_hybrid_search.py -v --tb=short
```

All tests in the file must pass. Compare test count against master baseline:

```bash
git stash
python -m pytest tests/unit/test_hybrid_search.py --collect-only -q 2>&1 | tail -3
git stash pop
python -m pytest tests/unit/test_hybrid_search.py --collect-only -q 2>&1 | tail -3
```

Test count post-migration must be ≥ master baseline (we don't lose tests; the forcing test may stay or expand).

Also verify 22a's helper tests still pass (helper must remain unchanged):

```bash
python -m pytest tests/_helpers/test_mock_factory.py -v
```

All 8 tests pass.

### (h) Deterministic gates unchanged

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — clean (no source changes)
- `python -m ruff check src/claude_memory tests scripts` — clean (existing invalid-noqa tolerated)
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (i) Scope discipline — write-guard not bypassed

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, ordering insensitive):
- `process/PR_ISSUE_22B_HANDOFF.md`
- `tests/unit/test_hybrid_search.py`

Any other file = FAIL with the surprise file listed. Especially watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `tests/unit/conftest.py` — denied by harness
- `process/issues/22*_SPEC.md` — denied by harness
- `src/claude_memory/*` — denied by harness

### (j) Pre-handoff checklist complete

Per master spec — 9 items with real evidence:
- `tox -e contracts` output (not `pytest -k`)
- full-scope `ruff check src/claude_memory tests scripts` output
- `bandit -r src/claude_memory -ll` output (not `N/A`)
- Multi-seed gate pre-PR baseline AND post-PR result both pasted
- No `N/A` shortcuts on deterministic gates
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "test_hybrid_search.py migrated. Multi-seed gate clean on this file. Helper design vindicated on worst-leakage file. Issues #22c (test_tools_coverage), #22d (test_memory_service), #22e (remaining files) unblocked as mechanical replications of this pattern."
