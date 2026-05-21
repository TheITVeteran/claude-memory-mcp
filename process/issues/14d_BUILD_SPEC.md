# Issue #14d — `test_embedding_filter.py` Async Mock Cleanup (Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14d
**Branch:** `issue-14d/test-embedding-filter-hologram-cleanup` (from current master HEAD)
**Pattern:** Same Topographical Forcing blueprint as `14a`/`14b`/`14c` — see [`14a_BUILD_SPEC.md`](14a_BUILD_SPEC.md) for the full framework reference. This spec is file+test-specific.

---

## Target

**Single test in single file:** `tests/unit/test_embedding_filter.py::test_happy_get_hologram_strips_embedding`

The full-suite strict-gate verification (2026-05-21) confirmed this is the lone remaining `RuntimeWarning: coroutine` emission site after 14a/b/c merged. Codex's verification agent identified it specifically. Architect static reading of the file (177 lines) shows the fixture uses `AsyncMock` correctly for `repo` and `vector_store`; the leak is somewhere in this specific test's body or its production-code interaction.

**Acceptance (canonical pass/fail):**

```bash
python -m pytest tests/unit/test_embedding_filter.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

→ ZERO matches.

**Plus the full-suite check (true closure of issue #14):**

```bash
python -m pytest tests/unit/ -W error::RuntimeWarning -q --tb=no 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

→ ZERO matches. This is the criterion that closes issue #14 for real.

## Async-signature inventory

Reuse from `14a_BUILD_SPEC.md` § "Async signature inventory" — same `MemoryService`, `AsyncMemoryRepository`, `VectorStore`, etc.

## Discovery loop (scoped to one test)

The file is small (177 lines) and only ONE test is the warning source. Run it in isolation under strict gate to capture the warning context:

```bash
python -m pytest tests/unit/test_embedding_filter.py::test_happy_get_hologram_strips_embedding \
    -W error::RuntimeWarning -v 2>&1 | tee /tmp/14d_strict.log
```

Likely sites to check (architect hypothesis, not guaranteed):
- Line 142: `anchor_mock = MagicMock()` — if this represents a SearchResult that has async methods, switch to AsyncMock
- Line 146: `mock_service.search = AsyncMock(return_value=[anchor_mock])` — replacing real async method, looks correct
- Line 147: `mock_service.repo.get_subgraph.return_value = {...}` — `get_subgraph` is async; setting `.return_value` on the AsyncMock-attribute is the right pattern
- Line 151: `mock_service.context_manager = MagicMock()` — `ContextManager.optimize` is sync per inventory, so MagicMock is correct
- Line 152: `mock_service.context_manager.optimize.return_value = [...]` — correct, sync target

If the static analysis doesn't reveal the leak, run the test, capture the verbatim warning output, and inspect the traceback to find the source. Same empirical-discovery procedure as 14a.

## Golden diff template

Same as 14a's pattern:

```diff
-mock_service.<something> = MagicMock()
+mock_service.<something> = AsyncMock()
```

OR a missing `await`:

```diff
-result = mock_service.<async_method>()
+result = await mock_service.<async_method>()
```

Apply at the discovered site(s).

## Assertion trap (architect-injected)

Add this test to the TOP of `tests/unit/test_embedding_filter.py` (after imports, before existing tests):

```python
def test_meta_fixture_topology_required(mock_service) -> None:
    """Topographical forcing: fixture must use AsyncMock for async-target attributes.

    Architect-injected per process/issues/14d_BUILD_SPEC.md.
    DO NOT remove or weaken this test.
    """
    from unittest.mock import AsyncMock

    assert isinstance(mock_service.repo, AsyncMock), (
        "mock_service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(mock_service.vector_store, AsyncMock), (
        "mock_service.vector_store has async methods — must be AsyncMock"
    )
```

## Files in scope

- `tests/unit/test_embedding_filter.py` — modify the specific test (likely 1-3 line change) + add the meta-test
- `process/PR_ISSUE_14D_HANDOFF.md` — create after the fix

## Write-guard active

`process/issues/14_HARNESS.toml` denies modification to `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini` on this branch. Now fires correctly post-regex-fix.

## Two-commit topology, handoff structure, Round 5 discipline

Same as 14b/14c — use `tox -e contracts` (NOT `pytest -k contract`), paste real ruff evidence, full 9-item checklist with no "N/A" shortcuts.

## Definition of done

Both canonical strict-gate checks return ZERO matches:
1. `pytest tests/unit/test_embedding_filter.py -W error::RuntimeWarning` — file-level
2. `pytest tests/unit/ -W error::RuntimeWarning` — full-suite

When both clean, issue #14 can be closed for real.
