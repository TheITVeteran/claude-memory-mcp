# Issue #14c — `test_hybrid_search.py` Async Mock Cleanup (Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14c
**Branch:** `issue-14c/test-hybrid-search-async-mocks` (from current master HEAD)
**Pattern:** Same Topographical Forcing blueprint as `14a` — see [`14a_BUILD_SPEC.md`](14a_BUILD_SPEC.md) for the full framework reference.

---

## Target

`tests/unit/test_hybrid_search.py` — 620 lines, 9 MagicMock sites. Two specific async-target sites identified at static-read time (Architect-enumerated).

**Acceptance (canonical pass/fail):**

```bash
python -m pytest tests/unit/test_hybrid_search.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

→ ZERO matches.

## Source-pattern audit (architect-provided, complete)

### Async-target sites (FIX REQUIRED)

| file:line | Current | Target async method | Fix |
|-----------|---------|--------------------|-----|
| `tests/unit/test_hybrid_search.py:58` | `svc.activation_engine.activate = MagicMock(return_value={})` | `ActivationEngine.activate` is **async** per inventory | `svc.activation_engine.activate = AsyncMock(return_value={})` |
| `tests/unit/test_hybrid_search.py:59` | `svc.activation_engine.spread = MagicMock(return_value={})` | `ActivationEngine.spread` is **async** per inventory | `svc.activation_engine.spread = AsyncMock(return_value={})` |

Note: lines 155-156 in the same file already correctly use `AsyncMock(return_value={...})` for the same methods in per-test overrides. The fixture inconsistency is the bug.

### Other MagicMock sites in file (verified sync-target — SKIP)

| Lines | Pattern | Target | Verdict |
|-------|---------|--------|---------|
| 33 | `mock_embedder = MagicMock()` | `EmbeddingService.encode` is sync | SKIP |
| 47-48 | `svc.fts_store = MagicMock()`, `.search = MagicMock(return_value=[])` | `FTSStore.search` is sync (sqlite) | SKIP |
| 49 | `svc.router = MagicMock(spec=QueryRouter)` | `QueryRouter.route` is sync | SKIP |
| 51 | `svc.reranker = MagicMock()` (overridden line 53 with AsyncMock for `.rerank`) | reranker container; specific async method overridden | SKIP |

## Golden diff template

```diff
-    svc.activation_engine.activate = MagicMock(return_value={})
-    svc.activation_engine.spread = MagicMock(return_value={})
+    svc.activation_engine.activate = AsyncMock(return_value={})
+    svc.activation_engine.spread = AsyncMock(return_value={})
```

Apply this exact transformation at lines 58-59.

## Assertion trap (architect-injected)

Inject this test at the TOP of `tests/unit/test_hybrid_search.py` (after imports, before existing tests):

```python
def test_meta_fixture_topology_required(service) -> None:
    """Topographical forcing: activation_engine methods must be AsyncMock.

    Architect-injected per process/issues/14c_BUILD_SPEC.md.
    DO NOT remove or weaken this test.
    """
    from unittest.mock import AsyncMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, AsyncMock), (
        "ActivationEngine.activate is async — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is async — must be AsyncMock"
    )
```

## Files in scope

- `tests/unit/test_hybrid_search.py` — modify lines 58-59 + add the meta-test
- `process/PR_ISSUE_14C_HANDOFF.md` — create after the fix

## Write-guard active

`process/issues/14_HARNESS.toml` denies modification to `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` on this branch.

## Two-commit topology, handoff structure, Round 5 discipline

Same as 14a/14b. **Specifically: use `tox -e contracts` (not `pytest -k contract`) for checklist item 5, and paste real ruff evidence.** 14a's audit flagged these as the only PARTIAL.
