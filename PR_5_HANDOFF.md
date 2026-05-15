# PR-5 Handoff: Channel Degradation Surfaced Through MCP

## Branch
`remediation/pr-5-channel-metadata`

## Commit Hash
`333a8eba6bde3f593cc3d503faa540f9131da0bd`

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
- `tests/integration/test_db_kill_scenarios.py`
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
- **MCP Server Compatibility**: The `search_memory` tool dynamically strips the metadata envelope when `include_meta=False`, ensuring older clients reliant on the list return shape continue to function properly. The "No results found." shortcut string was removed to ensure metadata is accurately surfaced for empty results.
- **Test Race Condition Fixed**: Corrected a test suite race condition in the concurrent execution test, ensuring isolated tracking of query states by analyzing the query parameter instead of using a global call counter.

## Test-First Evidence
All four failing tests were run against the pre-PR base (`c127865`). As expected, they failed because the old architecture lacked the `channels` metadata, lacked the dict response shape, or returned the `"No results found."` string.

### 1. `test_neutral_service_returns_dict_shape`
Failed because the old architecture returned a plain list instead of a metadata dictionary envelope.
```text
___________________ test_neutral_service_returns_dict_shape ___________________
tests\integration\test_spec_pr5.py:139: in test_neutral_service_returns_dict_shape
    assert isinstance(result, dict)
E   assert False
E    +  where False = isinstance([], dict)
```

### 2. `test_evil_kill_fts_mid_search`
Failed because it returned the "No results found." string, resulting in a TypeError when trying to access metadata.
```text
________________________ test_evil_kill_fts_mid_search ________________________
tests\integration\test_spec_pr5.py:78: in test_evil_kill_fts_mid_search
    assert result["meta"]["channels"]["fts"] == "failed"
           ^^^^^^^^^^^^^^
E   TypeError: string indices must be integers, not 'str'
```

### 3. `test_evil_kill_qdrant_mid_search`
Failed because killing Qdrant mid-search raised a raw exception that crashed the pipeline instead of degrading gracefully.
```text
___________________ test_evil_kill_qdrant_mid_search ___________________
tests\integration\test_spec_pr5.py:86: in test_evil_kill_qdrant_mid_search
    result = await search_memory(query="test", include_meta=True)
C:\Users\Asus\AppData\Local\Programs\Python\Python312\Lib\site-packages\qdrant_client\http\api_client.py:225: in send_inner
    raise ResponseHandlingException(e)
E   qdrant_client.http.exceptions.ResponseHandlingException
```

### 4. `test_evil_concurrent_search_no_crosstalk`
Failed because the lack of dictionary response caused a list index error when trying to access `metadata`.
```text
__________________ test_evil_concurrent_search_no_crosstalk ___________________
tests\integration\test_spec_pr5.py:115: in test_evil_concurrent_search_no_crosstalk
    assert r1["metadata"]["channels"]["fts"] == "failed"
           ^^^^^^^^^^^^^^
E   TypeError: list indices must be integers or slices, not str
```

## Readiness
The implementation achieves 100% test pass rate across the required scenarios (3-evil/1-sad/1-neutral), adhering strictly to the architectural constraints outlined in the BUILD spec. Ready for Codex audit.
