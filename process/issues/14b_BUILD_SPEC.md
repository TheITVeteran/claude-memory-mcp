# Issue #14b — `test_memory_service.py` Async Mock Cleanup (Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14b
**Branch:** `issue-14b/test-memory-service-async-mocks` (from current master HEAD)
**Pattern:** Same Topographical Forcing blueprint as `14a` — see [`14a_BUILD_SPEC.md`](14a_BUILD_SPEC.md) for the full framework reference. This spec is file-specific.

---

## Target

`tests/unit/test_memory_service.py` — 2033 lines, 37 MagicMock sites. Codex's Round 2 audit confirmed warnings still emit from this file (named in PR-6 Discovery as the second flagged site after `test_tools_coverage.py`).

**Acceptance (canonical pass/fail):**

```bash
python -m pytest tests/unit/test_memory_service.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

→ ZERO matches.

## Async-signature inventory

Reuse from `14a_BUILD_SPEC.md` § "Async signature inventory" — the inventory is identical (same `MemoryService`, `AsyncMemoryRepository`, `VectorStore`, etc.). Do not re-paste.

## Discovery loop

File is too large (2033 lines, 37 sites) for the Architect to enumerate every site statically. Use the empirical discovery loop:

1. **Run the strict gate, capture warning context:**
   ```bash
   python -m pytest tests/unit/test_memory_service.py -W error::RuntimeWarning -v 2>&1 | tee /tmp/14b_strict.log
   ```
2. **For each test passing but emitting the warning sentinel afterward**, find AsyncMock calls without `await` OR MagicMock targets that should be AsyncMock per the inventory.
3. **Fix each candidate. Re-run. Iterate until zero matches.**

The fixture at lines 96-141 follows the same pattern as test_tools_coverage.py (which 14a established as correctly structured per static reading — the bugs were in test bodies, not fixture). Likely the same pattern here: fixture is correct, bugs live at use sites in the 2000+ lines below.

## Golden diff template

Identical to 14a's. Reference [`14a_BUILD_SPEC.md`](14a_BUILD_SPEC.md) § "Golden diff (architect-provided template)" for the exact transformation pattern.

## Assertion trap (architect-injected)

Inject this test at the TOP of `tests/unit/test_memory_service.py` (after imports, before existing tests):

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: fixture must use AsyncMock for async-target attributes.

    Architect-injected per process/issues/14b_BUILD_SPEC.md.
    DO NOT remove or weaken this test.
    """
    from unittest.mock import AsyncMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
```

## Files in scope

- `tests/unit/test_memory_service.py` — modify as needed (test body fixes; fixture likely already correct)
- `process/PR_ISSUE_14B_HANDOFF.md` — create after the fix

## Write-guard active

`process/issues/14_HARNESS.toml` denies modification to `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` on this branch. Bypass = audit fail.

## Two-commit topology (mandatory)

Per master spec checklist item 1:

```bash
git add tests/unit/test_memory_service.py
git commit -m "fix(tests): proper await on async-target mocks in test_memory_service (#14b)"

git add process/PR_ISSUE_14B_HANDOFF.md  # uses **Commit:** <auto> placeholder
git commit -m "docs(issue-14b): handoff doc (hash auto-injected)"

git push --force-with-lease origin issue-14b/test-memory-service-async-mocks
```

## Handoff structure

Per 14a's pattern. **Use the FULL pre-handoff checklist with REAL evidence — Codex's audit on 14a flagged checklist hygiene as the only failure. Do not use `pytest -k contract`; use `tox -e contracts` for item 5. Paste ruff evidence (currently omitted on 14a).**

## Round 5 discipline

If anything ambiguous, escalate. "No fix needed because file is already clean" is valid. The pilot validates the procedure — not "must find fixes."
