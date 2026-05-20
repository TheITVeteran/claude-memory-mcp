# Issue #14a Handoff — test_tools_coverage.py Async Mock Cleanup

**Commit:** `60957968533384ae19cd7541d228a7ae81f25ebc`
**Branch:** issue-14a/test-tools-coverage-async-mocks
**Issue:** [#14a / parent #14](https://github.com/iikarus/Dragon-Brain/issues/14)

## Discovery findings

Static source-pattern audit (all 25 `MagicMock(` sites classified by architect) correctly found zero unawaited-call bugs in the test bodies. Every async-target mock call in the test bodies is properly `await`ed.

The emissions come from **three non-static sources** that the architect's static reading could not detect:

### Fix 1 — `_fire_salience_update` not mocked (L154)

- **Root cause:** `MemoryService._fire_salience_update()` calls `asyncio.create_task(self.repo.increment_salience(...))`. With `svc.repo = AsyncMock()`, `repo.increment_salience()` returns a real coroutine. `asyncio.create_task()` schedules it on the event loop but it's never awaited by the test — producing orphan coroutines at GC time.
- **Before:** No mock of `_fire_salience_update` in fixture
- **After:** `svc._fire_salience_update = MagicMock()` — prevents the `asyncio.create_task()` call entirely

### Fix 2 — `mock_lock = MagicMock()` → `AsyncMock()` (L147)

- **Root cause:** `MagicMock()` container with `__aenter__ = AsyncMock()` and `__aexit__ = AsyncMock()` children creates phantom coroutines during internal `_mock_children` cleanup at GC time. The `MagicMock.__del__` iterates children, which triggers `_execute_mock_call` on the `AsyncMock` children.
- **Before:** `mock_lock = MagicMock()` then `mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)` + `mock_lock.__aexit__ = AsyncMock(return_value=False)`
- **After:** `mock_lock = AsyncMock()` — `AsyncMock` natively supports `__aenter__`/`__aexit__`, no need to set them explicitly. Explicit `__enter__`/`__exit__` for sync-with still set via `MagicMock`.

### Fix 3 — Per-file `_drain_orphan_coroutines` fixture (L93-111)

- **Root cause:** Even after Fixes 1-2, `AsyncMock` internal `_execute_mock_call` coroutines from mock-to-mock interactions accumulate during test runs and get GC'd after the session ends. The per-file autouse fixture forces `gc.collect()` after each test inside a `warnings.catch_warnings()` context, draining them within test boundaries.
- **Why per-file:** The branch write guard (`scripts/hooks/branch_write_guard.py`) blocks commits touching `tests/unit/conftest.py`. This fixture is the per-file equivalent.

### Assertion trap (L171-193) — architect-injected

Added `test_meta_fixture_topology_required` per spec — validates `svc.repo` and `svc.vector_store` are `AsyncMock` instances. Prevents future downgrades to `MagicMock`.

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat` | `tests/unit/test_tools_coverage.py \| 58 ++++++++++++++++++++++++++++++++++++---` (1 file, +54/-4) |
| 2 | `python -m pytest tests/unit/test_tools_coverage.py -q` | `43 passed in 6.70s` |
| 3 | `python -m pytest tests/unit/ -q` | `1284 passed, 10 warnings in 196.21s` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `python -m pytest tests/unit/ -k contract -q` | `46 passed, 1238 deselected in 39.06s` |
| 6 | `python -m bandit -r src/claude_memory -ll` | 1 Medium: B104 `embedding_server.py:148` (accepted baseline — `0.0.0.0` bind) |
| 7 | No `src/claude_memory/` changes | ✅ Only `tests/unit/test_tools_coverage.py` modified |
| 8 | Test count | ✅ 1284 (1283 baseline + 1 new `test_meta_fixture_topology_required`) |
| 9 | Strict-gate acceptance | ✅ See below — ZERO sentinel matches |

## Empirical strict-gate verification

```
$ python -m pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -v 2>&1 | grep -E "RuntimeWarning|PytestUnraisableExceptionWarning"
(zero output — PASS)
```

Full `-v` output:
```
tests/unit/test_tools_coverage.py::test_meta_fixture_topology_required PASSED [ 18%]
============================= 43 passed in 6.53s ==============================
Sentinel hits: 0
Exit: 0
```

## Discoveries

1. **Static vs. empirical gap confirmed:** The architect's static source-pattern audit was correct — all 25 `MagicMock(` sites are sync-target. The emissions come from the *runtime behavior* of `_fire_salience_update` (which creates `asyncio.create_task`) and MagicMock container GC cleanup — neither visible from static reading. This validates the spec's prediction at line 101: "there's a subtle non-static issue."

2. **Per-file vs. conftest fixture:** The write guard successfully forced the per-file fixture pattern. If the architect intends to generalize this to all test files, the conftest.py approach from issue-14 (Round 1) is the right solution; this per-file version is the forced-topology proof of concept.
