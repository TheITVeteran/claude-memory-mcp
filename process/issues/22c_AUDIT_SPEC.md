# Issue #22c — Audit Spec (second per-file migration to make_mock_service)

**Issue:** parent #22 — sub-chunk 22c
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22c_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (the load-bearing multi-seed gate)

```bash
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_tools_coverage.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
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

Any seed showing `RuntimeWarning: coroutine '...' was never awaited` = **FAIL**. Use `pytest --forked` for attribution diagnosis if needed.

This is the primary load-bearing criterion. The other criteria below verify the migration is structurally correct; this one verifies it actually works.

## Per-criterion verification

### (a) Helper import added

```bash
grep -n "from tests._helpers.mock_factory import make_mock_service" tests/unit/test_tools_coverage.py
```

Must return exactly one match.

### (b) Suppression fixture deleted

```bash
grep -n "_drain_orphan_coroutines\|gc\.collect\|warnings\.simplefilter" tests/unit/test_tools_coverage.py
```

Must return **empty**. If any match, FAIL — the 14a band-aid is still present.

### (c) `service` fixture uses helper exclusively

The fixture body must call `make_mock_service(...)` for `MemoryService` construction. Forbidden patterns inside the `service` fixture body:

```bash
python -c "
import ast
with open('tests/unit/test_tools_coverage.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'service':
        src = ast.unparse(node)
        forbidden = [
            'svc.repo = AsyncMock()',
            'svc.vector_store = AsyncMock()',
            'svc.fts_store = MagicMock()',
            'svc.lock_manager = MagicMock()',
            'svc.reranker = MagicMock()',
            'svc.activation_engine = MagicMock()',
            'svc.activation_engine.activate = AsyncMock(',
            'with patch(\"claude_memory.repository.FalkorDB\"):',
            'with patch(\"claude_memory.lock_manager.redis.Redis\"):',
            'with patch(\"claude_memory.vector_store.AsyncQdrantClient\"):',
        ]
        for pattern in forbidden:
            assert pattern not in src, f'FAIL: forbidden pattern in fixture: {pattern}'
        assert 'make_mock_service(' in src, 'FAIL: fixture must call make_mock_service'
        print('PASS: fixture uses helper exclusively, no hand-rolled mocks')
        break
else:
    print('FAIL: service fixture not found')
"
```

### (d) Topographical forcing test updated correctly

```bash
python -c "
import ast, sys
with open('tests/unit/test_tools_coverage.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'test_meta_fixture_topology_required':
        src = ast.unparse(node)
        assert 'isinstance(service.activation_engine.activate, MagicMock)' in src, \
            'forcing test must assert activate is MagicMock (post-helper-correct topology)'
        assert 'isinstance(service.activation_engine.spread, AsyncMock)' in src, \
            'forcing test must assert spread is AsyncMock'
        assert 'not isinstance(service.activation_engine.activate, AsyncMock)' in src, \
            'forcing test must guard against bare AsyncMock on activate'
        print('PASS: forcing test updated to helper-correct topology')
        sys.exit(0)
print('FAIL: forcing test missing'); sys.exit(1)
"
```

### (e) Bare-MagicMock-replacement sites cleaned up

```bash
python -c "
import ast
with open('tests/unit/test_tools_coverage.py') as f:
    tree = ast.parse(f.read())
target_tests = {
    'test_happy_create_memory_type',
    'test_sad12_create_memory_type_defaults',
    'test_happy_get_hologram_with_non_dict_nodes',
}
found_tests = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in target_tests:
        found_tests.add(node.name)
        src = ast.unparse(node)
        forbidden = [
            'service.ontology = MagicMock()',
            'service.context_manager = MagicMock()',
        ]
        for pattern in forbidden:
            assert pattern not in src, f'FAIL: {node.name} still contains: {pattern}'
assert found_tests == target_tests, f'FAIL: missing target tests: {target_tests - found_tests}'
print('PASS: bare-MagicMock replacement sites cleaned up in 3 target tests')
"
```

### (f) Multi-seed gate — the canonical pass/fail above

Already specified. Zero warnings across 4 seeds. Load-bearing criterion.

### (g) No test regressions

```bash
python -m pytest tests/unit/test_tools_coverage.py -v --tb=short
```

All tests pass. Compare test count against master baseline:

```bash
git stash
python -m pytest tests/unit/test_tools_coverage.py --collect-only -q 2>&1 | tail -3
git stash pop
python -m pytest tests/unit/test_tools_coverage.py --collect-only -q 2>&1 | tail -3
```

Test count post-migration must be ≥ master baseline.

Helper regression check:

```bash
python -m pytest tests/_helpers/test_mock_factory.py -v
```

8 tests pass.

### (h) Deterministic gates unchanged (CANONICAL ruff command — no `--exclude`)

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical command, no `--exclude` flags**. If the handoff shows ruff evidence with `--exclude`, FAIL — that's the same hygiene gap from 22a/22b round-1.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (i) Scope discipline — write-guard not bypassed

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, ordering insensitive):
- `process/PR_ISSUE_22C_HANDOFF.md`
- `tests/unit/test_tools_coverage.py`

Any other file = FAIL with the surprise file listed. Especially watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` — denied by harness
- `process/issues/22*_SPEC.md`, `process/issues/22_HARNESS.toml` — denied by harness
- `src/claude_memory/*` — denied by harness
- `tests/unit/test_hybrid_search.py` — was already migrated in 22b, must not be touched

### (j) Pre-handoff checklist complete

Per master spec — 9 items with real evidence from a clean worktree:
- `tox -e contracts` output (not `pytest -k`)
- **canonical** `ruff check src/claude_memory tests scripts` output (NO `--exclude` flag)
- `bandit -r src/claude_memory -ll` output (not `N/A`)
- Multi-seed gate pre-PR baseline AND post-PR result both pasted
- No `N/A` shortcuts
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If ruff evidence uses `--exclude` flag: FAIL — same pattern as 22a/22b round-1 hygiene drift.

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "test_tools_coverage.py migrated. Multi-seed gate clean on file with largest dep surface area. Issues #22d (test_memory_service), #22e (remaining files) unblocked as mechanical replications."
