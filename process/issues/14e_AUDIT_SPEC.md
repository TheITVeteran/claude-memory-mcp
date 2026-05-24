# Issue #14e — Audit Spec (the actual #14 closer, multi-seed gate)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14e
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/14e_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail (multi-seed, FOUR checks, ALL must pass)

**Check 1 — file-level multi-seed:**
```bash
for seed in 1 7 12345 4231726796; do
  result=$(python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning --randomly-seed=$seed -q --tb=no 2>&1 \
    | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning" | wc -l)
  echo "seed=$seed matches=$result"
done
```
All 4 must report `matches=0`. Any non-zero = FAIL.

**Check 2 — full-suite multi-seed (THE #14 closure criterion):**
```bash
for seed in 1 7 12345 4231726796; do
  result=$(python -m pytest tests/unit/ -W error::RuntimeWarning --randomly-seed=$seed -q --tb=no 2>&1 \
    | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning" | wc -l)
  echo "full-suite seed=$seed matches=$result"
done
```
All 4 must report `matches=0`.

**Check 3 — suppression fixture removed:**
```bash
rg -n "_drain_orphan_coroutines|catch_warnings|simplefilter.*ignore.*RuntimeWarning|gc\.collect" tests/unit/test_hybrid_search.py
```
ZERO matches required. If any line matches, the suppression pattern wasn't fully removed.

**Check 4 — line 197-198 fix applied:**
```bash
rg -n "service\.activation_engine\.(activate|spread)\s*=\s*MagicMock" tests/unit/test_hybrid_search.py
```
ZERO matches required. If any line matches, the original bug wasn't fixed.

## Per-criterion verification

- **(a) Multi-seed strict-gate cleanliness — file-level + full-suite.** Both must clean at all 4 seeds. Primary criterion is binary AND repeatable.
- **(b) Suppression fixture removed** (Check 3 above)
- **(c) Original bug fix applied** (Check 4 above)
- **(d) Master AUDIT_SPEC updated** — `process/REMEDIATION_AUDIT_SPEC.md` diff shows new multi-seed gate + subprocess-per-test attribution-on-failure requirement
- **(e) No write-guard violations** — `git diff --name-only master..HEAD` zero matches for `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`. Also verify no NEW suppression fixtures elsewhere: `rg -n "catch_warnings|simplefilter.*ignore.*RuntimeWarning" tests/unit/`
- **(f) Hash injection topology** — handoff `**Commit:**` equals `git rev-parse HEAD~1`
- **(g) Deterministic gates unchanged** (`tox -e contracts` baseline 13, mypy clean, ruff clean, bandit only accepted B104)
- **(h) Pre-handoff checklist complete** with multi-seed evidence under item 4 (replacing single contracts run)
- **(i) Discovery findings documented** in handoff — every additional site beyond lines 197-198 listed with file:line / before-after / per-seed verification

## Subprocess-per-test attribution (if needed during audit)

If any seed in Check 1 or Check 2 emits, BEFORE marking FAIL, run subprocess-per-test on the failing file to confirm attribution:

```bash
python -m pytest tests/unit/test_hybrid_search.py --forked -W error::RuntimeWarning --randomly-seed=$failing_seed -v 2>&1
```

(Requires `pytest-forked` plugin; install if missing.) Subprocess isolation per test eliminates cross-test GC bleed. The test that emits in its own subprocess IS the source.

Report attribution finding in audit. This prevents wasting another trifecta cycle on a misattributed site (the failure mode that burned 14d).

## Output format

Standard. Lead with verdict. If PASS, explicitly note "Issue #14 closeable; master audit protocol now uses multi-seed deterministic strict gate + subprocess-per-test attribution protocol."
