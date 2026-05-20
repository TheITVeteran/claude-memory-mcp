# Issue #14b — Audit Spec

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14b
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/14b_BUILD_SPEC.md` — **do NOT read**.
**Pattern:** Same as `14a_AUDIT_SPEC.md`. This spec is file-specific.

---

## Canonical pass/fail

```bash
python -m pytest tests/unit/test_memory_service.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

ZERO matches = PASS. Anything else = FAIL.

## Per-criterion verification

Same criteria as 14a's audit spec, with file path swapped from `test_tools_coverage.py` to `test_memory_service.py`. Specifically:

- **(a)** Strict-gate cleanliness (primary, binary) — canonical check above
- **(b)** Architect-injected meta-test `test_meta_fixture_topology_required` present and passing
- **(c)** No write-guard violations — `git diff --name-only master..HEAD` returns zero matches for `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`
- **(d)** Hash injection topology — handoff `**Commit:**` equals `git rev-parse HEAD~1`
- **(e)** Deterministic gates unchanged (`tox -e contracts` at baseline 13, mypy clean, ruff clean, bandit only accepted B104)
- **(f)** Test count not reduced — should increase by 1 (meta-test)
- **(g)** Pre-handoff checklist complete — **specifically verify item 5 uses `tox -e contracts` (not `pytest -k contract`) and item 5/ruff has real evidence pasted**. 14a's audit caught these gaps; don't accept them on 14b.
- **(h)** Discovery findings documented — file:line / before-after for each fix, OR explicit "no fixes needed because file is clean"

## Output format

Standard per master spec. Lead with verdict.
