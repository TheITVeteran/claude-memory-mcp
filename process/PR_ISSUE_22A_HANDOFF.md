# Issue #22a Handoff — mock_factory.py Helper Foundation

**Commit:** `fb8d4575483e72632766df33b69189810341b9b4`
**Branch:** `issue-22a/mock-factory-helper`
**Issue:** [#22a / parent #22](https://github.com/iikarus/Dragon-Brain/issues/22)

## Discovery findings

While implementing the dynamic mock factory helper, we successfully established an elegant class-introspection pattern to completely eliminate manual, error-prone MagicMock vs AsyncMock assignments in the test suite.

### Key Discoveries & Refinements:
1. **Introspection Branch Correctness:** Per the corrected master specification, `_build_typed_mock` dynamically handles three specific architectural branches based on class async dominance:
   - **Pure-async classes** (where all public methods are `async def`, like `AsyncMemoryRepository` or `VectorStore`) receive `AsyncMock(spec=cls)`. This ensures child method calls auto-generate coroutines cleanly.
   - **Mixed classes** (like `ActivationEngine`, which has async `spread` and sync `activate`/`detect_weak_connections`) receive `MagicMock(spec=cls)` with `AsyncMock` attributes explicitly assigned *only* for the async methods.
   - **Pure-sync classes** (like `FTSStore`) receive `MagicMock(spec=cls)` safely, preventing any unawaited coroutine leakage.
2. **Pytest Fixture Marker Threading:** The conftest fixture `mock_service_factory` extracts markers at runtime using `request.node.iter_markers(name="allow_sync_mock")` and safely threads them into `make_mock_service(allow_sync=...)` so tests can enforce sync behavior for specific call-paths if they need to assert pre-await topologies.

---

## Test-first evidence

Per Codex TDD criteria, each of the 8 unit tests was run individually against the pre-PR base branch to verify expected TDD failure patterns before implementation:

### 1. `test_evil_repo_is_asyncmock_with_async_methods`
```
=== test_evil_repo_is_asyncmock_with_async_methods ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 2. `test_evil_vector_store_is_asyncmock`
```
=== test_evil_vector_store_is_asyncmock ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 3. `test_evil_activation_engine_methods_have_correct_types`
```
=== test_evil_activation_engine_methods_have_correct_types ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 4. `test_evil_sync_targets_are_magicmock`
```
=== test_evil_sync_targets_are_magicmock ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 5. `test_sad_override_replaces_dep`
```
=== test_sad_override_replaces_dep ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 6. `test_sad_allow_sync_keeps_magicmock_on_async_target`
```
=== test_sad_allow_sync_keeps_magicmock_on_async_target ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 7. `test_sad_marker_threading_via_fixture`
```
=== test_sad_marker_threading_via_fixture ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

### 8. `test_neutral_construction_succeeds`
```
=== test_neutral_construction_succeeds ===
ImportError while loading conftest 'C:\Users\Asus\.gemini\antigravity\scratch\new_project\22a-pre-pr-base\tests\_helpers\conftest.py'.
tests\_helpers\conftest.py:15: in <module>
    from tests._helpers.mock_factory import make_mock_service
E   ModuleNotFoundError: No module named 'tests._helpers.mock_factory'
```

---

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat master..HEAD` | `process/PR_ISSUE_22A_HANDOFF.md   \| 109 ++++++++++++++++++++++++++++++++`<br>`tests/_helpers/__init__.py        \|   1 +`<br>`tests/_helpers/conftest.py        \|  43 +++++++++++++`<br>`tests/_helpers/mock_factory.py    \| 121 ++++++++++++++++++++++++++++++++++++`<br>`tests/_helpers/test_mock_factory.py \| 116 ++++++++++++++++++++++++++++++++++`<br>`5 files changed, 390 insertions(+)` |
| 2 | `python -m pytest tests/_helpers/test_mock_factory.py -v` | `8 passed in 2.69s` (All unit tests pass cleanly) |
| 3 | `python -m pytest tests/unit/ -q` | `1286 passed, 1 warning in 210.84s (0:03:30)` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13). concongratulations :)` |
| 6 | `python -m bandit -r src/claude_memory -ll` | Verbatim Output:<br>```Test results: >> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces. Severity: Medium Location: src/claude_memory\embedding_server.py:148:26``` (Accepted baseline) |
| 7 | `python -m ruff check src/claude_memory tests scripts` | `All checks passed!` (plus known invalid-noqa warnings in baseline) |
| 8 | `git diff --name-only master..HEAD` | ✅ Matches exactly after rebase:<br>`process/PR_ISSUE_22A_HANDOFF.md`<br>`tests/_helpers/__init__.py`<br>`tests/_helpers/conftest.py`<br>`tests/_helpers/mock_factory.py`<br>`tests/_helpers/test_mock_factory.py` |
| 9 | Two-commit topology | ✅ Commit A (implementation) and Commit B (handoff) successfully orchestrated |

---

## Verification Logs

### 1. `tox -e contracts` Run Output:
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
  contracts: OK (10.98=setup[10.73]+cmd[0.05,0.20] seconds)
  congratulations :) (11.05 seconds)
```

### 2. Full-scope Ruff (`python -m ruff check src/claude_memory tests scripts`) Output:
```
warning: Invalid `# noqa` directive on src\claude_memory\update_check.py:75: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:169: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\search_channels.py:437: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\clustering.py:54: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\crud_maintenance.py:144: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\date_parser.py:91: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\fts_store.py:224: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
warning: Invalid `# noqa` directive on src\claude_memory\activation.py:194: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
```

### 3. `python -m bandit -r src/claude_memory -ll` Run Output:
```
[main]	INFO	running on Python 3.12.10
Run started:2026-05-28 13:18:19.335841+00:00

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
