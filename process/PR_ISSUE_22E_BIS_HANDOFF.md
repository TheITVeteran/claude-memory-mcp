# Issue #22e-bis Handoff — Migrate 2 Contract-Test Files to `make_mock_service()`

**Commit:** `5190cad8832a6a933997406ffcd3eee25c1debaf`
**Branch:** `issue-22e-bis/contract-tests-migration`
**Issue:** [#22e-bis / parent #22](https://github.com/iikarus/Dragon-Brain/issues/22)

## Discovery findings

While migrating the 2 remaining contract-test files (`test_batch3_contracts.py` and `test_batch5_contracts.py`) to use `make_mock_service()`, we performed post-migration scans for async method replacements (Transformation 7). We verified:
1. Running the scan `git grep -nE "service\.\w+\.\w+ = (AsyncMock|MagicMock)\("` returned exactly 0 matches across both files.
2. In `test_batch3_contracts.py`:
   - Replaced the hand-rolled `search_service` fixture with `make_mock_service(embedding_service=embedder)`.
   - Eliminated the hand-rolled bug-class pattern: `service.activation_engine = MagicMock()`.
   - Preserved `service.repo.client.select_graph.return_value = MagicMock()` by configuring the return value on the helper-built `AsyncMock` client hierarchy instead of overwriting the client with a bare `MagicMock` (which would trigger method replacement warnings).
   - Pre-configured `activation_engine` mocks (`activate.return_value = {}`, `spread.return_value = {}`) and `repo` mocks (`get_subgraph.return_value = {"nodes": [], "edges": []}`) to prevent unawaited coroutine iteration warnings when they are evaluated in iterable or dictionary contexts.
3. In `test_batch5_contracts.py`:
   - Created a module-level `service` fixture utilizing `make_mock_service()`.
   - Threaded the `service` fixture through all 10 test methods, completely removing 10 inline `MemoryService` constructions and 20 duplicate `svc.repo = AsyncMock()` typos.
   - Preserved the lock manager context manager by configuring `.lock.return_value = lock_ctx` on the helper-built mock rather than replacing `svc.lock_manager` with a bare `MagicMock` (which destroys mock introspection).

---

## Test-first evidence

Pre-PR baseline warning behavior (captured against master HEAD `c73834d`):

Pre-PR baseline shows clean output — these files lack the `_drain_orphan_coroutines` suppression but their hand-rolled fixtures have bug-class patterns (test_batch3's `activation_engine = MagicMock()`, test_batch5's 20 duplicate `svc.repo = AsyncMock()` typos) that don't currently emit warnings because the test code paths don't exercise the bug class in awaited contexts. The migration replaces hand-rolled patterns with helper-introspected correct types AND adds forcing tests that would fail-loud on any regression.

### 4-Seed Pre-PR Sweep
```
######## test_batch3_contracts.py ########
=== seed=1 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil2_channel_status_invalid_status PASSED [ 81%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil1_channel_status_serialization PASSED [ 90%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil3_channel_status_missing_channel PASSED [100%]

============================= 11 passed in 13.58s =============================
=== seed=2 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_sad1_channel_status_defaults PASSED [ 81%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_degraded PASSED [ 90%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_ok PASSED [100%]

============================= 11 passed in 13.84s =============================
=== seed=3 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil1_channel_status_serialization PASSED [ 81%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_ok PASSED [ 90%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_sad1_channel_status_defaults PASSED [100%]

============================= 11 passed in 13.90s =============================
=== seed=4 ===
tests/unit/test_batch3_contracts.py::test_happy_channel_status_with_results PASSED [ 81%]
tests/unit/test_batch3_contracts.py::test_evil1_channel_failure_visible_in_status PASSED [ 90%]
tests/unit/test_batch3_contracts.py::test_evil3_all_channels_ok_when_healthy PASSED [100%]

============================= 11 passed in 14.13s =============================
######## test_batch5_contracts.py ########
=== seed=1 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [ 80%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_happy_delete_relationship_basic PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_sad1_delete_relationship_returns_status PASSED [100%]

============================= 10 passed in 23.17s =============================
=== seed=2 ===
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_evil3_add_observation_lock_correct_project PASSED [ 80%]
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_happy_add_observation_with_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_evil1_add_observation_acquires_lock PASSED [100%]

============================= 10 passed in 23.55s =============================
=== seed=3 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [ 80%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil1_delete_relationship_acquires_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil2_delete_relationship_without_project_still_executes PASSED [100%]

============================= 10 passed in 23.15s =============================
=== seed=4 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil2_delete_relationship_without_project_still_executes PASSED [ 80%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil1_delete_relationship_acquires_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [100%]

============================= 10 passed in 23.25s =============================
```

---

## Pre-handoff checklist

| # | Gate | Evidence |
|---|------|----------|
| 1 | `git diff --stat master..HEAD` | `tests/unit/test_batch3_contracts.py \|  74 ++++---`<br>`tests/unit/test_batch5_contracts.py \| 406 ++++++++++++++++--------------------`<br>`2 files changed, 233 insertions(+), 247 deletions(-)` |
| 2 | `python -m pytest tests/unit/test_batch3_contracts.py tests/unit/test_batch5_contracts.py -v` | `23 passed` |
| 3 | `python -m pytest tests/_helpers/test_mock_factory.py -v` | `8 passed` |
| 4 | `python -m mypy --strict src/claude_memory` | `Success: no issues found in 40 source files` |
| 5 | `tox -e contracts` | `SUCCESS: Violations (13) are within baseline (13).` |
| 6 | `python -m bandit -r src/claude_memory -ll` | Verbatim Output:<br>```Test results: >> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces. Severity: Medium Location: src/claude_memory\embedding_server.py:148:26``` (Accepted baseline) |
| 7 | `python -m ruff check src/claude_memory tests scripts` | `All checks passed!` |
| 8 | `git diff --name-only master..HEAD` | ✅ Matches exactly:<br>`tests/unit/test_batch3_contracts.py`<br>`tests/unit/test_batch5_contracts.py` |
| 9 | Two-commit topology | ✅ Commit A (migration) and Commit B (handoff) successfully orchestrated |

---

## Verification Logs

### 1. Post-PR 8-Seed Sweep Output (Zero warnings across all 8 runs):
```
######## test_batch3_contracts.py ########
=== seed=1 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil2_channel_status_invalid_status PASSED [ 83%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil1_channel_status_serialization PASSED [ 91%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil3_channel_status_missing_channel PASSED [100%]

============================= 12 passed in 3.89s ==============================
=== seed=2 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_sad1_channel_status_defaults PASSED [ 83%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_degraded PASSED [ 91%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_ok PASSED [100%]

============================= 12 passed in 3.74s ==============================
=== seed=3 ===
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_evil1_channel_status_serialization PASSED [ 83%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_happy_channel_status_ok PASSED [ 91%]
tests/unit/test_batch3_contracts.py::TestChannelStatusSchema::test_sad1_channel_status_defaults PASSED [100%]

============================= 12 passed in 3.64s ==============================
=== seed=4 ===
tests/unit/test_batch3_contracts.py::test_happy_channel_status_with_results PASSED [ 83%]
tests/unit/test_batch3_contracts.py::test_evil1_channel_failure_visible_in_status PASSED [ 91%]
tests/unit/test_batch3_contracts.py::test_evil3_all_channels_ok_when_healthy PASSED [100%]

============================= 12 passed in 3.67s ==============================
######## test_batch5_contracts.py ########
=== seed=1 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [ 81%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_happy_delete_relationship_basic PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_sad1_delete_relationship_returns_status PASSED [100%]

============================= 11 passed in 2.79s ==============================
=== seed=2 ===
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_evil3_add_observation_lock_correct_project PASSED [ 81%]
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_happy_add_observation_with_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestAddObservationLocking::test_evil1_add_observation_acquires_lock PASSED [100%]

============================= 11 passed in 3.00s ==============================
=== seed=3 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [ 81%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil1_delete_relationship_acquires_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil2_delete_relationship_without_project_still_executes PASSED [100%]

============================= 11 passed in 2.84s ==============================
=== seed=4 ===
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil2_delete_relationship_without_project_still_executes PASSED [ 81%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil1_delete_relationship_acquires_lock PASSED [ 90%]
tests/unit/test_batch5_contracts.py::TestDeleteRelationshipLocking::test_evil3_delete_relationship_lock_uses_correct_project PASSED [100%]

============================= 11 passed in 2.74s ==============================
