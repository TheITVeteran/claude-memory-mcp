# Issue #22e-bis — Audit Spec (contract-test files migration, post-22e additive-discovery follow-up)

**Issue:** parent #22 — sub-chunk 22e-bis
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22e_bis_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (8 runs — 2 files × 4 seeds)

```bash
for file in test_batch3_contracts test_batch5_contracts; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
```

**Required outcome:** all 8 runs return zero RuntimeWarnings and all tests pass per file. Any seed showing `RuntimeWarning: coroutine '...' was never awaited` = **FAIL**.

This is the load-bearing criterion.

## Per-criterion verification

### (a) Helper import added to both files

```bash
for file in test_batch3_contracts test_batch5_contracts; do
  echo "=== ${file}.py ==="
  grep -n "from tests._helpers.mock_factory import make_mock_service" tests/unit/${file}.py
done
```

Each file must return exactly one match.

### (b) test_batch3 fixture uses helper exclusively

```bash
python -c "
import ast
with open('tests/unit/test_batch3_contracts.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'search_service':
        src = ast.unparse(node)
        forbidden = [
            'service.activation_engine = MagicMock()',
            'service.repo = AsyncMock()',
            'service.fts_store = ',
            'with patch(\"claude_memory.repository.FalkorDB\"):',
            'MemoryService(embedding_service=',
        ]
        for pattern in forbidden:
            assert pattern not in src, f'FAIL: search_service fixture contains forbidden: {pattern}'
        assert 'make_mock_service(' in src, 'FAIL: search_service must call make_mock_service'
        print('PASS: test_batch3 search_service fixture uses helper exclusively')
        break
else:
    print('FAIL: search_service fixture not found')
"
```

### (c) test_batch5 — no inline `MemoryService(...)` constructions, no duplicate-repo typos

```bash
# (1) Confirm no inline MemoryService constructions remain
grep -c "MemoryService(embedding_service=" tests/unit/test_batch5_contracts.py
# Must return 0 (constructions extracted to fixture).

# (2) Confirm no duplicate-repo typos remain (the 20 sites all eliminated)
grep -c "svc.repo = AsyncMock()" tests/unit/test_batch5_contracts.py
# Must return 0 (helper builds repo; no manual assignment).

# (3) Confirm no inline FalkorDB patch contexts in test methods
grep -c "with patch(\"claude_memory.repository.FalkorDB\"):" tests/unit/test_batch5_contracts.py
# Must return 0 (helper handles infrastructure patching).
```

### (d) test_batch5 — all 10 test methods take `service` fixture parameter

```bash
python -c "
import ast
with open('tests/unit/test_batch5_contracts.py') as f:
    tree = ast.parse(f.read())

# Find module-level service fixture
fixture_found = False
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'service':
        src = ast.unparse(node)
        assert 'make_mock_service(' in src, 'FAIL: service fixture must call make_mock_service'
        fixture_found = True
        break
assert fixture_found, 'FAIL: module-level service fixture not found'

# Verify all 10 test methods accept service parameter
test_methods = []
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith('test_'):
        param_names = [arg.arg for arg in node.args.args]
        assert 'service' in param_names, f'FAIL: {node.name} missing service fixture param'
        test_methods.append(node.name)

assert len(test_methods) == 10, f'FAIL: expected 10 test methods, found {len(test_methods)}: {test_methods}'
print(f'PASS: all {len(test_methods)} test methods take service fixture')
"
```

### (e) Both files have topographical forcing test

```bash
for file in test_batch3_contracts test_batch5_contracts; do
  echo "=== ${file}.py ==="
  grep -n "def test_meta_fixture_topology_required" tests/unit/${file}.py
done
```

Each file must return exactly one match.

```bash
python -c "
import ast
files = ['tests/unit/test_batch3_contracts.py', 'tests/unit/test_batch5_contracts.py']
for path in files:
    with open(path) as f:
        tree = ast.parse(f.read())
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'test_meta_fixture_topology_required':
            found = True
            src = ast.unparse(node)
            assert 'isinstance' in src and 'AsyncMock' in src, f'FAIL: {path} forcing test missing checks'
            assert 'activation_engine' in src, f'FAIL: {path} forcing test missing activation_engine check'
            break
    assert found, f'FAIL: {path} missing topographical forcing test'
print('PASS: both files have helper-correct topographical forcing test')
"
```

### (f) Multi-seed gate — canonical pass/fail (above)

8 runs. Zero warnings. Load-bearing.

### (g) No test regressions

```bash
python -m pytest tests/unit/test_batch3_contracts.py tests/unit/test_batch5_contracts.py -v --tb=short
```

All tests pass. Compare test count per file against master baseline (post-22e merge):

```bash
git worktree add /tmp/22e-bis-baseline master
cd /tmp/22e-bis-baseline
for file in test_batch3_contracts test_batch5_contracts; do
  echo "=== ${file}.py baseline ==="
  python -m pytest tests/unit/${file}.py --collect-only -q 2>&1 | tail -3
done
cd - && git worktree remove /tmp/22e-bis-baseline
```

Test count post-migration must be ≥ master baseline + 2 (one new forcing test per file).

Helper regression check:
```bash
python -m pytest tests/_helpers/test_mock_factory.py -v
```

### (h) Deterministic gates unchanged (CANONICAL ruff)

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical**. If handoff shows `--exclude`, FAIL.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (i) Scope discipline

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, 3 files):
- `process/PR_ISSUE_22E_BIS_HANDOFF.md`
- `tests/unit/test_batch3_contracts.py`
- `tests/unit/test_batch5_contracts.py`

Any other file = FAIL. Watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` — denied by harness
- `process/issues/22*_SPEC.md`, `process/issues/22_HARNESS.toml` — denied by harness
- `src/claude_memory/*` — denied by harness
- The 6 Category D files (`test_dynamic_validation`, `test_full_workflow`, `test_mutant_dict_crud`, `test_mutant_dict_services`, `test_mutant_temporal`, `test_temporal`) must not be touched
- Already-migrated 22b/22c/22d/22e files must not be touched

### (j) Pre-handoff checklist complete — HARDENED

Per master spec — 9 items with real evidence from a clean worktree:

- `tox -e contracts` output (not `pytest -k`)
- **canonical** `ruff check src/claude_memory tests scripts` output (NO `--exclude` flag) — FAIL if `--exclude` present
- `bandit -r src/claude_memory -ll` output (not `N/A`)
- **Pre-PR baseline shows all 4 seeds per file × 2 files = 8 seed outputs** — single-seed-per-file or partial-file-coverage is FAIL
- **Post-PR multi-seed gate shows all 8 outputs** with zero warnings
- Per-file async-method-replacement scan documented in "Discoveries"
- No `N/A` shortcuts
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If pre-PR baseline shows fewer than 8 seed outputs: FAIL.

### Discoveries (verification check for the closing arc state)

After verifying scope, run repo-wide checks to confirm the bug class is fully eliminated outside the 6 Category D files:

```bash
# (1) Suppression fixture sentinel — must remain at zero
grep -rn "_drain_orphan_coroutines" tests/
# Expected: empty. If any match, FAIL.

# (2) Hand-rolled MemoryService construction sentinel — filtered to exclude Category D files
grep -rn "MemoryService(embedding_service=" tests/unit/ | grep -vE "test_dynamic_validation|test_full_workflow|test_mutant_dict_crud|test_mutant_dict_services|test_mutant_temporal|test_temporal|test_router|test_list_orphans|test_locking|test_hologram"
# Expected: empty post-22e-bis. If any match in a non-allowlisted file, flag as Discovery
# — indicates a hand-rolled MemoryService construction the architect investigation missed.
```

If both checks pass, note as positive Discovery: "22e-bis closes the additive-discovery gap from 22e. Bug class structurally eliminated outside the 10 allowlisted Category D files. 22f's scanner Pattern 12 can start at baseline 0."

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "22e-bis closes the additive-discovery gap. Hand-rolled MemoryService construction outside the 10 Category D files is fully eliminated. Issue #22f (scanner Pattern 12 + verify_handoff_completeness hook + harness lockdown) can proceed with scanner baseline = 0."
