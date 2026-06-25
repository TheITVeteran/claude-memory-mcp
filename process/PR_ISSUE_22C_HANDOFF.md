# Issue #22c Handoff — Migrate `test_tools_coverage.py` to `make_mock_service()`

**Commit:** `536c64e61bdcbbbbca73b8e9c3f1610a13f37183`
**Branch:** `issue-22c/test-tools-coverage-migration`
**Issue:** [#22c / parent #22](https://github.com/iikarus/Dragon-Brain/issues/22)

## Discovery findings

While migrating `tests/unit/test_tools_coverage.py` to use `make_mock_service()`, we scanned the test suite for mock overrides/assignments (Transformation 6). We discovered:
1. Outside the `service` fixture, there are exactly 0 instances of `service.<dep>.<method> = AsyncMock(...)` or `MagicMock(...)` style overrides. All mock setups are configured via `.return_value` or `.side_effect` on the helper-built typed mocks.
2. The only direct dependency replacements were the 3 bare-MagicMock surgery sites (`service.ontology = MagicMock()` x2 in create_memory_type tests, and `service.context_manager = MagicMock()` x1 in get_hologram test). These lines have been deleted entirely, and the tests now utilize the type-correct dependency mocks constructed by `make_mock_service()` without any issues.
3. The custom `MemoryService` instance-level attributes (the `traverse_path` unmocking pattern in tests and the `_fire_salience_update` workaround to prevent unawaited tasks) were successfully preserved.

---

## Test-first evidence

Pre-PR baseline warning behavior (run on `master` with the autouse `_drain_orphan_coroutines` suppression fixture temporarily deleted):

### Seed 1
```
pytest.PytestUnraisableExceptionWarning: Exception ignored in: <coroutine object AsyncMockMixin._execute_mock_call at 0x000002A9C4FC8A40>
Enable tracemalloc to get traceback where the object was allocated.
See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
=========================== short test summary info ===========================
FAILED tests/unit/test_tools_coverage.py::test_sad5_traverse_path_no_nodes_attr
ERROR tests/unit/test_tools_coverage.py::test_evil6_add_observation_entity_not_found
==================== 1 failed, 41 passed, 1 error in 3.80s ====================
```

---

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat master..HEAD` | `tests/unit/test_tools_coverage.py \| 129 ++++++++++++++++++--------------------`<br>`1 file changed, 60 insertions(+), 69 deletions(-)` |
| 2 | `python -m pytest tests/unit/test_tools_coverage.py -v` | `43 passed in 7.58s` |
| 3 | `python -m pytest tests/_helpers/test_mock_factory.py -v` | `8 passed in 2.74s` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13). congratulations :)` |
| 6 | `python -m bandit -r src/claude_memory -ll` | Verbatim Output:<br>```Test results: >> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces. Severity: Medium Location: src/claude_memory\embedding_server.py:148:26``` (Accepted baseline) |
| 7 | `python -m ruff check src/claude_memory tests scripts` | `All checks passed!` (with the invalid noqa warnings) |
| 8 | `git diff --name-only master..HEAD` | ✅ Matches exactly:<br>`process/PR_ISSUE_22C_HANDOFF.md`<br>`tests/unit/test_tools_coverage.py` (after Commit B is added) |
| 9 | Two-commit topology | ✅ Commit A (migration) and Commit B (handoff) successfully orchestrated |

---

## Verification Logs

### 1. Post-PR 4-Seed Sweep Output (Zero warnings across all 4 seeds):
```
=== seed=1 ===
============================= 43 passed in 7.58s ==============================
=== seed=2 ===
============================= 43 passed in 4.01s ==============================
=== seed=3 ===
============================= 43 passed in 3.89s ==============================
=== seed=4 ===
============================= 43 passed in 3.84s ==============================
```

### 2. Helper Mock Factory Tests Run Output:
```
tests/_helpers/test_mock_factory.py::test_evil_vector_store_is_asyncmock PASSED [ 12%]
tests/_helpers/test_mock_factory.py::test_sad_override_replaces_dep PASSED [ 25%]
tests/_helpers/test_mock_factory.py::test_neutral_construction_succeeds PASSED [ 37%]
tests/_helpers/test_mock_factory.py::test_evil_sync_targets_are_magicmock PASSED [ 50%]
tests/_helpers/test_mock_factory.py::test_evil_repo_is_asyncmock_with_async_methods PASSED [ 62%]
tests/_helpers/test_mock_factory.py::test_evil_activation_engine_methods_have_correct_types PASSED [ 75%]
tests/_helpers/test_mock_factory.py::test_sad_marker_threading_via_fixture PASSED [ 87%]
tests/_helpers/test_mock_factory.py::test_sad_allow_sync_keeps_magicmock_on_async_target PASSED [100%]
============================== 8 passed in 2.74s ==============================
```

### 3. `tox -e contracts` Run Output:
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
  contracts: OK (303.02=setup[302.77]+cmd[0.05,0.20] seconds)
  congratulations :) (303.06 seconds)
```

### 4. Strict mypy Run Output:
```
Success: no issues found in 40 source files
```

### 5. Ruff Scan Output:
```
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:169: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:437: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\update_check.py:75: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\clustering.py:54: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\crud_maintenance.py:144: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\date_parser.py:91: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\fts_store.py:224: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\activation.py:194: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
```

### 6. Bandit Audit Run Output:
```
Run started:2026-06-25 18:06:33.252110+00:00

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
	Total potential issues skipped due to specifically being disabled: 2

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
