# Issue #22d — Audit Spec (third per-file migration, last suppression-fixture killer)

**Issue:** parent #22 — sub-chunk 22d
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22d_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (the load-bearing multi-seed gate)

```bash
for seed in 1 2 3 4; do
  echo "=== seed=$seed ==="
  python -m pytest tests/unit/test_memory_service.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
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

This is the load-bearing criterion.

## Per-criterion verification

### (a) Helper import added

```bash
grep -n "from tests._helpers.mock_factory import make_mock_service" tests/unit/test_memory_service.py
```

Must return exactly one match.

### (b) Suppression fixture deleted

```bash
grep -n "_drain_orphan_coroutines\|gc\.collect\|warnings\.simplefilter" tests/unit/test_memory_service.py
```

Must return **empty**. This is the last file with the suppression — after 22d merges, this grep across `tests/unit/` should also return empty (verify as a Discovery if you want).

### (c) `service` fixture uses helper exclusively

```bash
python -c "
import ast
with open('tests/unit/test_memory_service.py') as f:
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
with open('tests/unit/test_memory_service.py') as f:
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
        assert 'isinstance(service.fts_store, MagicMock)' in src, \
            'forcing test must assert fts_store is MagicMock'
        assert 'isinstance(service.lock_manager, MagicMock)' in src, \
            'forcing test must assert lock_manager is MagicMock'
        print('PASS: forcing test updated to helper-correct topology')
        sys.exit(0)
print('FAIL: forcing test missing'); sys.exit(1)
"
```

### (e) Bare-MagicMock-replacement and method-replacement sites cleaned up

```bash
# (1) All bare-MagicMock replacements of service.ontology and service.context_manager deleted
grep -nE "^\s+service\.ontology = MagicMock\(\)\s*$" tests/unit/test_memory_service.py
# Must return empty.
grep -nE "^\s+service\.context_manager = MagicMock\(\)\s*$" tests/unit/test_memory_service.py
# Must return empty.

# (2) Method-level vector_store.upsert and ontology.is_valid_type replacements converted
grep -nE "service\.vector_store\.upsert = AsyncMock\(\)" tests/unit/test_memory_service.py
# Must return empty (these should be deleted entirely — helper already provides AsyncMock).
grep -nE "service\.ontology\.is_valid_type = MagicMock\(return_value=" tests/unit/test_memory_service.py
# Must return empty (converted to .return_value = assignment).
```

If any grep returns matches, FAIL with the matched lines.

### (f) Multi-seed gate — canonical pass/fail above

Already specified. Zero warnings across 4 seeds. Load-bearing.

### (g) No test regressions

```bash
python -m pytest tests/unit/test_memory_service.py -v --tb=short
```

All tests pass. Compare test count against master baseline:

```bash
git worktree add /tmp/22d-baseline master
cd /tmp/22d-baseline
python -m pytest tests/unit/test_memory_service.py --collect-only -q 2>&1 | tail -3
cd - && git worktree remove /tmp/22d-baseline
```

Test count post-migration must be ≥ master baseline.

Helper regression check:

```bash
python -m pytest tests/_helpers/test_mock_factory.py -v
```

8 tests pass.

### (h) Deterministic gates unchanged (CANONICAL ruff — no `--exclude`)

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical**. If handoff shows `--exclude`, FAIL.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (i) Scope discipline — write-guard not bypassed

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, ordering insensitive):
- `process/PR_ISSUE_22D_HANDOFF.md`
- `tests/unit/test_memory_service.py`

Any other file = FAIL with the surprise file listed. Watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` — denied by harness
- `process/issues/22*_SPEC.md`, `process/issues/22_HARNESS.toml` — denied by harness
- `src/claude_memory/*` — denied by harness
- `tests/unit/test_hybrid_search.py`, `tests/unit/test_tools_coverage.py` — already migrated, must not be touched

### (j) Pre-handoff checklist complete — HARDENED PER 22C R1 LESSON

Per master spec — 9 items with real evidence from a clean worktree. **Additional requirements specific to this PR after 22c round-1 hygiene gap:**

- `tox -e contracts` output (not `pytest -k`)
- **canonical** `ruff check src/claude_memory tests scripts` output (NO `--exclude` flag) — FAIL if `--exclude` present
- `bandit -r src/claude_memory -ll` output (not `N/A`)
- **Pre-PR baseline shows all 4 seed outputs** — single-seed-only is FAIL (this is the hardened addition). Builder may use Method A (disposable no-drain copy of master) to demonstrate the warning class, OR Method B (master-as-is with explanatory note that suppression masks warnings). Either way, all 4 seeds must be pasted.
- **Post-PR multi-seed gate shows all 4 seed outputs** with zero warnings
- No `N/A` shortcuts
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If pre-PR baseline shows fewer than 4 seed outputs: FAIL — same hygiene gap as 22c round 1.

### Discoveries (special note for this PR)

After 22d, every `_drain_orphan_coroutines` suppression fixture should be gone from the repo. Independently verify with:

```bash
grep -rn "_drain_orphan_coroutines" tests/
```

If this returns ANY matches outside `tests/unit/test_memory_service.py` (which itself should be in the diff as a deletion), FAIL with the surprise file listed — there's a suppression sneak-around we missed during 14a-e.

If it returns empty (or only the deletion-diff context), note as a positive Discovery: "Confirmed: 22d closes the last suppression fixture in the repo. The 14a-e suppression-sneak-around bug class is fully eliminated structurally."

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "test_memory_service.py migrated. Last suppression fixture eliminated repo-wide. Issue #22e (audit remaining 8 service-fixture files for any latent bug class instances) and #22f (scanner Pattern 12 + harness lockdown) unblocked."
