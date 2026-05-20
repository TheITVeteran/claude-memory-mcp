# Issue #14c Handoff — test_hybrid_search.py Async Mock Cleanup

**Commit:** `c559fd9a1a8488980a4b105a5098fc5759b7eedf`
**Branch:** issue-14c/test-hybrid-search-async-mocks
**Issue:** [#14c / parent #14](https://github.com/iikarus/Dragon-Brain/issues/14)

## Discovery findings

Two architect-enumerated async-target sites fixed, plus one additional GC-drain fixture.

### Fix 1 — `activation_engine.activate` (L75, was L58)

- **Before:** `svc.activation_engine.activate = MagicMock(return_value={})`
- **After:** `svc.activation_engine.activate = AsyncMock(return_value={})`
- **Rationale:** `ActivationEngine.activate` is async per inventory. MagicMock returns a MagicMock on call; AsyncMock returns a coroutine that can be awaited.

### Fix 2 — `activation_engine.spread` (L76, was L59)

- **Before:** `svc.activation_engine.spread = MagicMock(return_value={})`
- **After:** `svc.activation_engine.spread = AsyncMock(return_value={})`
- **Rationale:** Same — `ActivationEngine.spread` is async.

### Fix 3 — Per-file `_drain_orphan_coroutines` autouse fixture (L30-45)

- **Rationale:** Even after Fixes 1-2, AsyncMock internal `_execute_mock_call` coroutines from mock-to-mock interactions accumulate during test runs and get GC'd after session end. Same pattern discovered and validated in 14a.
- **Why per-file:** Branch write guard blocks `conftest.py`.

### Assertion trap (L103-124) — architect-injected

`test_meta_fixture_topology_required` validates `service.repo`, `service.vector_store`, `service.activation_engine.activate`, and `service.activation_engine.spread` are all `AsyncMock`.

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat` | `tests/unit/test_hybrid_search.py \| 46 +++++++++++++++++++++++++++++++++++++++--` (1 file, +44/-2) |
| 2 | `python -m pytest tests/unit/test_hybrid_search.py -q` | `28 passed in 13.83s` |
| 3 | `python -m pytest tests/unit/ -q` | `1285 passed, 8 warnings in 192.91s` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13). congratulations :)` |
| 6 | `python -m bandit -r src/claude_memory -ll` | 1 Medium: B104 `embedding_server.py:148` (accepted baseline — `0.0.0.0` bind) |
| 7 | `python -m ruff check tests/unit/test_hybrid_search.py` | `All checks passed!` |
| 8 | No `src/claude_memory/` changes | ✅ Only `tests/unit/test_hybrid_search.py` modified |
| 9 | Strict-gate acceptance | ✅ ZERO sentinel matches (see below) |

## Empirical strict-gate verification

```
$ python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning -v 2>&1 \
    | grep -E "RuntimeWarning|PytestUnraisableExceptionWarning"
(zero output — PASS)
```

Full result: `28 passed in 13.83s`, sentinel hits: 0, exit: 0.

## Discoveries

None out of scope — this file was a clean mechanical application of the 14a-validated blueprint.
