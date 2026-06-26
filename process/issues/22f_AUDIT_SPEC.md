# Issue #22f — Audit Spec (Final Infrastructure Lockdown)

**Issue:** parent #22 — sub-chunk 22f (closing piece)
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22f_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (synthetic violation + acceptance tests)

```bash
# (1) Acceptance test suites both pass
python -m pytest tests/unit/test_contract_scanner_pattern12.py tests/unit/test_verify_handoff_completeness.py -v

# (2) Baseline holds at 13
tox -e contracts
# Expected: "Found 13 violations. Within baseline."

# (3) SYNTHETIC VIOLATION TEST — proves scanner catches future regressions
cat > tests/unit/test_22f_synthetic_violation.py << 'EOF'
"""Synthetic violation test for Pattern 12 audit verification.
This file is created and deleted within the audit; if it persists, FAIL."""
from unittest.mock import MagicMock
from claude_memory.tools import MemoryService

def test_synthetic_violation():
    svc = MemoryService(embedding_service=MagicMock())
    assert svc is not None
EOF
tox -e contracts
# Expected: FAIL with "Found 14 violations" (or similar — must be > 13)
rm tests/unit/test_22f_synthetic_violation.py
tox -e contracts
# Expected: "Found 13 violations. Within baseline." — back to clean state

# (4) SYNTHETIC HOOK TEST — proves hook rejects incomplete handoffs
cat > /tmp/PR_ISSUE_22Z_HANDOFF.md << 'EOF'
## Pre-PR baseline
seed=1 only

## Checklist
- ruff check src/claude_memory tests scripts --exclude=foo
- bandit: N/A
EOF
python scripts/hooks/verify_handoff_completeness.py /tmp/PR_ISSUE_22Z_HANDOFF.md
# Expected: exit code 1, stderr mentions missing seeds AND --exclude AND N/A
rm /tmp/PR_ISSUE_22Z_HANDOFF.md
```

**Required outcome:** all 4 steps succeed in the order specified (acceptance tests PASS, baseline holds at 13, synthetic violation fires and reverts, synthetic hook rejection works). Any deviation = **FAIL**.

## Per-criterion verification

### (a) Pattern 12 allowlist exists with correct membership AND no smuggled exemptions

**REVISED 2026-06-26 after 22f R1 audit:** AST scan surfaced 6 additional Category D files (test_analysis_radar, test_entity_lifecycle, test_graph_traversal, test_phase4, test_semantic_radar, test_session) — same lightweight-integration pattern as test_temporal/test_hologram. The canonical allowlist is now **17 entries**. The detector function MUST NOT have any additional hardcoded exemptions outside the constant (this was the 22f R1 smuggling anti-pattern Codex caught).

```bash
python -c "
from scripts.trace_contracts_dragon import PATTERN_12_ALLOWLIST
expected = {
    # The one legitimate helper
    'tests/_helpers/mock_factory.py',
    # Bare-MagicMock stubs (2)
    'tests/unit/test_router.py',
    'tests/unit/test_list_orphans.py',
    # Real-dependency tests (2)
    'tests/unit/test_locking.py',
    'tests/unit/test_dynamic_validation.py',
    # Mutant-testing factories (3)
    'tests/unit/test_mutant_dict_crud.py',
    'tests/unit/test_mutant_dict_services.py',
    'tests/unit/test_mutant_temporal.py',
    # Lightweight-integration (9)
    'tests/unit/test_temporal.py',
    'tests/unit/test_hologram.py',
    'tests/unit/test_full_workflow.py',
    'tests/unit/test_analysis_radar.py',
    'tests/unit/test_entity_lifecycle.py',
    'tests/unit/test_graph_traversal.py',
    'tests/unit/test_phase4.py',
    'tests/unit/test_semantic_radar.py',
    'tests/unit/test_session.py',
}
assert set(PATTERN_12_ALLOWLIST) == expected, \
    f'FAIL: allowlist mismatch. Missing: {expected - set(PATTERN_12_ALLOWLIST)}, Extra: {set(PATTERN_12_ALLOWLIST) - expected}'
assert len(PATTERN_12_ALLOWLIST) == 17, f'FAIL: expected 17 entries, got {len(PATTERN_12_ALLOWLIST)}'
print('PASS: PATTERN_12_ALLOWLIST has exactly 17 expected entries')
"
```

**Additional smuggling check (critical — added after 22f R1):** the detector function body must NOT contain any hardcoded file paths beyond what's in the constant. AST-scan the detector function for string literals containing `test_*.py` outside the constant reference:

```bash
python -c "
import ast
with open('scripts/trace_contracts_dragon.py') as f:
    tree = ast.parse(f.read())
detector_func = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'detect_pattern_12_hand_rolled_memory_service':
        detector_func = node
        break
assert detector_func, 'FAIL: detector function not found'

# Find all string literals in the function body
smuggled = []
for node in ast.walk(detector_func):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if '.py' in node.value and ('test_' in node.value or 'tests/' in node.value):
            smuggled.append(node.value)

if smuggled:
    print(f'FAIL: detector function contains hardcoded path exemptions outside PATTERN_12_ALLOWLIST: {smuggled}')
    print('All allowlisting MUST flow through the public constant. See 22f R1 audit verdict.')
    exit(1)
print('PASS: no smuggled exemptions in detector function — all allowlisting flows through PATTERN_12_ALLOWLIST')
"
```

### (b) Pattern 12 detector function exists with correct signature

```bash
python -c "
import inspect
from scripts.trace_contracts_dragon import detect_pattern_12_hand_rolled_memory_service
sig = inspect.signature(detect_pattern_12_hand_rolled_memory_service)
params = list(sig.parameters.keys())
assert params == ['tree', 'filepath_relative'], f'FAIL: signature mismatch, got {params}'
print('PASS: detector function signature correct')
"
```

### (c) Scanner main() walks tests/unit/ for Pattern 12

```bash
# Verify by inspection — confirm main() includes a tests/unit/ scan loop after src/.
grep -n "tests/unit\|tests_dir" scripts/trace_contracts_dragon.py
# Must show new scan logic added in main() function (typically after the existing
# src_dir.rglob loop, before the totals print).
```

### (d) Pattern 12 acceptance tests pass

```bash
python -m pytest tests/unit/test_contract_scanner_pattern12.py -v --tb=short
```

Must show ≥6 tests passing. Verify test names cover allowlist (helper exempt, Category D exempt), detection (non-allowlisted file fires, attribute access call fires, multiple inline constructions counted), and edge cases (no embedding_service kwarg doesn't fire, empty file).

### (e) Hook script exists with prescribed checks

```bash
python -c "
import ast
with open('scripts/hooks/verify_handoff_completeness.py') as f:
    tree = ast.parse(f.read())
funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
assert 'validate_handoff' in funcs, 'FAIL: validate_handoff function missing'
assert 'main' in funcs, 'FAIL: main function missing'

# Verify the 3 hardcoded checks are present (constants)
src = open('scripts/hooks/verify_handoff_completeness.py').read()
assert 'REQUIRED_SEED_MARKERS' in src, 'FAIL: REQUIRED_SEED_MARKERS constant missing'
assert 'FORBIDDEN_RUFF_FLAG' in src, 'FAIL: FORBIDDEN_RUFF_FLAG constant missing'
assert 'DETERMINISTIC_GATE_NAMES' in src, 'FAIL: DETERMINISTIC_GATE_NAMES constant missing'
print('PASS: hook script has prescribed structure')
"
```

### (f) Hook acceptance tests pass

```bash
python -m pytest tests/unit/test_verify_handoff_completeness.py -v --tb=short
```

Must show ≥6 tests passing covering happy + 3 evil (single seed, --exclude, N/A) + sad + neutral paths.

### (g) Pre-commit config registers the hook

```bash
grep -A 5 "verify-handoff-completeness" .pre-commit-config.yaml
```

Must show entry with:
- `id: verify-handoff-completeness`
- `entry: python scripts/hooks/verify_handoff_completeness.py`
- `files: ^process/PR_ISSUE_.*_HANDOFF\.md$`

### (h) Harness lockdown documentation present

```bash
# Check either CLAUDE.md or ARCHITECTURE.md for the lockdown section
grep -l "Test-suite physical enforcement\|harness lockdown\|5-layer" CLAUDE.md ARCHITECTURE.md 2>/dev/null
```

Must return at least one file. Inspect content — must include the 5-layer table mentioning:
- branch_write_guard.py
- inject_handoff_hash.py
- verify_handoff_completeness.py
- trace_contracts_dragon.py Pattern 12
- (existing scanner / baseline ratchet)

AND must list the 10 Category D allowlist files with reasons.

### (i) Scanner baseline holds at 13

Already covered in canonical pass/fail step 2.

### (j) Standard gates clean

- `python -m mypy --strict src/claude_memory` — clean
- `python -m ruff check src/claude_memory tests scripts` — **canonical**. If handoff shows `--exclude`, FAIL.
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (k) Synthetic violation test — canonical pass/fail step 3

Already covered. Must demonstrate scanner catches a new violation by failing baseline, then returns to clean state after the synthetic file is removed.

### (l) Synthetic hook rejection test — canonical pass/fail step 4

Already covered. Must demonstrate hook rejects incomplete handoff with non-zero exit AND stderr mentions all three failure types (missing seeds, --exclude, N/A).

### (m) Scope discipline

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, 7+1 files, ordering insensitive):
- `scripts/trace_contracts_dragon.py`
- `scripts/hooks/verify_handoff_completeness.py`
- `.pre-commit-config.yaml`
- `tests/unit/test_contract_scanner_pattern12.py`
- `tests/unit/test_verify_handoff_completeness.py`
- `CLAUDE.md` OR `ARCHITECTURE.md` (one or the other; if both modified, flag as Discovery)
- `process/PR_ISSUE_22F_HANDOFF.md`

Any other file = FAIL. Watch for:
- `tests/_helpers/*` — helper must remain unchanged
- `src/claude_memory/*` — denied by harness; this is infrastructure-only
- Any test file outside the 2 new acceptance test files

### (n) Pre-handoff checklist complete

Per master spec — 9 items with real evidence from a clean worktree:
- Acceptance test results for both new test files (must show ≥6 tests each, all passing)
- `tox -e contracts` output (baseline 13 holds)
- **canonical** `ruff check src/claude_memory tests scripts` output (NO `--exclude` flag)
- `mypy --strict src/claude_memory` output (clean)
- `bandit -r src/claude_memory -ll` output (only B104)
- Synthetic violation demonstration: scanner fired on temp violation, returned clean after removal
- Synthetic hook rejection demonstration: hook rejected incomplete handoff
- Two-commit topology preserved; handoff commit's `**Commit:**` field equals `git rev-parse HEAD~1`

If hook rejection demonstration is missing or unclear: FAIL — the hook's whole purpose is structural enforcement; an unverified hook is no enforcement.

## Discoveries (closing-arc verification)

After verifying all criteria, run repo-wide closing checks:

```bash
# (1) Suppression fixture sentinel — must remain at zero
grep -rn "_drain_orphan_coroutines" tests/
# Expected: empty.

# (2) Hand-rolled MemoryService construction sentinel — filtered to exclude Category D
grep -rn "MemoryService(embedding_service=" tests/unit/ | grep -vE "test_dynamic_validation|test_full_workflow|test_mutant_dict_crud|test_mutant_dict_services|test_mutant_temporal|test_temporal|test_router|test_list_orphans|test_locking|test_hologram"
# Expected: empty.

# (3) Pattern 12 baseline contribution — must be 0
python scripts/trace_contracts_dragon.py 2>&1 | grep "Pattern 12"
# Expected: either no "Pattern 12" line (no violations), or "Pattern 12: 0".
```

If all three return clean, note closing positive Discovery:

> "Issue #22 arc closed. Bug class (wrong-type async mocks, suppression sneak-arounds, hand-rolled MemoryService construction) structurally eliminated outside the 10 Category D allowlist files. Five layers of physical enforcement (branch_write_guard, inject_handoff_hash, verify_handoff_completeness, scanner Pattern 12, existing baseline ratchet) prevent reintroduction without explicit intent."

## Output format

Standard. Lead with verdict. If PASS, explicitly note the arc closing: "Issue #22 arc complete. The 14a-22f sequence eliminated the bug class from the test suite and locked the door behind it. No further per-file migrations or infrastructure work in the #22 family is anticipated."
