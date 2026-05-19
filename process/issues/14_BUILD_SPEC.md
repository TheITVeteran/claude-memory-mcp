# Issue #14 — Async Warning Cleanup (Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14)
**Architect:** Claude
**Builder:** Antigravity (this is your spec)
**Auditor:** Codex (under separate `14_AUDIT_SPEC.md`)
**Director:** Tabish

Audit guidelines for Codex live in `process/issues/14_AUDIT_SPEC.md` — you don't need to read that one. Per-PR audit criteria are reproduced below as "The Bar" so you know what your work will be measured against.

**This is the first PR to use the `inject-handoff-hash` pre-commit hook from issue #15.** Write `**Commit:** <auto>` in your handoff doc's commit-hash field; the hook injects the parent HEAD hash at commit time. See `process/REMEDIATION_BUILD_SPEC.md` pre-handoff checklist item 1.

---

## Problem

The full unit suite (1,283 tests) passes but emits `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` from at least:

- `tests/unit/test_tools_coverage.py:400`
- `tests/unit/test_memory_service.py:1754`

Codex flagged these in the PR-6 audit (v1.2.1 Round 2 remediation) as out-of-scope Discoveries. Codex flagged them AGAIN in the issue #15 audit ("The existing unawaited AsyncMock warnings remain outside this issue's scope") — same warnings, same locations, still present.

**Why it matters:**

- Each warning is a latent bug surface — the mocked async path isn't being exercised the way the test author intended (the coroutine is created but never awaited, so the mock's behavior under await is untested)
- Warnings bleed signal-to-noise on the test runner; useful warnings get lost in the existing ones
- Future strict-warning CI (`-W error::RuntimeWarning`) is blocked until cleanup is done

## Solution: find, fix, gate

**Find:** broader rg than the two known sites — these are likely the tip. The PR-6 Discovery only enumerated the warnings it saw in its specific run.

**Fix:** typical pattern — replace `MagicMock()` with `AsyncMock()` where the mocked target is an async method/function. Less commonly, add explicit `await` where the test scenario expected mock coroutine resolution.

**Gate:** add `filterwarnings = ["error::RuntimeWarning"]` to pytest config so any future regression (a contributor adding `MagicMock` to mock an async method) fails the build before merge. Same regression-prevention philosophy as the contract scanner.

## Concrete fix (no inference allowed)

### Step 1 — Source-pattern audit (NOT warning-replay, NOT GC suppression)

**Important — read both warnings:**

1. **Warning attribution is GC-nondeterministic.** `RuntimeWarning: coroutine never awaited` fires at GC time, not at the test that created the unawaited coroutine. So "list which tests emit warnings" via runtime is an unsatisfiable audit criterion. Use deterministic source-pattern audit instead.
2. **DO NOT add a conftest fixture, warning filter, or any other mechanism that SUPPRESSES the warnings without fixing the underlying mocks.** Suppression masks the bug; the unawaited coroutine still exists, the mock's behavior is still untested. The strict gate's job is to SEE the warnings until they're gone for real. Suppression = audit fail.

**Source-pattern audit** is deterministic, file:line-stable, independent of runtime:

```bash
rg -n "MagicMock\(" tests/unit/ tests/lint/
```

**Classification with batching (large suite tolerated):**

If your test suite has hundreds of `MagicMock` sites (Dragon Brain has ~503), per-site classification is onerous and unnecessary. Use this hybrid approach:

- **Per-site classification for async-target candidates.** Any site where the mocked target MIGHT be async — list it explicitly with file:line, target name, async-or-sync verdict, and fix applied.
- **Batched classification for clearly-sync patterns.** Group sites by file + pattern (e.g., "test_foo.py: 42 occurrences of `MagicMock(spec=PydanticModelName)` — all sync Pydantic data class mocks, no fix needed"). Include a count.
- **Summary count + spot checks** of pure-sync sites — Codex doesn't need per-site verification of every `MagicMock` mocking a `dict` or `int`.

Format your handoff's "Source-pattern audit" section:

```markdown
## Source-pattern audit

**Total rg matches:** 503

### Async-target sites (FIXED, per-site listing)

| file:line | Target | Pre-fix | Post-fix |
|-----------|--------|---------|----------|
| `tests/unit/test_tools_coverage.py:400` | `service.search` (async) | `MagicMock(return_value=...)` | `AsyncMock(return_value=...)` |
| ... | ... | ... | ... |

### Async-target sites (UNCLEAR — escalated for re-spec)

[any sites where async-vs-sync was ambiguous, escalated per Round 5]

### Sync-target sites (batched, SKIPPED)

| File | Pattern | Count | Justification |
|------|---------|-------|---------------|
| `tests/unit/test_foo.py` | `MagicMock(spec=FooModel)` (sync Pydantic) | 42 | All instances mock sync data class |
| `tests/unit/test_bar.py` | `MagicMock()` for `int`/`str` return values | 18 | Sync return type |
| ... | ... | ... | ... |
```

Codex audits by independently running the same rg, checking the async-target table for completeness, and spot-checking 5-10 sync-target batches for correctness. Missed async-target sites = FAIL.

**Empirical verification (the canonical outcome check):**

After fixes, run:

```bash
python -m pytest tests/unit/ -W error::RuntimeWarning -v 2>&1 | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

This must return ZERO matches. If even one match appears, an async-target site was missed. Iterate.

### Step 2 — Fix each warning site

For each flagged location, the fix is typically one of:

**Pattern A — `MagicMock` mocking an async method:**

```python
# Before (emits warning when the mocked coroutine is never awaited)
mock_service = MagicMock()
mock_service.search.return_value = [...]   # search() is async, returns coroutine

# After
from unittest.mock import AsyncMock
mock_service = MagicMock()
mock_service.search = AsyncMock(return_value=[...])
```

**Pattern B — `patch()` without specifying AsyncMock:**

```python
# Before
with patch("module.async_function") as mock:
    mock.return_value = "result"

# After
with patch("module.async_function", new_callable=AsyncMock) as mock:
    mock.return_value = "result"
```

**Pattern C — Missing `await` on a real coroutine in the test body:**

```python
# Before
result = some_async_method()   # creates coroutine, never awaited

# After
result = await some_async_method()
```

Pick the right pattern per site by reading the test's intent. If unclear, escalate per Round 5 discipline.

### Step 3 — Add the strict-warning CI gate

In `pyproject.toml`, find the `[tool.pytest.ini_options]` section (or add it if absent) and ensure `filterwarnings` includes `"error::RuntimeWarning"`:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::RuntimeWarning",
    # ... preserve any existing filterwarnings entries
]
```

If the config lives in a different file (`pytest.ini`, `setup.cfg`, `tox.ini`), put it there instead — verify with `grep -r "filterwarnings" --include="*.toml" --include="*.ini" --include="*.cfg"`.

Keep any existing `filterwarnings` entries intact — they're tolerated existing exceptions.

### Step 4 — Verify zero warnings remain

```bash
python -m pytest tests/unit/ -q
# Must exit 0 with the new filterwarnings config active
```

If any test still fails under the new strict gate, that's a missed site — go back to step 2 and fix.

### Step 5 — Add subprocess verification tests

Create `tests/lint/test_async_warnings.py` (new file, new directory). This is a meta-test suite — each test runs pytest as a subprocess against the actual codebase with strict-warning enforcement, providing durable regression coverage even if the `filterwarnings` config gets accidentally regressed.

```python
"""Regression suite: verify the codebase emits no RuntimeWarnings under strict gate.

These tests run pytest as a subprocess against specific test files (or the
full suite) with `-W error::RuntimeWarning` to fail on any unawaited
coroutine or similar runtime hazard.

Slow by design (each test re-invokes pytest). Run via `tox -e lint-warnings`
or directly via `pytest tests/lint/ -q` — kept out of the main suite for speed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_pytest_strict(targets: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-W", "error::RuntimeWarning", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=900,
    )


def test_evil_full_unit_suite_no_runtime_warnings() -> None:
    """Full unit suite runs clean under -W error::RuntimeWarning."""
    result = _run_pytest_strict(["tests/unit/"])
    assert result.returncode == 0, (
        f"Unit suite emitted RuntimeWarning(s).\n"
        f"stdout (last 50 lines):\n{result.stdout[-3000:]}\n"
        f"stderr (last 20 lines):\n{result.stderr[-1500:]}"
    )


def test_evil_test_tools_coverage_no_runtime_warnings() -> None:
    """test_tools_coverage.py runs clean (PR-6 Discovery target)."""
    result = _run_pytest_strict(["tests/unit/test_tools_coverage.py"])
    assert result.returncode == 0, f"Warnings in test_tools_coverage.py:\n{result.stdout[-2000:]}"


def test_evil_test_memory_service_no_runtime_warnings() -> None:
    """test_memory_service.py runs clean (PR-6 Discovery target)."""
    result = _run_pytest_strict(["tests/unit/test_memory_service.py"])
    assert result.returncode == 0, f"Warnings in test_memory_service.py:\n{result.stdout[-2000:]}"
```

### Step 6 — Register the lint-warnings tox env

In `tox.ini` (or wherever tox envs live), add:

```ini
[testenv:lint-warnings]
description = Strict-warning regression suite (subprocess pytest under -W error::RuntimeWarning)
deps = {[testenv]deps}
commands = pytest tests/lint/ -q
```

Verify it runs: `tox -e lint-warnings`.

## Files affected

- **Modified (estimate):** several test files where MagicMock → AsyncMock substitutions happen. Exact count depends on the full pre-PR scope inventory from Step 1 — likely 3-10 test files based on the known 2 sites + typical pattern spread.
- **Modified:** `pyproject.toml` (or wherever pytest config lives) — add `filterwarnings = ["error::RuntimeWarning"]`
- **Modified:** `tox.ini` (or wherever tox envs live) — new `lint-warnings` env
- **New:** `tests/lint/__init__.py` (empty, makes the dir a package)
- **New:** `tests/lint/test_async_warnings.py` (~80 LoC)

**LoC estimate:** ~150 total (~30 production test fixes + ~100 new lint suite + ~20 config).

## Tests (3 evil + 1 sad + 1 neutral, test-first)

| Test | Category | Scenario | Pre-PR | Post-PR |
|------|----------|----------|--------|---------|
| test_evil_full_unit_suite_no_runtime_warnings | evil | `pytest tests/unit/ -W error::RuntimeWarning -q` (subprocess, in `tests/lint/`) | TEST FAILS (suite errors out on first unawaited coroutine warning) | TEST PASSES (suite clean under strict gate) |
| test_evil_test_tools_coverage_no_runtime_warnings | evil | Same subprocess pattern, targeted at `tests/unit/test_tools_coverage.py` | TEST FAILS (specific file emits AsyncMockMixin warning per PR-6 Discovery) | TEST PASSES |
| test_evil_test_memory_service_no_runtime_warnings | evil | Same subprocess pattern, targeted at `tests/unit/test_memory_service.py` | TEST FAILS (same) | TEST PASSES |
| test_sad_pytest_filterwarnings_config_present | sad | Inspect `pyproject.toml` for `filterwarnings = ["error::RuntimeWarning"]` in `[tool.pytest.ini_options]` | TEST FAILS (no such config — verify the test catches this pre-PR) | TEST PASSES (config added) |
| test_neutral_unit_suite_pass_count_unchanged | neutral | `pytest tests/unit/ -q` (without strict filter) — full suite still passes | TEST PASSES (1283 passing) | TEST PASSES (no behavioral regression — test fixes are mechanical, not semantic) |

**Test-first evidence requirement:** for the 3 evil tests + 1 sad test marked "TEST FAILS" pre-PR (4 of 5), AG MUST capture verbatim failure output against pre-PR base by running the test file against master without the new fixes. Paste in handoff under "Test-first evidence" section.

The `test_sad_pytest_filterwarnings_config_present` test should be co-located in `tests/lint/test_async_warnings.py` — add it as a fourth test alongside the three evil ones.

## The bar (Codex will verify)

- (a) `pyproject.toml` (or equivalent) has `filterwarnings = ["error::RuntimeWarning"]` in pytest config
- (b) Full unit suite runs clean under that config: `python -m pytest tests/unit/ -q` exits 0
- (c) Specific PR-6 Discovery files demonstrably clean: `pytest tests/unit/test_tools_coverage.py tests/unit/test_memory_service.py -W error::RuntimeWarning -q` exits 0
- (d) Source-pattern audit complete — every `MagicMock` call site in `tests/` classified (async target / sync target / skipped with reason); every async-target site fixed to `AsyncMock` (or equivalent); Codex's independent rg + classification matches yours
- (e) `tests/lint/test_async_warnings.py` exists with the 4 specified tests (3 evil + 1 sad); all pass against the new codebase
- (f) `tox -e lint-warnings` runs the lint suite cleanly
- (g) Test-first evidence: handoff includes verbatim pre-PR failure output for the 4 TEST FAILS rows
- (h) `tox -e contracts` post-PR — delta = 0 (no NEW contract violations; test file fixes don't affect `src/claude_memory/` count)
- (i) `mypy --strict src/claude_memory` still passes (no source layer changes)
- (j) Full unit suite still passes (no regression in count): `pytest tests/unit/ -q` shows >= 1283 passing
- (k) Pre-handoff checklist complete with real bandit evidence (don't repeat issue #15 round 1's "N/A" mistake)

## Branch + handoff conventions

- **Branch:** `issue-14/async-warning-cleanup` (create from current master HEAD `27eafd0` or later)
- **Handoff doc:** `process/PR_ISSUE_14_HANDOFF.md`
- **Use the `<auto>` placeholder for the commit hash** — the issue #15 hook will inject it. This is the first PR to USE the hook in production; proves the tooling works on a real cycle.

## Out of scope

- Do NOT modify any source code in `src/claude_memory/` — this is test-cleanup only. If a test fix reveals an actual production bug, file a NEW issue and DEFER it.
- Do NOT change the test count (preserve the existing 1,283 passing tests; mechanical fixes shouldn't add or remove tests). If a test needs to be SPLIT to fix, justify in handoff.
- Do NOT add new dependencies — `AsyncMock` is in stdlib `unittest.mock`.
- Do NOT bundle other warning-cleanup work (e.g., DeprecationWarning) — strict `error::RuntimeWarning` only, per issue #14 scope.
- **Do NOT add conftest fixtures, warning filters, GC-control mechanisms, or any other tool that SUPPRESSES the warning without fixing the underlying MagicMock-on-async sites.** Suppression masks the bug; the unawaited coroutine still exists. The audit verifies the strict gate emits ZERO warning sentinels in stdout/stderr — if you suppress, you'll either still leak warnings (criterion failure) OR pass the gate fraudulently (which Codex will catch via source-pattern audit). The only correct fix is at the source — `MagicMock` → `AsyncMock` for async targets.

## Round 5 discipline reminder

If anything in this spec is ambiguous, contradicts itself, or the picked option seems wrong: **escalate to re-spec — do not infer.** The cost of a re-spec round is small. The cost of a wrong-inference build is large.

The Step 1 scope inventory is critical — don't skip it. The PR-6 Discovery only enumerated 2 sites; the real count is likely higher. Run the strict gate first to see the actual scope before committing to fixes.
