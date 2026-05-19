# Issue #14 — Async Warning Cleanup (Audit Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14)
**Architect:** Claude (defines audit criteria)
**Auditor:** ChatGPT Codex 5.5 (this is your spec)
**Builder:** Antigravity (under separate `14_BUILD_SPEC.md` — you do not see their implementation recipe)
**Director:** Tabish

This is the audit-side document. The build spec lives in `process/issues/14_BUILD_SPEC.md` — **you do not need to read it.** Auditing recipes biases verification toward checkbox-following instead of outcome-achievement. **Audit outcomes, not recipes.**

The master `process/REMEDIATION_AUDIT_SPEC.md` defines the general audit protocol (trigger, scope, handoff doc semantics, pre-handoff checklist verification, test-first verification, Discoveries section). This document narrows the per-issue criteria.

---

## What You're Auditing

A cleanup PR that eliminates `RuntimeWarning: coroutine never awaited` from the unit test suite by:

1. Fixing each occurrence (typically `MagicMock` → `AsyncMock` where the mocked target is an async method)
2. Adding `filterwarnings = ["error::RuntimeWarning"]` to pytest config so future regressions fail the build
3. Adding a subprocess-based lint test suite at `tests/lint/test_async_warnings.py` for durable regression coverage

**Background context (relevant for outcome verification, not for recipe-following):**

You flagged these warnings in the PR-6 audit (v1.2.1 Round 2 remediation) and again in the issue #15 audit. They originate from `unittest.mock.AsyncMockMixin._execute_mock_call` producing coroutines that the test code never awaits — typically because the test uses `MagicMock()` to mock an async method. The known sites in the PR-6 Discovery were `tests/unit/test_tools_coverage.py:400` and `tests/unit/test_memory_service.py:1754`, but the real scope is likely broader.

This is the **first PR to use the `inject-handoff-hash` pre-commit hook from issue #15.** AG writes `**Commit:** <auto>` in the handoff and the hook injects the implementation commit hash. Verify the hash in the handoff matches the parent commit of the handoff's own commit (= the implementation commit being audited).

---

## Audit Trigger

Standard per master spec: fires when AG creates `process/PR_ISSUE_14_HANDOFF.md` at the repo root AND pushes the branch `issue-14/async-warning-cleanup`. Director invokes with branch ref + handoff doc + this audit spec.

---

## Per-Issue Criteria

Verify each criterion against ground truth. No "looks fine" — paste evidence (file:line, command output, test output).

### (a) `filterwarnings` config installed

Verify pytest config (in `pyproject.toml` `[tool.pytest.ini_options]` OR `pytest.ini` OR equivalent) contains `"error::RuntimeWarning"` in the `filterwarnings` list. Locate via:

```bash
grep -r "filterwarnings" --include="*.toml" --include="*.ini" --include="*.cfg"
```

Pass if the entry is present in active pytest config. Fail if it's anywhere AG could claim "looks added" but isn't actually loaded by pytest (e.g., in a comment or wrong section).

### (b) Full unit suite runs clean under strict gate

Run directly:

```bash
python -m pytest tests/unit/ -q --tb=line
```

With the new config active, pytest should pick up the `filterwarnings = ["error::RuntimeWarning"]` automatically. Expected: exit 0, no error escalations from RuntimeWarnings, pass count >= 1283.

Cross-check by running explicitly without the config override:

```bash
python -m pytest tests/unit/ -W error::RuntimeWarning -q --tb=line
```

Both should be green. If they differ, the config isn't actually being picked up.

### (c) PR-6 Discovery target files demonstrably clean

Run each individually under strict gate:

```bash
python -m pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -q
python -m pytest tests/unit/test_memory_service.py -W error::RuntimeWarning -q
```

Both must exit 0. These were the named PR-6 sites — if they still emit warnings, the fix is incomplete.

### (d) Source-pattern audit (NOT warning-replay, with suppression check)

**Important:** Runtime warning attribution is nondeterministic — `RuntimeWarning: coroutine never awaited` fires at GC time. **Do not require AG's site list to match your replay's site list.** Verify via source pattern + suppression-absence + empirical strict-gate cleanliness.

**Three independent checks for this criterion:**

**(d.1) Source-pattern audit completeness — per-site for async, batched for sync.**

The handoff's "Source-pattern audit" section must include:
- **Per-site classification** of every async-target candidate (with file:line, target, async-or-sync verdict, fix applied)
- **Batched classification** of sync-target sites (acceptable to group by file + pattern with counts and justification)
- **Total rg match count** that matches your independent `rg -n "MagicMock\(" tests/unit/ tests/lint/` count

Verification:
- Run the rg yourself. Note the total count.
- Verify AG's total matches yours.
- For the async-target list, spot-check 3-5 entries by reading the source — does the mocked target's actual definition match AG's async-or-sync verdict?
- For the sync-target batches, spot-check 3-5 random sites — are they actually sync?

Pass if total matches AND spot-checks confirm classifications. Fail with specifics if AG's count diverges or spot-check finds misclassification.

**(d.2) No GC-suppression / warning-filter masking.**

Suppression of the warning is a forbidden anti-pattern (per the build spec's Out of Scope section). Verify AG didn't smuggle in a suppression mechanism:

```bash
# Check conftest.py for warning-suppression fixtures
rg -n "filterwarnings|simplefilter|RuntimeWarning|catch_warnings|warnings\.simplefilter" tests/unit/conftest.py tests/conftest.py 2>/dev/null

# Check for autouse fixtures involving gc.collect or warning handling
rg -n "autouse=True" tests/unit/conftest.py tests/conftest.py 2>/dev/null
```

If a fixture suppresses, filters, or otherwise hides `RuntimeWarning` without fixing the underlying mock, mark as FAIL with "Forbidden suppression mechanism at [file:line]." The fix must be at source level (MagicMock → AsyncMock), not at runtime suppression.

The `filterwarnings = ["error::RuntimeWarning"]` config in `pyproject.toml` is NOT a suppression mechanism — it's the strict-gate config that escalates warnings to errors. That stays. Suppression means catching/ignoring/hiding the warning.

**(d.3) Strict-gate empirical cleanliness.**

Run the strict-gate suite and scan for sentinel strings:

```bash
python -m pytest tests/unit/ -W error::RuntimeWarning -v 2>&1 \
    | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

This MUST return zero matches. If any line matches, AG didn't fix all sites — mark as FAIL with the matched line(s) as evidence.

**All three sub-checks (d.1, d.2, d.3) must pass for criterion (d) to pass.**

### (e) Lint suite exists with required tests

`tests/lint/test_async_warnings.py` exists and contains:

- `test_evil_full_unit_suite_no_runtime_warnings`
- `test_evil_test_tools_coverage_no_runtime_warnings`
- `test_evil_test_memory_service_no_runtime_warnings`
- `test_sad_pytest_filterwarnings_config_present`

All 4 pass against the new codebase:

```bash
python -m pytest tests/lint/test_async_warnings.py -q
```

Expected: 4 passed.

### (f) Tox env registered

`tox.ini` (or equivalent) has a `[testenv:lint-warnings]` section. Run it:

```bash
tox -e lint-warnings
```

Expected: exit 0.

### (g) Test-first evidence for the 4 TEST FAILS rows

Per master AUDIT_SPEC step 9 — for tests marked "TEST FAILS" pre-PR:

The handoff doc MUST include verbatim first-run failure output for `test_evil_full_unit_suite_no_runtime_warnings`, `test_evil_test_tools_coverage_no_runtime_warnings`, `test_evil_test_memory_service_no_runtime_warnings`, and `test_sad_pytest_filterwarnings_config_present` — captured against the pre-PR base.

Independently verify by checking out the pre-PR commit in a worktree, copying the new `tests/lint/` directory in, and running the 4 tests. They should fail (the 3 evil ones with RuntimeWarning escalations, the sad one because the config isn't there yet).

### (h) Deterministic gates unchanged

- `tox -e contracts` post-PR shows delta = 0 (new files are in `tests/lint/`, outside `src/claude_memory/`)
- `python -m mypy --strict src/claude_memory` still passes (no source layer changes; this PR is test-only)
- `python -m ruff check src/claude_memory tests scripts` passes
- Bandit shows only the accepted `embedding_server.py:148` bind-all
- Pre-handoff checklist item 6 (bandit) has REAL evidence pasted, not "N/A" (per the issue #15 round 1 lesson)

### (i) No source code changes

Spec is strict: this is test-cleanup only. Verify `git diff --name-only master..HEAD` includes no files under `src/claude_memory/`. If any source file changed, that's scope creep — flag with detail (which files, what changed).

### (j) Hash injection hook worked correctly

This is the first PR using the issue #15 hook. Verify:

- Handoff doc's `**Commit:**` field contains a real hash (not the literal `<auto>` placeholder)
- That hash equals `git rev-parse HEAD~1` from the handoff's own commit (= the parent / implementation commit being audited)

If the hash matches `git rev-parse HEAD` (the handoff's own commit), the hook didn't fire or AG manually edited — flag as Discovery about the hook's first production usage.

---

## Audit Protocol Summary

Standard per master spec:

1. Run deterministic tools first (`tox -e contracts`, `mypy --strict`, `bandit`, `ruff`, `pytest tests/unit/`, `pytest tests/lint/`)
2. Run the per-criterion verifications (a) through (j) above
3. Verify pre-handoff checklist completeness in the handoff doc (master spec step 8)
4. Verify test-first evidence for the 4 TEST FAILS rows (master spec step 9)
5. Verify the hash-injection hook worked (criterion (j) above — first production usage)
6. Flag any Discoveries outside this spec's scope

---

## Constraints (Codex Must NOT)

- Audit aspects outside this issue's scope (this is test cleanup, not feature work; ignore unrelated tooling)
- Audit recipe-following (you don't see the build spec; verify the OUTCOMES described above)
- Accept "N/A" for any pre-handoff checklist item where the master spec requires actual evidence
- Mark the hash-injection result as a primary criterion failure if it merely indicates the new hook needs adjustment — flag as Discovery instead unless it actively breaks the audit

---

## Output Format

Standard per master spec:

```markdown
# Issue #14 Audit Result

**Verdict:** PASS | FAIL | PARTIAL PASS

## Tool outputs (verbatim)
[paste outputs from steps 1-5 of the master spec protocol]

## Per-criterion evidence
### (a) filterwarnings config installed
**Status:** PASS | FAIL
**Evidence:** [file:line, command output, etc.]

[continue through (j)]

## Pre-handoff checklist verification
[per master spec step 8]

## Test-first evidence verification
[per master spec step 9, independently re-ran the 4 TEST FAILS tests against pre-PR base]

## Hash injection hook verification (first production usage of issue #15 tool)
[criterion (j) specific — does the handoff's commit hash equal HEAD~1 of the handoff's commit?]

## Discoveries (out-of-scope findings)
[any net-new findings not covered by this issue's scope]

## Cross-check verdict
[summary]
```

If verdict is FAIL or PARTIAL PASS, name the failing criteria precisely. Don't bury the lede.

*Audit outcomes, not recipes. The strict-gate suite run in criterion (b) is the canonical outcome check — if `pytest tests/unit/ -q` exits 0 with `filterwarnings = ["error::RuntimeWarning"]` active, the warnings are gone regardless of how AG implemented the fixes.*
