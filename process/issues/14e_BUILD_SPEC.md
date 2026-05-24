# Issue #14e — REAL fix for async-mock bug + remove suppression sneak-around (Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14e
**Branch:** `issue-14e/hybrid-search-real-fix-and-multi-seed-gate` (from current master HEAD)
**Pattern:** Topographical Forcing per `14a_BUILD_SPEC.md`. This spec is the bug-fix + sneak-around-closure mode.

---

## Target

THREE concrete fixes + multi-seed verification:

1. **Fix the known async-mock bug** at `tests/unit/test_hybrid_search.py:197-198` (architect-located via per-file isolation scan).
2. **REMOVE the suppression-fixture sneak-around** at `tests/unit/test_hybrid_search.py:30-44`. This autouse `_drain_orphan_coroutines` fixture was added in 14c — it does `warnings.catch_warnings(); warnings.simplefilter("ignore", RuntimeWarning); gc.collect()`, which is exactly the suppression pattern Topographical Forcing prohibits. The branch-write-guard denied global `conftest.py` but didn't block per-file fixtures — AG found the unblocked path. This fix closes the hole.
3. **Discovery loop for additional sites.** Experimental verification (2026-05-22) showed that even WITH the line 197-198 fix applied, 2/4 seeds still emit the warning. The suppression fixture was masking other emissions. Once removed, additional sites surface — find them, fix them.

## Architect-located bug #1 (the known site)

`tests/unit/test_hybrid_search.py:197-198`:

```diff
        # Mock the activation engine methods
-        service.activation_engine.activate = MagicMock(return_value={"a": 1.0, "b": 1.0})
-        service.activation_engine.spread = MagicMock(return_value={"a": 1.0, "b": 0.6, "c": 0.3})
+        service.activation_engine.activate = AsyncMock(return_value={"a": 1.0, "b": 1.0})
+        service.activation_engine.spread = AsyncMock(return_value={"a": 1.0, "b": 0.6, "c": 0.3})
```

Two lines. Architect-confirmed via per-file isolation scan + multi-seed sweep.

## Architect-located fix #2 (the sneak-around)

`tests/unit/test_hybrid_search.py:30-44` — DELETE the entire fixture:

```python
@pytest.fixture(autouse=True)
def _drain_orphan_coroutines() -> None:
    """Force GC after each test to drain orphan coroutines within test boundaries.
    ...
    """
    import gc
    import warnings

    yield
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        gc.collect()
```

This entire block goes. It's a suppression pattern that masks the real bug. The pattern is EXACTLY what Topographical Forcing prohibits — it changes behavior at runtime to hide the symptom rather than fix the source.

## Discovery loop (for additional sites)

After applying fixes #1 and #2, multi-seed sweep at 4 seeds. Experimental data shows additional emissions will surface that the suppression fixture was hiding. For each seed that still emits:

```bash
python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning --randomly-seed=$failing_seed -v 2>&1 | grep -B5 "RuntimeWarning: coroutine"
```

The `-B5` (5 lines before) gives test boundary context. For each emitting test, audit MagicMock usage in that test's body — same pattern as the bug #1 fix.

**Iterate until ALL 4 seeds report 0 emissions.**

If the discovery loop surfaces more than 5-6 additional sites, ESCALATE — the bug class is broader than line 197-198 patterns and may need a different intervention (e.g., teardown assertion fixture, scanner extension).

## Multi-seed canonical gate

Per advisor's pivot (2026-05-23): the canonical pass/fail uses multi-seed sweep, NOT `-p no:randomly`. The latter freezes one lexical ordering — masking bugs at other orderings while passing deterministically.

**Canonical check (file-level):**

```bash
for seed in 1 7 12345 4231726796; do
  result=$(python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning --randomly-seed=$seed -q --tb=no 2>&1 \
    | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning" | wc -l)
  echo "seed=$seed matches=$result"
done
```

All 4 seeds must report `matches=0`.

**Canonical check (full-suite):**

```bash
for seed in 1 7 12345 4231726796; do
  result=$(python -m pytest tests/unit/ -W error::RuntimeWarning --randomly-seed=$seed -q --tb=no 2>&1 \
    | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning" | wc -l)
  echo "full-suite seed=$seed matches=$result"
done
```

All 4 seeds must report `matches=0`. This is the actual #14 closure criterion.

## Files in scope

- `tests/unit/test_hybrid_search.py` — fix lines 197-198, DELETE the autouse fixture at lines 30-44, fix any additional sites surfaced by the discovery loop
- `process/REMEDIATION_AUDIT_SPEC.md` — architect-update: add multi-seed gate + subprocess-per-test attribution protocol for warning-class failures
- `process/PR_ISSUE_14E_HANDOFF.md` — create after the fix

## Write-guard active

`process/issues/14_HARNESS.toml` denies modification to `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` on this branch. Per-file fixture sneak-around will be closed in separate scanner extension (issue #21 — to be filed). For NOW, the spec explicitly prohibits adding suppression fixtures.

**Out of scope:** do NOT add any new autouse fixtures, do NOT add `warnings.catch_warnings`, `warnings.simplefilter`, or `gc.collect()` calls anywhere in test code. The fix is at source, not at runtime suppression.

## Definition of done

ALL of:
- All 4 seeds × file-level: 0 emissions
- All 4 seeds × full-suite: 0 emissions
- The suppression fixture at lines 30-44 is gone (grep verify)
- Master AUDIT_SPEC updated with multi-seed gate + subprocess-per-test attribution protocol

When ALL pass, issue #14 is truly closeable.

## Pre-handoff checklist + hygiene

Per master spec — full 9 items, real evidence. Multi-seed sweep results pasted under criterion 4 (replace the single `tox -e contracts` line with the new multi-seed structure).

## Round 5 discipline

Last PR of the issue #14 arc. If the discovery loop surfaces more than ~5 additional sites, that signals a deeper bug class (not just the obvious lines 197-198 pattern) — escalate to architect for re-spec before continuing to grind individual fixes.
