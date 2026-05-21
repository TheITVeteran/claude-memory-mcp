# Issue #14b Handoff — test_memory_service.py Async Mock Cleanup

**Commit:** `46c260535ab13b1dfe0dbe08bf003fce0c7ea318`
**Branch:** issue-14b/test-memory-service-async-mocks
**Issue:** [#14b / parent #14](https://github.com/iikarus/Dragon-Brain/issues/14)

## Discovery findings

Discovery-loop mode (2033 lines, 37 MagicMock sites). Empirical strict gate found 33 sentinel hits at baseline.

### Fix 1 — `_fire_salience_update` not mocked (L153)

- **Root cause:** Same as 14a — `asyncio.create_task(repo.increment_salience(...))` spawns orphan coroutines with AsyncMock repo.
- **Fix:** `svc._fire_salience_update = MagicMock()` in fixture.
- **Side-effect:** Two tests (`test_happy_search_fires_salience_async`, `test_evil13_search_salience_background_error_silent`) explicitly test the fire-and-forget pathway. Added `del service._fire_salience_update` at the top of both to restore the real class method.

### Fix 2 — `mock_lock = MagicMock()` → `AsyncMock()` (L146)

- **Root cause:** Same as 14a — MagicMock container with `__aenter__`/`__aexit__` AsyncMock children creates phantom coroutines during `_mock_children` cleanup.
- **Fix:** `mock_lock = AsyncMock()`. Removed explicit `__aenter__`/`__aexit__` assignments (AsyncMock supports them natively).

### Fix 3 — Per-file `_drain_orphan_coroutines` autouse fixture (L93-109)

- **Rationale:** Same as 14a/14c — drains remaining AsyncMock internal `_execute_mock_call` coroutines within test boundaries via `gc.collect()` inside `warnings.catch_warnings()`.

### Assertion trap (L163-177) — architect-injected

`test_meta_fixture_topology_required` validates `service.repo` and `service.vector_store` are `AsyncMock`.

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat` | `tests/unit/test_memory_service.py \| 53 ++++++++++++++++++++++++++++++++++++---` (1 file, +49/-4) |
| 2 | `python -m pytest tests/unit/test_memory_service.py -q` | `103 passed in 13.69s` |
| 3 | `python -m pytest tests/unit/ -q` | `1286 passed in 205.95s` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13). congratulations :)` |
| 6 | `python -m bandit -r src/claude_memory -ll` | 1 Medium: B104 `embedding_server.py:148` (accepted baseline) |
| 7 | `python -m ruff check tests/unit/test_memory_service.py` | `All checks passed!` |
| 8 | No `src/claude_memory/` changes | ✅ Only `tests/unit/test_memory_service.py` modified |
| 9 | Strict-gate acceptance | ✅ ZERO sentinel matches (see below) |

## Empirical strict-gate verification

```
$ python -m pytest tests/unit/test_memory_service.py -W error::RuntimeWarning -v 2>&1 \
    | grep -E "RuntimeWarning|PytestUnraisableExceptionWarning"
(zero output — PASS)
```

Full result: `103 passed in 13.69s`, sentinel hits: 0, exit: 0.

## Discoveries

1. **Salience tests require real `_fire_salience_update`:** Two tests explicitly exercise the fire-and-forget salience pathway. Fixture mock prevents the `asyncio.create_task()` call entirely, which breaks these tests. Solution: `del service._fire_salience_update` at the start of each test restores the original class method. The GC drain fixture handles any residual coroutines from these tests.

2. **Discovery loop validated:** The spec correctly predicted the fixture was the bug site (same pattern as 14a). No test body fixes needed beyond the two salience test restorations.
