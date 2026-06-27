# B10.5 — Native Async Migration (Audit Spec)

**Epic:** B10.5
**Auditor:** ChatGPT Codex 5.5 (NEW session — no context inheritance from #22 arc)
**Builder spec:** `process/issues/B10_5_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (load-bearing: integration tests on native async)

```bash
RUN_INTEGRATION=1 python -m pytest tests/integration/test_db_kill_scenarios.py -v --tb=short
```

**Required outcome:** all 6 tests pass on the migration branch. Each test must show `PASSED` status. Real testcontainers (FalkorDB v4.14.11 + Qdrant v1.16.3) — these are behavioral tests against real infra with native async, not unit-level mocks.

Any test FAILED, ERROR, or SKIPPED (for reasons other than missing `RUN_INTEGRATION=1`) = **FAIL**. The integration suite is the load-bearing verification that native async preserves the SearchError contract end-to-end.

This is the primary criterion. The other criteria below verify migration structure; this one verifies behavior.

## Per-criterion verification

### (a) Cypher constants extracted to `cypher_queries.py`

```bash
# File must exist
test -f src/claude_memory/cypher_queries.py && echo "PASS" || echo "FAIL: missing"

# Survey shows no inline Cypher remains in repo files.
# Excludes docstrings (Expr->Constant pattern) and module-level strings.
# Only flags Constants used as arguments to .query()/.execute() calls.
# REVISED 2026-06-27 after B10.5 R2 audit found bare-string check had
# legitimate docstring false-positives (same pattern as 22e R1).
python -c "
import ast
files_to_check = [
    'src/claude_memory/repository.py',
    'src/claude_memory/repository_queries.py',
    'src/claude_memory/repository_traversal.py',
    'src/claude_memory/repository_async.py',
]
cypher_keywords = ['MATCH ', 'MERGE ', 'CREATE ', 'WITH ', 'RETURN ', 'WHERE ']

def is_docstring(node, parent_map):
    '''Check if this Constant is a docstring (first Expr in module/class/function body).'''
    parent = parent_map.get(id(node))
    if not isinstance(parent, ast.Expr):
        return False
    grandparent = parent_map.get(id(parent))
    if not isinstance(grandparent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return grandparent.body and grandparent.body[0] is parent

def is_query_argument(node, parent_map):
    '''Check if this Constant is passed as an argument to .query()/.execute() calls.'''
    parent = parent_map.get(id(node))
    if not isinstance(parent, ast.Call):
        return False
    func = parent.func
    method_name = func.attr if isinstance(func, ast.Attribute) else None
    return method_name in ('query', 'execute_cypher', 'execute')

for path in files_to_check:
    with open(path) as f:
        tree = ast.parse(f.read())
    parent_map = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node
    inline_cypher = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if not (any(kw in node.value.upper() for kw in cypher_keywords) and len(node.value) > 30):
            continue
        # Exclude docstrings — they're allowed to contain Cypher keywords for documentation
        if is_docstring(node, parent_map):
            continue
        # Only flag if used as a query argument (this is the actual bug class)
        if is_query_argument(node, parent_map):
            inline_cypher.append((node.lineno, node.value[:60]))
    if inline_cypher:
        print(f'FAIL: {path} contains inline Cypher passed to .query()/.execute() at lines: {inline_cypher}')
        print(f'  All such Cypher should be in cypher_queries.py constants.')
        exit(1)
print('PASS: no inline Cypher passed as query arguments; docstrings excluded; all live queries reference cypher_queries.py constants')
"
```

### (b) Native async — no `asyncio.to_thread` in `repository_async.py`

```bash
grep -c "asyncio.to_thread\|to_thread(" src/claude_memory/repository_async.py
# Must return 0. The wrapper pattern is fully eliminated.

# Verify native async client is imported
grep -n "from falkordb.asyncio import FalkorDB" src/claude_memory/repository_async.py
# Must return exactly one match.
```

### (c) Sync `MemoryRepository` preserved (Director's x-ray vision call)

```bash
# File still exists
test -f src/claude_memory/repository.py && echo "PASS" || echo "FAIL: deleted"

# Class still importable and instantiable
python -c "
from claude_memory.repository import MemoryRepository
import inspect
assert inspect.isclass(MemoryRepository), 'FAIL: MemoryRepository not a class'
# Class should have the diagnostic-role docstring
src = inspect.getsource(MemoryRepository)
assert 'diagnostic' in src.lower() or 'cli ops' in src.lower() or 'x-ray' in src.lower(), \
    'FAIL: MemoryRepository docstring should explain its post-B10.5 diagnostic role'
print('PASS: sync MemoryRepository preserved with diagnostic-role docstring')
"
```

### (d) `tools.py:82` construction simplified

```bash
grep -n "AsyncMemoryRepository(" src/claude_memory/tools.py
# Must show: `self.repo = AsyncMemoryRepository(host, port, password)` (or similar direct construction)
# Must NOT show: `AsyncMemoryRepository(MemoryRepository(...))`

python -c "
with open('src/claude_memory/tools.py') as f:
    src = f.read()
assert 'AsyncMemoryRepository(MemoryRepository(' not in src, \
    'FAIL: tools.py still wraps sync MemoryRepository inside AsyncMemoryRepository'
assert 'AsyncMemoryRepository(' in src, 'FAIL: tools.py missing AsyncMemoryRepository construction'
print('PASS: tools.py construction simplified to direct AsyncMemoryRepository(...)')
"
```

### (e) `test_repository_async.py` rewritten — behavioral, not delegation

```bash
python -c "
import ast
with open('tests/unit/test_repository_async.py') as f:
    tree = ast.parse(f.read())

# (1) No delegation test names survive
delegation_test_pattern_count = 0
test_count = 0
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
        test_count += 1
        if 'delegate' in node.name.lower() or 'to_thread' in node.name.lower():
            delegation_test_pattern_count += 1

assert delegation_test_pattern_count == 0, \
    f'FAIL: {delegation_test_pattern_count} delegation/to_thread test names survive — should all be behavioral'

# (2) Behavioral test count meets minimum (≥26 per spec)
assert test_count >= 26, f'FAIL: only {test_count} tests, spec requires ≥26 behavioral tests'

# (3) Source uses native async mock pattern
src_text = ast.unparse(tree)
assert 'falkordb.asyncio' in src_text or 'FalkorDB' in src_text, \
    'FAIL: tests should mock the native async client'

print(f'PASS: test_repository_async.py rewritten with {test_count} behavioral tests, no delegation tests')
"
```

### (f) Integration tests pass — canonical pass/fail (above)

Already specified. 6 tests, all PASS. Load-bearing.

### (g) No regression in adjacent test files

```bash
# Standard unit test suite must pass
python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -5
# All previously-passing tests still pass; count >= master baseline.

# Helper acceptance tests
python -m pytest tests/_helpers/test_mock_factory.py -v
# 8 pass.

# Multi-seed gate on the most-migrated test files (sanity check that 22 arc gains preserved)
for file in test_hybrid_search test_tools_coverage test_memory_service; do
    for seed in 1 2 3 4; do
        python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -2
    done
done
# All clean (zero RuntimeWarning).
```

### (h) Deterministic gates unchanged

- `tox -e contracts` — baseline 13 unchanged (Pattern 12 still 0)
- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical** (no `--exclude`). FAIL if `--exclude` present.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (i) Dependency tightening in `pyproject.toml`

```bash
grep -A 0 "falkordb" pyproject.toml | head -3
# Must show: `"falkordb>=1.4.0,<2.0.0",` (lower bound tightened from 1.0.0 to 1.4.0)
```

### (j) Scope discipline

```bash
git diff --name-only origin/master..HEAD
```

**REVISED 2026-06-27 after B10.5 R2 + R3 audits:** scope expanded from 9 → 13 → 14 files via two oracle corrections in build spec. Expected output (must match, ordering insensitive — **14 files**):

Original 9:
- `src/claude_memory/cypher_queries.py` (new)
- `src/claude_memory/repository_async.py`
- `src/claude_memory/repository.py`
- `src/claude_memory/repository_queries.py`
- `src/claude_memory/repository_traversal.py`
- `src/claude_memory/tools.py`
- `tests/unit/test_repository_async.py`
- `pyproject.toml`
- `process/PR_B10_5_HANDOFF.md` (new)

Added in R2 scope expansion (test infrastructure):
- `tests/_helpers/mock_factory.py` (patch new async FalkorDB path)
- `tests/unit/test_mutant_dict_crud.py` (update `_build()` patches)
- `tests/unit/test_mutant_dict_services.py` (update `_build()` patches)
- `tests/unit/test_mutant_temporal.py` (update `_build()` patches)

Added in R3 scope expansion (type-preserving decorator):
- `src/claude_memory/retry.py` (`retry_on_transient` decorator rewrite with `ParamSpec` + `TypeVar` to preserve signatures through the wrapper — eliminates `[no-any-return]` in mixin call sites)

Any file beyond these 14 = FAIL. Watch for:
- `tests/unit/test_*` other than the 4 explicitly listed — must not be touched (Category A files already migrated in 22 arc don't need re-touching unless their patches now break)
- `process/*_SPEC.md` other than the new B10.5 handoff — denied per spec discipline (architect-owned)
- `scripts/hooks/*` — 5-layer enforcement infrastructure must not be modified
- `scripts/trace_contracts_dragon.py` — Pattern 12 scanner must not be modified

**Verification:** the AG amend MUST first rebase onto current `origin/master` to absorb prior architect patches (hook regex fix at `2a69a70`, scorched earth Dimension 9 at `b500ced`, B10.5 spec patches at HEAD). Without rebase, `git diff origin/master..HEAD` shows phantom files. Failure to rebase = FAIL on this criterion with explanatory note "AG branch behind master; rebase required."

### (k) Pre-handoff checklist complete

Per master spec + `verify_handoff_completeness.py` auto-enforcement (hook regex patched 2026-06-27 to `^process/PR_.*_HANDOFF\.md$` after B10.5 R1 audit found `PR_B10_5_HANDOFF.md` was bypassing the original `PR_ISSUE_*` filter):

- Pre-PR baseline shows all 6 integration tests passing on master (Method A — clean output expected, narrative note in handoff explaining the wrapper works on master)
- Post-PR shows all 6 integration tests passing on native async branch (load-bearing)
- All 4 seed markers present (hook enforces at commit time — handoff REJECTED if missing)
- Ruff command canonical (no `--exclude`)
- No `N/A` shortcuts on deterministic gates
- **`tox -e contracts` evidence pasted verbatim** (must show baseline 13 or explicit reason for change)
- **Canonical `bandit -r src/claude_memory -ll` output pasted** (must show only B104)
- **`**Commit:**` field present** (auto-injected by `inject_handoff_hash.py` from `<auto>` placeholder)
- **"Pre-handoff checklist" section present** with all 9 items
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If `verify_handoff_completeness.py` rejects the handoff, AG amends; do not bypass with `--no-verify`.

## Discoveries (architect-anticipated)

**Things Codex SHOULD flag if encountered:**

1. **Connection retry semantics divergence** — sync `_connect_with_retry()` uses `time.sleep()`; async equivalent must use `asyncio.sleep()`. Different retry timing in concurrent scenarios may need separate tuning.

2. **Connection pool behavior** — `redis.asyncio.Redis` connection pool may have different defaults than `redis.Redis`. Worth verifying the production load profile fits.

3. **Transaction semantics** — if any code uses `WITH` blocks for multi-statement transactions, native async may handle commit/rollback differently. Survey for transaction-shaped Cypher patterns.

4. **Error type translation** — `falkordb.asyncio` may raise different exception types than the sync client (e.g., `redis.asyncio.exceptions.ConnectionError` vs `redis.exceptions.ConnectionError`). Verify the `SearchError` wrapping in `repository_async.py` catches both.

5. **Cypher template parameter binding** — verify `await graph.query(CYPHER, params)` parameter binding matches sync `graph.query(CYPHER, params)` semantics for all data types we use (dicts, lists, None, datetime, etc.).

If any of these surface during build, AG should escalate to architect — not silently work around.

**Closing positive Discoveries (after PASS):**

- Confirm `grep -rn "asyncio.to_thread" src/claude_memory/` returns empty repo-wide post-migration (the wrapper pattern is fully eliminated)
- Confirm `tox -e contracts` baseline still 13 (Pattern 12 contribution 0)
- Note in verdict: "B10.5 closes the last deferred epic from the original Audit Remediation. Production async path now uses native FalkorDB v1.4 async client; sync MemoryRepository preserved as diagnostic. Trifecta validated on production code change (not just test hygiene)."

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "B10.5 native async migration complete. AsyncMemoryRepository uses falkordb.asyncio.FalkorDB directly; sync MemoryRepository preserved for diagnostics; cypher_queries.py canonical query layer eliminates divergence risk. All 6 integration tests pass on native async (load-bearing). Last deferred epic from Audit Remediation Round 1 is closed."
