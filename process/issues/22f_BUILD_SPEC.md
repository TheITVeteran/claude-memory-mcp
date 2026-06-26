# Issue #22f — Final Infrastructure Lockdown (Build Spec)

**Issue:** parent #22 — sub-chunk 22f (closing piece of the arc).
**Branch:** `issue-22f/scanner-and-hook-lockdown` (from current master HEAD)
**Pattern:** Infrastructure work — no test fixture migrations. Three distinct deliverables, each independently verifiable.

---

## Target

Close the door behind us. The 14a-22e-bis arc structurally eliminated the bug class across the test suite. 22f puts physical guards in place so it can never reopen:

1. **Scanner Pattern 12** detects any future hand-rolled `MemoryService(embedding_service=...)` construction outside the helper + outside the 10 allowlisted Category D files. **Baseline = 0** (the arc closed this gap; any reintroduction fails CI).
2. **`verify_handoff_completeness.py` pre-commit hook** physically enforces handoff hygiene — the structural fix for the 7-PR (j) drift pattern that no amount of spec hardening closed via verbal discipline. Mirrors `inject_handoff_hash.py` / `branch_write_guard.py`.
3. **Harness lockdown documentation** captures the 5-layer physical enforcement state in `CLAUDE.md` (or `ARCHITECTURE.md`, AG's call) so future maintainers understand the structural guarantees.

**Scope:** infrastructure files only. NO test file changes (the 22a-22e-bis arc is the migration; 22f is the lockdown).

## Files in scope

- **Modify:** `scripts/trace_contracts_dragon.py` (add Pattern 12 + tests/unit/ scan)
- **New:** `scripts/hooks/verify_handoff_completeness.py`
- **Modify:** `.pre-commit-config.yaml` (register the new hook)
- **New:** `tests/unit/test_contract_scanner_pattern12.py` (acceptance tests for Pattern 12)
- **New:** `tests/unit/test_verify_handoff_completeness.py` (acceptance tests for the hook)
- **Modify:** `CLAUDE.md` (or `ARCHITECTURE.md`) — add harness lockdown section
- **New:** `process/PR_ISSUE_22F_HANDOFF.md`

Seven-file diff. Larger than per-file migrations, but each file is small and focused.

## Deliverable 1: Scanner Pattern 12

### Detection logic

Add to `scripts/trace_contracts_dragon.py`. Pattern 12 detects `MemoryService` construction calls in test files outside the allowlist.

**Allowlist (hardcoded in the scanner):**

```python
# In scripts/trace_contracts_dragon.py, near ALLOWLIST_MARKERS:
PATTERN_12_ALLOWLIST = frozenset({
    # Legitimate helper — the ONE place hand-rolled construction lives
    "tests/_helpers/mock_factory.py",
    # Category D files (architect-verified intentional patterns; helper would break them)
    "tests/unit/test_router.py",
    "tests/unit/test_list_orphans.py",
    "tests/unit/test_locking.py",         # uses real LockManager
    "tests/unit/test_hologram.py",        # lightweight integration
    "tests/unit/test_dynamic_validation.py",  # uses real OntologyManager
    "tests/unit/test_full_workflow.py",   # integration-ish
    "tests/unit/test_mutant_dict_crud.py",    # mutant-testing factory
    "tests/unit/test_mutant_dict_services.py",  # mutant-testing factory
    "tests/unit/test_mutant_temporal.py",  # mutant-testing factory
    "tests/unit/test_temporal.py",        # lightweight integration
})
```

**Pattern 12 detector function (add as new function in the scanner):**

```python
def detect_pattern_12_hand_rolled_memory_service(tree, filepath_relative):
    """Pattern 12: Hand-rolled MemoryService construction outside helper/allowlist.

    The 22a-22e-bis arc structurally eliminated hand-rolled MemoryService(...)
    in test files; future violations should fail CI. Allowlist contains the
    helper + 10 architect-verified Category D files with intentional patterns.

    Detects: `MemoryService(embedding_service=...)` ast.Call nodes anywhere
    in non-allowlisted files under tests/.

    Returns: list of (lineno, func, "MemoryService(...)", "hand-rolled construction",
             "Pattern 12: Hand-rolled MemoryService") tuples, or [] if file is
    allowlisted or no violations.
    """
    if filepath_relative in PATTERN_12_ALLOWLIST:
        return []

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match either `MemoryService(...)` or `module.MemoryService(...)`
        func = node.func
        is_memory_service_call = (
            (isinstance(func, ast.Name) and func.id == "MemoryService")
            or (isinstance(func, ast.Attribute) and func.attr == "MemoryService")
        )
        if not is_memory_service_call:
            continue
        # Must have embedding_service kwarg (filter out unrelated MemoryService-named symbols)
        has_embedding_service_kwarg = any(
            kw.arg == "embedding_service" for kw in node.keywords
        )
        if not has_embedding_service_kwarg:
            continue
        violations.append(
            (
                node.lineno,
                "<module>",  # could be refined with parent function lookup
                "MemoryService(embedding_service=...)",
                "hand-rolled construction outside helper/allowlist",
                "Pattern 12: Hand-rolled MemoryService",
            )
        )
    return violations
```

### Wire into `main()`

Currently `main()` only scans `src/claude_memory`. Pattern 12 needs to scan `tests/unit/`. Modify the scan loop:

```python
# After the existing src/ scan, add tests/unit/ scan for Pattern 12
tests_dir = Path("tests/unit")
if tests_dir.exists():
    for py_file in sorted(tests_dir.rglob("test_*.py")):
        total_files += 1
        rel_path_str = str(py_file).replace("\\", "/")  # normalize for allowlist match
        with open(py_file, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except Exception:
                continue
        violations = detect_pattern_12_hand_rolled_memory_service(tree, rel_path_str)
        if violations:
            rel_path = py_file.relative_to(Path.cwd()) if py_file.is_absolute() else py_file
            for lineno, func, exc_type, ret_val, vtype in violations:
                out.write(
                    f"| `{rel_path}` | {lineno} | `{func}()` | `{exc_type}` | `{ret_val}` | {vtype} |\n"
                )
                total_violations += 1
                by_category[vtype] = by_category.get(vtype, 0) + 1
```

### Baseline contract

The existing tox -e contracts baseline is 13 (from the src/ scan). Pattern 12 introduces a NEW baseline of 0 for the test-suite scan. Two options for combining:

- **(a) Keep a single baseline of 13** — Pattern 12 contributes 0, so the total stays at 13. Any Pattern 12 violation bumps total to 14, failing the gate.
- **(b) Separate sub-baselines** — scanner reports `src: 13/13, tests: 0/0` separately. More legible but requires refactoring main()'s baseline check.

**Use option (a).** Simpler, matches existing pattern. Pattern 12 contributes 0 violations on master after 22e-bis; any new violation appears as `14 > 13` and fails the gate.

### Acceptance tests for Pattern 12

`tests/unit/test_contract_scanner_pattern12.py`:

```python
"""Acceptance tests for Pattern 12 (hand-rolled MemoryService detection).

Per process/issues/22f_BUILD_SPEC.md.
"""
import ast
from textwrap import dedent

from scripts.trace_contracts_dragon import (
    PATTERN_12_ALLOWLIST,
    detect_pattern_12_hand_rolled_memory_service,
)


# ─── Allowlist tests ───────────────────────────────────────────────────


def test_evil_allowlist_helper_exempt() -> None:
    """The helper at tests/_helpers/mock_factory.py is allowlisted — must not fire."""
    source = dedent("""
        from claude_memory.tools import MemoryService
        svc = MemoryService(embedding_service=embedder)
    """)
    tree = ast.parse(source)
    violations = detect_pattern_12_hand_rolled_memory_service(tree, "tests/_helpers/mock_factory.py")
    assert violations == []


def test_evil_allowlist_category_d_exempt() -> None:
    """All 10 Category D files are allowlisted — none should fire."""
    source = dedent("""
        from claude_memory.tools import MemoryService
        svc = MemoryService(embedding_service=embedder, vector_store=vs)
    """)
    tree = ast.parse(source)
    category_d_files = [f for f in PATTERN_12_ALLOWLIST if f != "tests/_helpers/mock_factory.py"]
    assert len(category_d_files) == 10, "Expected 10 Category D files in allowlist"
    for filepath in category_d_files:
        violations = detect_pattern_12_hand_rolled_memory_service(tree, filepath)
        assert violations == [], f"FAIL: Category D file {filepath} fired Pattern 12"


# ─── Detection tests ────────────────────────────────────────────────────


def test_evil_detects_hand_rolled_in_non_allowlisted_file() -> None:
    """A non-allowlisted file with hand-rolled construction must fire Pattern 12."""
    source = dedent("""
        from claude_memory.tools import MemoryService
        svc = MemoryService(embedding_service=embedder)
    """)
    tree = ast.parse(source)
    violations = detect_pattern_12_hand_rolled_memory_service(
        tree, "tests/unit/test_some_new_file.py"
    )
    assert len(violations) == 1
    assert "Pattern 12" in violations[0][4]


def test_evil_detects_attribute_access_call() -> None:
    """`tools.MemoryService(...)` (Attribute access) also fires."""
    source = dedent("""
        from claude_memory import tools
        svc = tools.MemoryService(embedding_service=embedder)
    """)
    tree = ast.parse(source)
    violations = detect_pattern_12_hand_rolled_memory_service(
        tree, "tests/unit/test_some_new_file.py"
    )
    assert len(violations) == 1


def test_evil_detects_multiple_inline_constructions() -> None:
    """File with N inline constructions emits N violations (test_batch5-style regression)."""
    source = dedent("""
        from claude_memory.tools import MemoryService

        async def test_one():
            svc = MemoryService(embedding_service=MagicMock())

        async def test_two():
            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())

        async def test_three():
            svc = MemoryService(embedding_service=mock)
    """)
    tree = ast.parse(source)
    violations = detect_pattern_12_hand_rolled_memory_service(
        tree, "tests/unit/test_regression.py"
    )
    assert len(violations) == 3


# ─── Sad-path / neutral tests ──────────────────────────────────────────


def test_sad_no_embedding_service_kwarg_does_not_fire() -> None:
    """A `MemoryService(...)` call WITHOUT `embedding_service=` kwarg doesn't fire.

    Defensive filter against false positives on unrelated MemoryService-named
    symbols or alternative call signatures.
    """
    source = dedent("""
        class MemoryService:
            pass

        svc = MemoryService()  # no embedding_service kwarg
    """)
    tree = ast.parse(source)
    violations = detect_pattern_12_hand_rolled_memory_service(
        tree, "tests/unit/test_unrelated.py"
    )
    assert violations == []


def test_neutral_empty_file_no_violations() -> None:
    """Empty file emits no violations."""
    tree = ast.parse("")
    violations = detect_pattern_12_hand_rolled_memory_service(
        tree, "tests/unit/test_empty.py"
    )
    assert violations == []
```

## Deliverable 2: `verify_handoff_completeness.py` pre-commit hook

### Purpose

Physically enforce handoff hygiene at commit time. The 22a-22e-bis arc had 7 (j) checklist drift PRs — verbal discipline + spec hardening didn't close the gap. A pre-commit hook that REJECTS incomplete handoffs is the structural fix.

### Hook prescription

`scripts/hooks/verify_handoff_completeness.py`:

```python
#!/usr/bin/env python3
"""Pre-commit hook: verify_handoff_completeness.

Validates that any process/PR_ISSUE_*_HANDOFF.md file being committed contains:
  1. All 4 seed markers (seed=1, seed=2, seed=3, seed=4) at least once each
     — protects against the single-seed pre-PR baseline drift pattern (22c/22d/22e R1)
  2. The canonical ruff command (no `--exclude` substring)
     — protects against the dirty-worktree ruff hygiene gap (22a/22b R1)
  3. No `N/A` text in checklist items for deterministic gates (contracts/ruff/bandit/mypy)
     — protects against `N/A` shortcuts on required evidence

Exits 1 with a clear error message if any handoff fails validation.
Exits 0 if no handoff files in commit OR all handoffs pass.

Per process/issues/22f_BUILD_SPEC.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED_SEED_MARKERS = ("seed=1", "seed=2", "seed=3", "seed=4")
FORBIDDEN_RUFF_FLAG = "--exclude"
DETERMINISTIC_GATE_NAMES = ("contracts", "ruff", "bandit", "mypy")
NA_PATTERN = re.compile(r"\bN/A\b", re.IGNORECASE)


def validate_handoff(path: Path) -> list[str]:
    """Validate a single handoff file. Returns list of failure messages (empty if PASS)."""
    failures: list[str] = []
    content = path.read_text(encoding="utf-8")

    # Check 1: all 4 seed markers present
    for marker in REQUIRED_SEED_MARKERS:
        if marker not in content:
            failures.append(
                f"{path}: missing required seed marker '{marker}' — "
                f"multi-seed baseline must show all 4 seed outputs (see 22d/22e R1 lessons)"
            )

    # Check 2: ruff command is canonical (no --exclude substring on a ruff line)
    for lineno, line in enumerate(content.splitlines(), start=1):
        if "ruff check" in line and FORBIDDEN_RUFF_FLAG in line:
            failures.append(
                f"{path}:{lineno}: ruff command uses '{FORBIDDEN_RUFF_FLAG}' flag — "
                f"canonical command is `python -m ruff check src/claude_memory tests scripts` "
                f"with no flags (see 22a/22b R1 lessons)"
            )

    # Check 3: no N/A on deterministic-gate sections
    # Heuristic: find sections referencing each gate name and check for N/A within
    # a small window (next 8 lines after the gate-name mention).
    lines = content.splitlines()
    for lineno, line in enumerate(lines):
        for gate in DETERMINISTIC_GATE_NAMES:
            if gate in line.lower():
                window = "\n".join(lines[lineno : lineno + 8])
                if NA_PATTERN.search(window):
                    failures.append(
                        f"{path}:{lineno + 1}: N/A shortcut on deterministic gate '{gate}' "
                        f"section — gates must have real evidence pasted, not N/A"
                    )
                    break  # one report per (line, gate) is enough

    return failures


def main(argv: list[str]) -> int:
    handoff_files = [Path(p) for p in argv if "PR_ISSUE_" in p and p.endswith("_HANDOFF.md")]
    if not handoff_files:
        return 0  # No handoffs in this commit — nothing to validate

    all_failures: list[str] = []
    for path in handoff_files:
        if not path.exists():
            continue  # File deleted in this commit — skip
        all_failures.extend(validate_handoff(path))

    if all_failures:
        print("=" * 70, file=sys.stderr)
        print("HANDOFF COMPLETENESS CHECK FAILED:", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for msg in all_failures:
            print(f"  • {msg}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(
            "Fix the handoff document(s) and re-commit. The 22a-22e-bis arc had 7 PRs "
            "fail checklist hygiene; this hook prevents an 8th.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

### `.pre-commit-config.yaml` registration

Add a new local hook entry (mirror the existing `inject-handoff-hash` / `branch-write-guard` style):

```yaml
  - id: verify-handoff-completeness
    name: Verify handoff PR documents have complete checklist evidence
    entry: python scripts/hooks/verify_handoff_completeness.py
    language: system
    files: ^process/PR_ISSUE_.*_HANDOFF\.md$
    stages: [pre-commit]
```

### Acceptance tests for the hook

`tests/unit/test_verify_handoff_completeness.py`:

```python
"""Acceptance tests for verify_handoff_completeness pre-commit hook.

Per process/issues/22f_BUILD_SPEC.md.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


HOOK_SCRIPT = Path("scripts/hooks/verify_handoff_completeness.py")


def _run_hook(handoff_path: Path) -> tuple[int, str]:
    """Run the hook against the given handoff path; return (exit_code, stderr)."""
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT), str(handoff_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stderr


def _write_handoff(tmp_path: Path, content: str) -> Path:
    """Write a handoff file with the given content; return its path."""
    handoff = tmp_path / "PR_ISSUE_TEST_HANDOFF.md"
    handoff.write_text(content, encoding="utf-8")
    return handoff


# ─── Happy path ──────────────────────────────────────────────────────


def test_happy_complete_handoff_passes(tmp_path: Path) -> None:
    """A complete handoff with all 4 seeds, canonical ruff, no N/A passes."""
    content = dedent("""
        # Test Handoff

        ## Pre-PR baseline
        seed=1 ...
        seed=2 ...
        seed=3 ...
        seed=4 ...

        ## Checklist
        - tox -e contracts: SUCCESS, 13/13
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, _ = _run_hook(handoff)
    assert code == 0


# ─── Evil paths ──────────────────────────────────────────────────────


def test_evil_single_seed_fails(tmp_path: Path) -> None:
    """Pre-PR baseline showing only seed=1 fails."""
    content = dedent("""
        ## Pre-PR baseline
        seed=1 ...

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "seed=2" in stderr or "seed=3" in stderr or "seed=4" in stderr


def test_evil_exclude_flag_on_ruff_fails(tmp_path: Path) -> None:
    """A ruff command with --exclude fails."""
    content = dedent("""
        seed=1 seed=2 seed=3 seed=4

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts --exclude=tests/lint/_*.py: passed
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "--exclude" in stderr


def test_evil_na_shortcut_on_bandit_fails(tmp_path: Path) -> None:
    """N/A in a bandit section fails."""
    content = dedent("""
        seed=1 seed=2 seed=3 seed=4

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: N/A — no security checks needed
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "N/A" in stderr


# ─── Sad / neutral paths ─────────────────────────────────────────────


def test_sad_non_handoff_file_skipped(tmp_path: Path) -> None:
    """Non-handoff files passed as args are ignored — hook exits 0."""
    other = tmp_path / "some_other.md"
    other.write_text("any content", encoding="utf-8")
    code, _ = _run_hook(other)
    assert code == 0


def test_neutral_no_handoffs_in_commit(tmp_path: Path) -> None:
    """No handoff args at all — hook exits 0."""
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
```

## Deliverable 3: Harness lockdown documentation

Add a new section to `CLAUDE.md` (preferred) or `ARCHITECTURE.md` (AG's call based on which is more discoverable for maintainers). Title it **"Test-suite physical enforcement (post-22 lockdown)"** or similar.

Content prescription:

```markdown
## Test-suite physical enforcement (post-22 lockdown)

After the 14a-22f arc, five layers of physical enforcement guard the test-suite's
type-correct mock pattern. Each layer is independently active; together they make
the 14-era bug class (wrong-type mocks, suppression sneak-arounds, hand-rolled
construction) structurally impossible to reintroduce without explicit intent.

| Layer | Mechanism | Catches |
|-------|-----------|---------|
| 1. `branch_write_guard.py` | Pre-commit hook reads `process/issues/N_HARNESS.toml` per-issue denylists | Architect spec edits on builder branches; conftest sneak-arounds; src/ scope creep on test-only PRs |
| 2. `inject_handoff_hash.py` | Pre-commit hook auto-injects implementation Commit A's hash into handoff doc's `**Commit:** <auto>` placeholder | Hand-edited hashes; stale or fabricated commit references in handoffs |
| 3. `verify_handoff_completeness.py` | Pre-commit hook validates handoff files for 4-seed baseline, canonical ruff command, no N/A shortcuts on deterministic gates | Single-seed pre-PR baseline drift (22c/22d/22e R1); `--exclude` flag on ruff (22a/22b R1); N/A shortcuts |
| 4. `trace_contracts_dragon.py` Pattern 12 | AST scanner flags hand-rolled `MemoryService(embedding_service=...)` outside helper + 10 Category D allowlist | Reintroduction of the bug class via new test files or migrations bypassing `make_mock_service()` |
| 5. Existing scanner Patterns 1-11 | Baseline 13 (ratcheting toward zero quarterly) | Original audit-remediation contract violations |

The 10 Category D allowlist files (intentional patterns where helper would
change semantics): test_router, test_list_orphans, test_locking (real
LockManager), test_hologram (lightweight integration), test_dynamic_validation
(real OntologyManager), test_full_workflow (integration-ish), test_mutant_dict_crud,
test_mutant_dict_services, test_mutant_temporal (mutant-testing factories),
test_temporal (lightweight integration).

Adding a new test file? Use `make_mock_service()` from `tests/_helpers/mock_factory.py`.
Adding a new file that genuinely needs hand-rolled construction? Add the path to
`PATTERN_12_ALLOWLIST` in `scripts/trace_contracts_dragon.py` AND document why in
the comment (real-dep usage, mutant testing, integration shape).
```

## Verification

### Acceptance tests run

```bash
git worktree add ../22f-evidence issue-22f/scanner-and-hook-lockdown
cd ../22f-evidence

# (1) Pattern 12 acceptance tests
python -m pytest tests/unit/test_contract_scanner_pattern12.py -v

# (2) Hook acceptance tests
python -m pytest tests/unit/test_verify_handoff_completeness.py -v

# (3) Scanner baseline check — must remain 13 (Pattern 12 contributes 0 post-arc)
tox -e contracts
# Expected: Scanned N files. Found 13 violations. Within baseline.

# (4) Scanner Pattern 12 specifically — verify allowlist works
# (Already covered by acceptance tests, but a manual cross-check)
python scripts/trace_contracts_dragon.py
# Check the generated contract_violations_report.md: no Pattern 12 entries should appear
# (Or all Pattern 12 entries should reference NON-allowlisted files that genuinely violate)

# (5) Hook behavior verification — synthetic incomplete handoff fails
echo "## Pre-PR
seed=1 only

## Checklist
- ruff check src/claude_memory tests scripts --exclude=foo
- bandit: N/A" > /tmp/PR_ISSUE_TEST_HANDOFF.md
python scripts/hooks/verify_handoff_completeness.py /tmp/PR_ISSUE_TEST_HANDOFF.md
# Expected: exit 1 with messages about missing seeds, --exclude, and N/A
rm /tmp/PR_ISSUE_TEST_HANDOFF.md

# (6) Standard gates
python -m mypy --strict src/claude_memory
python -m ruff check src/claude_memory tests scripts          # canonical, no --exclude
python -m bandit -r src/claude_memory -ll

cd - && git worktree remove ../22f-evidence
```

## The bar (Codex will verify)

- (a) `scripts/trace_contracts_dragon.py` has `PATTERN_12_ALLOWLIST` constant with exactly 11 entries (helper + 10 Category D files)
- (b) `scripts/trace_contracts_dragon.py` has `detect_pattern_12_hand_rolled_memory_service()` function with the prescribed signature
- (c) Scanner `main()` wires Pattern 12 into the scan loop (also walks `tests/unit/`)
- (d) `tests/unit/test_contract_scanner_pattern12.py` exists with ≥6 acceptance tests covering allowlist + detection + edge cases
- (e) `scripts/hooks/verify_handoff_completeness.py` exists with the prescribed validation logic
- (f) `tests/unit/test_verify_handoff_completeness.py` exists with ≥6 acceptance tests covering happy + 3 evil + sad + neutral paths
- (g) `.pre-commit-config.yaml` registers `verify-handoff-completeness` hook with `files: ^process/PR_ISSUE_.*_HANDOFF\.md$` filter
- (h) `CLAUDE.md` (or `ARCHITECTURE.md`) has the harness lockdown section with the 5-layer table
- (i) `tox -e contracts` baseline stays at 13 (Pattern 12 contributes 0 violations post-22e-bis)
- (j) All acceptance tests pass; mypy clean; ruff canonical; bandit only B104
- (k) **Synthetic violation test (Codex-verified):** Codex creates a temporary file `tests/unit/test_22f_synthetic_violation.py` containing `MemoryService(embedding_service=mock)`, runs `tox -e contracts`, confirms it FAILS with "14 > 13", removes the temp file, confirms baseline returns to 13. This proves the scanner catches future violations.
- (l) **Synthetic hook test (Codex-verified):** Codex creates a temporary incomplete handoff `process/PR_ISSUE_22Z_HANDOFF.md` with only seed=1, runs the hook, confirms it FAILS. Removes temp file.
- (m) Scope discipline: only the 7 files listed in "Files in scope" + handoff in the diff
- (n) Pre-handoff checklist complete (9 items) with real evidence from a clean worktree

## Out of scope (do NOT do in this PR)

- Do NOT migrate any test file (all per-file migrations completed in 22a-22e-bis)
- Do NOT modify any test file outside the 2 new acceptance test files
- Do NOT modify `tests/_helpers/mock_factory.py`
- Do NOT modify any `process/*_SPEC.md` (except creating the 22f handoff)
- Do NOT modify `src/claude_memory/*`
- Do NOT add additional Pattern 13+ to the scanner — Pattern 12 is the only addition

## Round 5 discipline

If Pattern 12 fires unexpectedly on a non-allowlisted file during baseline verification, that's signal — investigate before adding to allowlist. The file might be a legitimate new addition that needs migration, OR an architectural pattern I missed in the 22e-bis investigation.

If the hook rejects a handoff that AG believes is complete, AG should NOT bypass the hook with `--no-verify`. Either fix the handoff to satisfy the check (paste missing seeds, swap ruff command, replace N/A with real evidence) OR escalate if the hook has a false positive.

## Hygiene (the final round)

Run all evidence commands in a single fresh worktree. After 22f merges, the hook does this enforcement automatically for all future PRs — but for 22f itself, manual discipline. Push with `--force-with-lease`.
