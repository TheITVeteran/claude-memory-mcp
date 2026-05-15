# PR-5: Channel Degradation Surfaced Through MCP

## 1. Commit Information
**Commit Hash:** `d1f2bd2d81cadb65369f3f191e3598f03db7f1cf`
**Branch:** `remediation/pr-5-channel-metadata`

## 2. Objective
Finalize PR-5 to eliminate TOCTOU architectural risks by surfacing per-channel search health metadata and temporal stats directly in the `search()` return payload instead of relying on `self._last_*` instance attributes.

## 3. Implementation Details
* **Payload Refactor:** Updated `MemoryService.search()` to return a dictionary containing both `"results"` (list of `SearchResult`) and `"metadata"` (a dict with temporal stats and per-channel health metrics).
* **Backward Compatibility:** Updated `search_memory` in `server.py`. When `include_meta=False`, the response is stripped to just the `"results"` list to preserve existing behavior. When `include_meta=True`, the full metadata envelope is returned via the `HybridSearchResponse` schema.
* **Internal Callers Updated:** Updated internal calls in `router.py` (semantic fallbacks) and `search_advanced.py` (hologram anchors) to correctly extract the results array from the new dict payload structure.
* **State Elimination:** Removed all `self._last_*` shared state mutations from `MemoryService`, resolving the concurrent access TOCTOU risk.
* **Test-First Discipline:** Implemented `tests/unit/test_channel_degradation.py` containing a 5-row regression test design (3 evil, 1 sad, 1 neutral) verifying metadata existence, state elimination, and backward compatibility. RED phase failure output was successfully captured prior to implementation.
* **TDD Remediation:** Handled comprehensive test updates across `test_memory_service.py`, `test_tools_coverage.py`, `test_hybrid_search.py`, and `test_router.py` to adapt to the new dictionary signature and pass the strict CI gate.

## 4. Verification & Hygiene
* **Test Suite:** The 208-test unit regression suite successfully passes (100% GREEN).
* **Contract Scanner:** Executed `trace_contracts_dragon.py`. Output verified at exactly 75 baseline violations, representing a zero-delta contract state post-PR.
* **Linting & Formatting:** Validated code quality through Ruff and pre-commit checks.

## 5. Codex Audit Preparedness
This stable, validated artifact fulfills the updated handoff requirements specified in `REMEDIATION_BUILD_SPEC.md` and aligns with the test-first verification methodology mandated by `REMEDIATION_AUDIT_SPEC.md`. Ready for Codex review and integration.
