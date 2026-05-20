# Issue #14a — Async Mock Cleanup Audit Spec (Pilot)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14a
**Auditor:** ChatGPT Codex 5.5 (this is your spec)
**Builder spec:** `process/issues/14a_BUILD_SPEC.md` — **do NOT read**.

Standard protocol per `process/REMEDIATION_AUDIT_SPEC.md`. Audit outcomes, not recipes.

---

## Canonical pass/fail (the outcome check)

```bash
python -m pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

ZERO matches = PASS on the primary criterion. Any match = FAIL with the matched line(s) as evidence.

That's the whole pilot. Everything below verifies it didn't pass via a forbidden shortcut.

---

## Per-criterion verification

### (a) Strict-gate cleanliness (PRIMARY)

Run the canonical check above. Zero matches required.

### (b) Architect-injected meta-test present + passing

`tests/unit/test_tools_coverage.py` contains a test named `test_meta_fixture_topology_required` near the top of the file. The test asserts `isinstance(mock_service.repo, AsyncMock)` and `isinstance(mock_service.vector_store, AsyncMock)`. Run:

```bash
python -m pytest tests/unit/test_tools_coverage.py::test_meta_fixture_topology_required -v
```

Must pass. If absent OR modified to weaker assertions, FAIL.

### (c) No write-guard violations

Verify the harness wasn't bypassed:

```bash
git diff --name-only master..HEAD | grep -E "tests/unit/conftest\.py|tests/conftest\.py|pytest\.ini"
```

Must return zero lines. If any of these files appear in the diff, AG bypassed the branch-write-guard — FAIL.

### (d) Hash injection topology correct

The handoff doc's `**Commit:**` field must equal `git rev-parse HEAD~1` (= the implementation commit). Verify per master spec criterion (j) from issue #14's original audit spec.

### (e) Deterministic gates unchanged

Standard tool runs — all must pass at their baseline:

```bash
tox -e contracts                          # baseline 13
python -m mypy --strict src/claude_memory # 40 files, 0 errors
python -m ruff check src/claude_memory tests scripts
python -m bandit -r src/claude_memory -ll # only accepted B104
python -m pytest tests/unit/ -q           # pass count >= 1283
```

### (f) Test count not reduced

```bash
python -m pytest tests/unit/test_tools_coverage.py --collect-only -q | tail -2
```

Compare to pre-PR count. AG must not delete tests as a "fix." Test count should increase by 1 (the architect-injected meta-test).

### (g) Pre-handoff checklist complete

All 9 items in `process/PR_ISSUE_14A_HANDOFF.md` per master spec. No "N/A" for bandit / mypy / contracts.

### (h) Discovery findings documented

The handoff's "Discovery findings" section must enumerate every site fixed (file:line, before/after snippet, one row per fix). If no fixes were needed (file was already clean), the handoff says so explicitly with empirical evidence.

---

## Constraints

- Do NOT read the build spec.
- Do NOT audit aspects outside this sub-issue's scope (other files in `tests/unit/` are out of bounds for THIS PR).
- Do NOT mark PASS if the canonical strict-gate check shows any warning sentinel. The primary criterion is binary.

## Output format

Standard per master spec. Lead with the verdict — don't bury the lede.
