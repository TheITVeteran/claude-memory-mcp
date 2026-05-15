# PR-5 Handoff: Channel Degradation Surfaced Through MCP

## Branch
`remediation/pr-5-channel-metadata`

## Commit Hash
`b0085dce699cb53c82ed1526c0f5c3dd5316f138`

## Diff Summary
The following files were modified to implement channel degradation and dictionary envelope response, or swept up via doc updates:
- `PR_5_HANDOFF.md`
- `REMEDIATION_AUDIT_SPEC.md`
- `REMEDIATION_BUILD_SPEC.md`
- `src/claude_memory/router.py`
- `src/claude_memory/schema.py`
- `src/claude_memory/search.py`
- `src/claude_memory/search_advanced.py`
- `src/claude_memory/search_channels.py`
- `src/claude_memory/server.py`
- `tests/integration/test_spec_pr5.py`
- `tests/unit/test_channel_degradation.py`
- `tests/unit/test_hybrid_search.py`
- `tests/unit/test_memory_service.py`
- `tests/unit/test_router.py`
- `tests/unit/test_server.py`
- `tests/unit/test_tools_coverage.py`

## Implementation Notes
- **Return Shape**: `MemoryService.search()` now returns a dict containing `results` and `metadata`, allowing us to track channel health cleanly per call and eliminating `self._last_channel_status` TOCTOU risks.
- **Graceful Degradation**: Wrapped integration points (FTS, Qdrant, Temporal, Relational, Hydration) in `try-except` blocks. Connection errors no longer crash the pipeline; they correctly degrade the specific channel's metadata to `"failed"` or `"degraded"`.
- **MCP Server Compatibility**: The `search_memory` tool dynamically strips the metadata envelope when `include_meta=False`, ensuring older clients reliant on the list return shape continue to function properly.
- **Test Race Condition Fixed**: Corrected a test suite race condition in the concurrent execution test, ensuring isolated tracking of query states by analyzing the query parameter instead of using a global call counter.

## Test-First Evidence
The integration test `test_neutral_service_returns_dict_shape` was run against the pre-PR base (`c127865`). As expected, it failed with `isinstance([], dict)` because the old architecture returned a list instead of a metadata dictionary envelope.

```text
================================== FAILURES ===================================
___________________ test_neutral_service_returns_dict_shape ___________________

memory_service = <claude_memory.tools.MemoryService object at 0x00000212BE612BA0>

    @pytest.mark.asyncio
    async def test_neutral_service_returns_dict_shape(memory_service):
        result = await memory_service.search(SearchMemoryParams(query="test"))
>       assert isinstance(result, dict)
E       assert False
E        +  where False = isinstance([], dict)

tests\integration\test_spec_pr5.py:127: AssertionError
=========================== short test summary info ===========================
FAILED tests/integration/test_spec_pr5.py::test_neutral_service_returns_dict_shape - assert False
```

## Readiness
The implementation achieves 100% test pass rate across the required scenarios (3-evil/1-sad/1-neutral), adhering strictly to the architectural constraints outlined in the BUILD spec. Ready for Codex audit.
