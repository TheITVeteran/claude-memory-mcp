# Issue #14c — Audit Spec

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14c
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/14c_BUILD_SPEC.md` — **do NOT read**.
**Pattern:** Same as `14a_AUDIT_SPEC.md`.

---

## Canonical pass/fail

```bash
python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

ZERO matches = PASS.

## Per-criterion verification

Same criteria as 14a/14b's audit spec, swapped for `test_hybrid_search.py`. Specifically:

- **(a)** Strict-gate cleanliness (primary, binary)
- **(b)** Architect-injected meta-test `test_meta_fixture_topology_required` present and passing — note this PR extends the meta-test with 4 assertions (repo, vector_store, activation_engine.activate, activation_engine.spread)
- **(c)** No write-guard violations
- **(d)** Hash injection topology correct
- **(e)** Deterministic gates unchanged
- **(f)** Test count not reduced — should increase by 1 (meta-test)
- **(g)** Pre-handoff checklist complete with `tox -e contracts` (NOT `pytest -k contract`) AND ruff evidence pasted
- **(h)** Discovery findings documented — at minimum the 2 fixes at lines 58-59 (file:line / before-after each); if AG found more sites empirically, those too

## Specific verification (architect can predict)

Lines 58-59 of `tests/unit/test_hybrid_search.py` should now read:

```python
    svc.activation_engine.activate = AsyncMock(return_value={})
    svc.activation_engine.spread = AsyncMock(return_value={})
```

If they still read `MagicMock`, the primary fix was missed. FAIL.

## Output format

Standard. Lead with verdict.
