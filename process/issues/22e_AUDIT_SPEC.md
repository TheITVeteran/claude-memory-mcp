# Issue #22e — Audit Spec (final per-file migration round, 4 files)

**Issue:** parent #22 — sub-chunk 22e
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22e_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (16 runs — 4 files × 4 seeds)

```bash
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
```

**Required outcome:** all 16 runs return zero RuntimeWarnings and all tests pass per file. Any seed showing `RuntimeWarning: coroutine '...' was never awaited` = **FAIL**.

This is the load-bearing criterion.

## Per-criterion verification

### (a) Helper import added to all 4 files

```bash
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "=== ${file}.py ==="
  grep -n "from tests._helpers.mock_factory import make_mock_service" tests/unit/${file}.py
done
```

Each file must return exactly one match.

### (b) All 4 fixtures use helper exclusively, no hand-rolled mocks

```bash
python -c "
import ast
files_and_fixtures = [
    ('tests/unit/test_entity_channel.py', 'service'),
    ('tests/unit/test_search_associative.py', 'service'),
    ('tests/unit/test_embedding_filter.py', 'mock_service'),
    ('tests/unit/test_channel_degradation.py', 'service'),
]
for path, fixture_name in files_and_fixtures:
    with open(path) as f:
        tree = ast.parse(f.read())
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fixture_name:
            found = True
            src = ast.unparse(node)
            forbidden = [
                'svc.repo = AsyncMock()',
                'service.repo = AsyncMock()',
                'svc.vector_store = AsyncMock()',
                'service.vector_store = AsyncMock()',
                'svc.fts_store = MagicMock()',
                'service.fts_store = MagicMock()',
                'svc.lock_manager = MagicMock()',
                'service.lock_manager = MagicMock()',
                'svc.reranker = MagicMock()',
                'service.reranker = MagicMock()',
                'svc.activation_engine = MagicMock()',
                'service.activation_engine = MagicMock()',
                'with patch(\"claude_memory.repository.FalkorDB\"):',
                'with patch(\"claude_memory.tools.MemoryRepository\"):',
                'with patch(\"claude_memory.lock_manager.redis.Redis\"):',
                'with patch(\"claude_memory.vector_store.AsyncQdrantClient\"):',
            ]
            for pattern in forbidden:
                assert pattern not in src, f'FAIL: {path} fixture {fixture_name} contains forbidden: {pattern}'
            assert 'make_mock_service(' in src, f'FAIL: {path} fixture {fixture_name} must call make_mock_service'
            break
    assert found, f'FAIL: fixture {fixture_name} not found in {path}'
print('PASS: all 4 fixtures use helper exclusively, no hand-rolled mocks')
"
```

### (c) test_search_associative.py — duplicate-repo typo and misleading comment gone

```bash
grep -c "svc.repo = AsyncMock()" tests/unit/test_search_associative.py
# Must return 0 (helper builds repo; no manual assignment needed)

grep -n "sync so spread()" tests/unit/test_search_associative.py
# Must return empty (misleading comment removed)
```

### (d) test_entity_channel.py — wrong-type spread MagicMock gone

```bash
grep -n "activation_engine.spread = MagicMock" tests/unit/test_entity_channel.py
# Must return empty (was wrong type — helper makes it AsyncMock)
```

### (e) test_embedding_filter.py — wrong-type activate AsyncMock gone AND inline ad-hoc construction migrated

```bash
grep -n "activation_engine.activate = AsyncMock" tests/unit/test_embedding_filter.py
# Must return empty (was wrong type — helper makes it MagicMock)

# Inline ad-hoc check: test_sad1 must NOT contain inline MemoryService(...) construction
python -c "
import ast
with open('tests/unit/test_embedding_filter.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'test_sad1_create_entity_receipt_missing_embedding_key_evil':
        src = ast.unparse(node)
        assert 'MemoryService(embedding_service=' not in src, \
            'FAIL: test_sad1 still has inline MemoryService(...) construction'
        assert 'make_mock_service(' in src, \
            'FAIL: test_sad1 must use make_mock_service() for service construction'
        print('PASS: test_sad1 inline construction migrated')
        break
"
```

### (f) test_channel_degradation.py — async lock context manager PRESERVED

```bash
python -c "
import ast, re
with open('tests/unit/test_channel_degradation.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'service':
        src = ast.unparse(node)
        # Positive: helper-correct async lock assignments must be present.
        # Match assignment patterns (\.__name__\s*=), NOT bare string presence —
        # docstring text mentioning __aenter__/__enter__ for teaching purposes
        # must not trigger the check. Bug originally found 22e R1: build spec's
        # golden diff docstring contained literal __enter__/__exit__ as a
        # teaching note and crashed the bare-string-presence check.
        assert re.search(r'\\.__aenter__\\s*=', src), 'FAIL: async .__aenter__ = assignment missing'
        assert re.search(r'\\.__aexit__\\s*=', src), 'FAIL: async .__aexit__ = assignment missing'
        # Negative: sync .__enter__ = / .__exit__ = assignments must NOT be present
        # (docstring mentions are fine; only assignment patterns are forbidden).
        assert not re.search(r'\\.__enter__\\s*=', src), \
            'FAIL: sync .__enter__ = assignment in fixture — should be .__aenter__ = (async). 22b/22c/22d pattern incorrectly applied.'
        assert not re.search(r'\\.__exit__\\s*=', src), \
            'FAIL: sync .__exit__ = assignment in fixture — should be .__aexit__ = (async).'
        print('PASS: async lock context manager pattern preserved')
        break
"
```

### (g) All 4 files have topographical forcing test

```bash
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "=== ${file}.py ==="
  grep -n "def test_meta_fixture_topology_required" tests/unit/${file}.py
done
```

Each file must return exactly one match. Verify assertions are helper-correct:

```bash
python -c "
import ast
files = [
    'tests/unit/test_entity_channel.py',
    'tests/unit/test_search_associative.py',
    'tests/unit/test_embedding_filter.py',
    'tests/unit/test_channel_degradation.py',
]
for path in files:
    with open(path) as f:
        tree = ast.parse(f.read())
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'test_meta_fixture_topology_required':
            found = True
            src = ast.unparse(node)
            assert 'isinstance' in src and 'AsyncMock' in src, f'FAIL: {path} forcing test missing isinstance/AsyncMock checks'
            assert 'activation_engine' in src, f'FAIL: {path} forcing test missing activation_engine check'
            break
    assert found, f'FAIL: {path} missing topographical forcing test'
print('PASS: all 4 files have helper-correct topographical forcing test')
"
```

Additionally, test_channel_degradation.py's forcing test should include an `__aenter__` assertion on the lock — verify by grep:

```bash
grep -A 30 "def test_meta_fixture_topology_required" tests/unit/test_channel_degradation.py | grep "__aenter__"
# Must return a non-empty match (async lock guard)
```

### (h) Multi-seed gate — canonical pass/fail (above)

16 runs. Zero warnings. Load-bearing.

### (i) No test regressions

```bash
python -m pytest tests/unit/test_entity_channel.py tests/unit/test_search_associative.py tests/unit/test_embedding_filter.py tests/unit/test_channel_degradation.py -v --tb=short
```

All tests pass. Compare test count per file against master baseline:

```bash
git worktree add /tmp/22e-baseline master
cd /tmp/22e-baseline
for file in test_entity_channel test_search_associative test_embedding_filter test_channel_degradation; do
  echo "=== ${file}.py baseline ==="
  python -m pytest tests/unit/${file}.py --collect-only -q 2>&1 | tail -3
done
cd - && git worktree remove /tmp/22e-baseline
```

Test count post-migration must be ≥ master baseline + 4 (one new forcing test per file).

Helper regression check:
```bash
python -m pytest tests/_helpers/test_mock_factory.py -v
```

### (j) Deterministic gates unchanged (CANONICAL ruff)

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical**. If handoff shows `--exclude`, FAIL.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (k) Scope discipline — write-guard not bypassed

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, 5 files, ordering insensitive):
- `process/PR_ISSUE_22E_HANDOFF.md`
- `tests/unit/test_entity_channel.py`
- `tests/unit/test_search_associative.py`
- `tests/unit/test_embedding_filter.py`
- `tests/unit/test_channel_degradation.py`

Any other file = FAIL. Watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` — denied by harness
- `process/issues/22*_SPEC.md`, `process/issues/22_HARNESS.toml` — denied by harness
- `src/claude_memory/*` — denied by harness
- Already-migrated files (test_hybrid_search, test_tools_coverage, test_memory_service) — must not be touched
- Out-of-scope files (test_router, test_list_orphans, test_locking, test_hologram) — must not be touched

### (l) Pre-handoff checklist complete — HARDENED

Per master spec — 9 items with real evidence from a clean worktree. **Hardened criteria specific to this PR:**

- `tox -e contracts` output (not `pytest -k`)
- **canonical** `ruff check src/claude_memory tests scripts` output (NO `--exclude` flag) — FAIL if `--exclude` present
- `bandit -r src/claude_memory -ll` output (not `N/A`)
- **Pre-PR baseline shows all 4 seeds per file × 4 files = 16 seed outputs** — single-seed-per-file or partial-file-coverage is FAIL
- **Post-PR multi-seed gate shows all 16 outputs** with zero warnings
- Per-file async-method-replacement scan documented in "Discoveries" section
- No `N/A` shortcuts
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If pre-PR baseline shows fewer than 16 seed outputs total: FAIL.

### Discoveries (positive checks for this PR)

After verifying scope, run repo-wide checks:

```bash
# (1) Confirm NO suppression fixture survives anywhere in tests/
grep -rn "_drain_orphan_coroutines" tests/
# Expected: empty (22d already eliminated the last one; 22e doesn't add any).
```

If any match outside this PR's diff context, FAIL with the surprise file listed.

```bash
# (2) Confirm hand-rolled MemoryService fixtures only exist in out-of-scope files now
grep -rn "MemoryService(embedding_service=" tests/unit/ | grep -v "test_router\|test_list_orphans\|test_locking\|test_hologram"
# Expected: zero matches (or only inside make_mock_service() implementation, which is in tests/_helpers/, not tests/unit/).
```

If matches appear in any other file, flag as Discovery — there may be additional hand-rolled fixtures the architect missed during investigation.

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "4 remaining service-fixture files migrated. Every MemoryService fixture in the suite (except the 4 out-of-scope files with different patterns) now uses make_mock_service(). Issue #22f (scanner Pattern 12 + harness lockdown + verify_handoff_completeness hook) is the final arc piece."
