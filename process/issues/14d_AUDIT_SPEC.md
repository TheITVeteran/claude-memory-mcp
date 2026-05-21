# Issue #14d — Audit Spec

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14d
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/14d_BUILD_SPEC.md` — **do NOT read**.
**Pattern:** Same as `14a_AUDIT_SPEC.md`. This spec is file-specific.

---

## Canonical pass/fail (TWO checks, BOTH must pass)

**Check 1 — file-level:**
```bash
python -m pytest tests/unit/test_embedding_filter.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```
ZERO matches.

**Check 2 — full-suite (this is the actual issue-#14-closure criterion):**
```bash
python -m pytest tests/unit/ -W error::RuntimeWarning -q --tb=no 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```
ZERO matches. If this still emits, AG missed something — issue #14 stays open.

## Per-criterion verification

Same criteria as 14b/14c's audit specs, scoped to `test_embedding_filter.py`:

- **(a) Strict-gate cleanliness — file-level AND full-suite.** Both must be empty. Primary criterion is binary.
- **(b)** Architect-injected meta-test `test_meta_fixture_topology_required` present and passing
- **(c)** No write-guard violations — `git diff --name-only master..HEAD` zero matches for `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`
- **(d)** Hash injection topology — handoff `**Commit:**` equals `git rev-parse HEAD~1`
- **(e)** Deterministic gates unchanged (`tox -e contracts` baseline 13, mypy clean, ruff clean, bandit only accepted B104)
- **(f)** Test count not reduced — should increase by 1 (meta-test)
- **(g)** Pre-handoff checklist complete with `tox -e contracts` AND ruff evidence pasted
- **(h)** Discovery findings documented — at minimum the specific site(s) AG identified and fixed

## Specific verification (architect prediction)

Architect's static reading suggests the bug is subtle (the file's fixture is mostly clean per inventory). AG's discovery-loop will identify the exact site. Whatever it is, the post-fix file should:

- Run `test_happy_get_hologram_strips_embedding` under strict gate cleanly
- Run the full unit suite under strict gate cleanly (this is the actual closure criterion)

If only the file-level check passes but full-suite still emits warnings somewhere else, that's a regression introduced by 14d OR a missed site elsewhere — FAIL.

## Output format

Standard. Lead with verdict.

## Closure note

If 14d PASSes, **the original issue #14 is genuinely closeable** — full-suite strict gate is the criterion the 14_AUDIT_SPEC.md set from day one. Codex's verdict on 14d determines whether #14 can be re-closed.
