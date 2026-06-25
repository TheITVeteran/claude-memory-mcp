# Issue #22d Handoff — Migrate `test_memory_service.py` to `make_mock_service()`

**Commit:** `98d77bd15b1aaf3fec5e45e19e6ef9c95191a683`
**Branch:** `issue-22d/test-memory-service-migration`
**Issue:** [#22d / parent #22](https://github.com/iikarus/Dragon-Brain/issues/22)

## Discovery findings

While migrating `tests/unit/test_memory_service.py` to use `make_mock_service()`, we scanned the test suite for mock overrides/assignments (Transformation 7). We discovered:
1. Outside the `service` fixture, there are exactly 0 instances of `service.<dep>.<method> = AsyncMock(...)` or `MagicMock(...)` style overrides. All mock setups are configured via `.return_value` or `.side_effect` on the helper-built typed mocks.
2. The bare-MagicMock replacement deletions (Transformation 4 & 5) were performed cleanly:
   - Deleted the four `service.ontology = MagicMock()` lines across test cases.
   - Deleted the `service.context_manager = MagicMock()` line under the hologram retrieval tests.
   - All tests now successfully utilize the type-correct dependency mocks constructed by `make_mock_service()` without any issues.
3. Method-level mock replacements (Transformation 6) were successfully converted:
   - Changed `service.ontology.is_valid_type = MagicMock(return_value=True)` overrides to `.return_value = True` on the existing mock.
   - Deleted redundant `service.vector_store.upsert = AsyncMock()` overrides since the helper automatically provisions it as an `AsyncMock` via introspection.

---

## Test-first evidence

Pre-PR baseline warning behavior (captured against a disposable copy of `master` with the `_drain_orphan_coroutines` fixture stripped, exposing the warning class the migration fixes):

### Seed 1
```
tests/unit/test_memory_service.py::test_sad20_service_query_timeline_with_project ERROR [ 61%]
tests/unit/test_memory_service.py::test_happy_traverse_path_with_nodes ERROR [ 66%]
tests/unit/test_memory_service.py::test_happy_add_observation_creates_vector ERROR [ 79%]
tests/unit/test_memory_service.py::test_sad10_point_in_time_query_no_results ERROR [ 83%]
tests/unit/test_memory_service.py::test_happy_analyze_graph_pagerank_only_entity_label ERROR [ 97%]

=================================== ERRORS ====================================
______ ERROR at setup of test_sad20_service_query_timeline_with_project _______
E       RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
C:\Users\Asus\AppData\Local\Programs\Python\Python312\Lib\warnings.py:555: RuntimeWarning
```

---

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat master..HEAD` | `tests/unit/test_memory_service.py \| 114 +++++++++++++++++---------------------`<br>`1 file changed, 50 insertions(+), 64 deletions(-)` |
| 2 | `python -m pytest tests/unit/test_memory_service.py -v` | `103 passed` |
| 3 | `python -m pytest tests/_helpers/test_mock_factory.py -v` | `8 passed` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13).` |
| 6 | `python -m bandit -r src/claude_memory -ll` | Verbatim Output:<br>```Test results: >> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces. Severity: Medium Location: src/claude_memory\embedding_server.py:148:26``` (Accepted baseline) |
| 7 | `python -m ruff check src/claude_memory tests scripts` | `All checks passed!` (with the invalid noqa warnings) |
| 8 | `git diff --name-only master..HEAD` | ✅ Matches exactly:<br>`process/PR_ISSUE_22D_HANDOFF.md`<br>`tests/unit/test_memory_service.py` (after Commit B is added) |
| 9 | Two-commit topology | ✅ Commit A (migration) and Commit B (handoff) successfully orchestrated |

---

## Verification Logs

### 1. Post-PR 4-Seed Sweep Output (Zero warnings across all 4 seeds):
```
=== seed=1 ===
============================ 103 passed in 9.50s ==============================
=== seed=2 ===
============================ 103 passed in 9.30s ==============================
=== seed=3 ===
============================ 103 passed in 9.40s ==============================
=== seed=4 ===
============================ 103 passed in 9.45s ==============================
```

### 2. Helper Mock Factory Tests Run Output:
```
tests/_helpers/test_mock_factory.py::test_sad_marker_threading_via_fixture PASSED [ 12%]
tests/_helpers/test_mock_factory.py::test_sad_allow_sync_keeps_magicmock_on_async_target PASSED [ 25%]
tests/_helpers/test_mock_factory.py::test_sad_override_replaces_dep PASSED [ 37%]
tests/_helpers/test_mock_factory.py::test_neutral_construction_succeeds PASSED [ 50%]
tests/_helpers/test_mock_factory.py::test_evil_activation_engine_methods_have_correct_types PASSED [ 62%]
tests/_helpers/test_mock_factory.py::test_evil_vector_store_is_asyncmock PASSED [ 75%]
tests/_helpers/test_mock_factory.py::test_evil_repo_is_asyncmock_with_async_methods PASSED [ 87%]
tests/_helpers/test_mock_factory.py::test_evil_sync_targets_are_magicmock PASSED [100%]
============================== 8 passed in 2.85s ==============================
```

### 3. `tox -e contracts` Run Output:
```
Dragon Brain Contract Scanner — Audit Edition
============================================================

Scanned 40 files. Found 13 violations.

By category:
  Bare Pass: 6
  Silent Fallback: 5
  Per-Item Swallow: 2

Report saved to contract_violations_report.md

SUCCESS: Violations (13) are within baseline (13).
  contracts: OK
```

### 4. Strict mypy Run Output:
```
Success: no issues found in 40 source files
```

### 5. Ruff Scan Output:
```
warning: Invalid `# noqa` directive on src\claude_memory\fts_store.py:224: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\clustering.py:54: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\crud_maintenance.py:144: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\date_parser.py:91: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:169: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:437: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\update_check.py:75: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\activation.py:194: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
```

### 6. Bandit Audit Run Output:
```
Run started:2026-06-25 19:18:36.688972+00:00

Test results:
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.9.3/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: src/claude_memory\embedding_server.py:148:26
147	    port = int(os.getenv("PORT", "8000"))
148	    uvicorn.run(app, host="0.0.0.0", port=port)  # noqa: S104
```
