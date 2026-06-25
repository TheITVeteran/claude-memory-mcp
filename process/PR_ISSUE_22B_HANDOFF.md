# Issue #22b Handoff — Migrate `test_hybrid_search.py` to `make_mock_service()`

**Commit:** `dbce44d47f22b27f03c1c2ed546f2d3e9d67f9eb`
**Branch:** `issue-22b/test-hybrid-search-migration`
**Issue:** [#22b / parent #22](https://github.com/iikarus/Dragon-Brain/issues/22)

## Discovery findings

While migrating `tests/unit/test_hybrid_search.py` to use `make_mock_service()`, we discovered a critical Python mock quirk that explains why `RuntimeWarning` leaks occur.

When `spread` is set up as an `AsyncMock`, its default return value is also an `AsyncMock`. Because of this, invoking synchronous dictionary methods like `keys()` on the returned `spread_map` (e.g. `spread_map.keys()`) returns a coroutine object by default instead of a collection. In the production code `all_ids = list(set(seed_ids) | set(spread_map.keys()))`, this leads to:
1. A `TypeError: 'coroutine' object is not iterable` traceback.
2. An unawaited coroutine leakage (`RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`).

By establishing type-correct default values on the mocked activation engine (`activate.return_value = {}` and `spread.return_value = {}`), we ensure the mocks return real dictionaries, allowing the synchronous dictionary methods to execute normally without generating unawaited coroutine warnings.

---

## Test-first evidence

Pre-PR baseline warning counts per seed (run on `master` pre-migration):

### Seed 1
```
tests/unit/test_hybrid_search.py::TestIncludeMetaEnvelope::test_happy_include_meta_false_returns_plain_list FAILED
E                   pytest.PytestUnraisableExceptionWarning: Exception ignored in: <coroutine object AsyncMockMixin._execute_mock_call at 0x0000023F76738340>
E                   Enable tracemalloc to get traceback where the object was allocated.
E                   See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
======================== 1 failed, 27 passed in 13.89s ========================
```

### Seed 2
```
pytest.PytestUnraisableExceptionWarning: Exception ignored in: <coroutine object AsyncMockMixin._execute_mock_call at 0x000002E168C43E40>
Enable tracemalloc to get traceback where the object was allocated.
See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
============================= 28 passed in 14.14s =============================
```

### Seed 3
```
============================= 28 passed in 13.75s =============================
```

### Seed 4
```
tests/unit/test_hybrid_search.py::TestIncludeMetaEnvelope::test_happy_include_meta_false_returns_plain_list FAILED
E                   pytest.PytestUnraisableExceptionWarning: Exception ignored in: <coroutine object AsyncMockMixin._execute_mock_call at 0x000002235F3C8A40>
E                   Enable tracemalloc to get traceback where the object was allocated.
E                   See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
======================== 1 failed, 27 passed in 14.34s ========================
```

---

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat master..HEAD` | `process/PR_ISSUE_22B_HANDOFF.md   \| 153 ++++++++++++++++++++++++++++++++++++`<br>`tests/unit/test_hybrid_search.py    \|  93 +++++++----------------`<br>`2 files changed, 172 insertions(+), 74 deletions(-)` |
| 2 | `python -m pytest tests/unit/test_hybrid_search.py -v` | `28 passed in 11.63s` |
| 3 | `python -m pytest tests/_helpers/test_mock_factory.py -v` | `8 passed in 2.66s` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13). concongratulations :)` |
| 6 | `python -m bandit -r src/claude_memory -ll` | Verbatim Output:<br>```Test results: >> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces. Severity: Medium Location: src/claude_memory\embedding_server.py:148:26``` (Accepted baseline) |
| 7 | `python -m ruff check src/claude_memory tests scripts` | `All checks passed!` |
| 8 | `git diff --name-only master..HEAD` | ✅ Matches exactly:<br>`process/PR_ISSUE_22B_HANDOFF.md`<br>`tests/unit/test_hybrid_search.py` |
| 9 | Two-commit topology | ✅ Commit A (migration) and Commit B (handoff) successfully orchestrated |

---

## Verification Logs

### 1. Post-PR 4-Seed Sweep Output (Zero warnings across all 4 seeds):
```
=== seed=1 ===
28 passed in 11.63s
=== seed=2 ===
28 passed in 11.61s
=== seed=3 ===
28 passed in 11.64s
=== seed=4 ===
28 passed in 11.69s
```

### 2. `tox -e contracts` Run Output:
```
contracts: commands[0]> python -c "print('\n[1/1] Contract Scanner...')"

[1/1] Contract Scanner...
contracts: commands[1]> python scripts/trace_contracts_dragon.py src/claude_memory --baseline 13
Dragon Brain Contract Scanner — Audit Edition
============================================================

Scanned 40 files. Found 13 violations.

By category:
  Bare Pass: 6
  Silent Fallback: 5
  Per-Item Swallow: 2

Report saved to contract_violations_report.md

SUCCESS: Violations (13) are within baseline (13).
  contracts: OK (11.81=setup[11.55]+cmd[0.06,0.20] seconds)
  congratulations :) (11.89 seconds)
```

### 3. Full-scope Ruff (`python -m ruff check src/claude_memory tests scripts`) Output:
```
warning: Invalid `# noqa` directive on src\claude_memory\clustering.py:54: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\crud_maintenance.py:144: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\date_parser.py:91: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\update_check.py:75: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\fts_store.py:224: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:169: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:437: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\activation.py:194: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
```

### 4. `python -m bandit -r src/claude_memory -ll` Run Output:
```
Run started:2026-06-24 21:19:45.370794+00:00

Test results:
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.9.3/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: src/claude_memory\embedding_server.py:148:26
147	    port = int(os.getenv("PORT", "8000"))
148	    uvicorn.run(app, host="0.0.0.0", port=port)  # noqa: S104

--------------------------------------------------

Code scanned:
	Total lines of code: 6740
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 2

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 1
		Medium: 1
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 1
		High: 1
Files skipped (0):
```
