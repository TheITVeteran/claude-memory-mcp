# Issue #22a — Build `mock_factory.py` Helper (Build Spec)

**Issue:** parent issue #22 (to be filed) — sub-chunk 22a (the foundational helper).
**Branch:** `issue-22a/mock-factory-helper` (from current master HEAD)
**Pattern:** Topographical Forcing per `14a_BUILD_SPEC.md`. Greenfield build, no migration in this PR.

---

## Target

Build a single helper module `tests/_helpers/mock_factory.py` that constructs a `MemoryService` instance with type-correct mocks for every dependency. The helper introspects each dependency class via `inspect.iscoroutinefunction()` to decide AsyncMock vs MagicMock per method automatically — eliminating the hand-rolled decision point that has caused every async-mock bug in the issue #14 arc.

**Scope:** the helper + its unit tests. NO migrations to it in this PR (those are 22b-22e).

## Files in scope

- **New:** `tests/_helpers/__init__.py` (empty package marker)
- **New:** `tests/_helpers/mock_factory.py` (~150 LoC — the helper)
- **New:** `tests/_helpers/conftest.py` (~30 LoC — pytest fixture wrapper)
- **New:** `tests/_helpers/test_mock_factory.py` (~200 LoC — 8 tests)
- **New:** `process/PR_ISSUE_22A_HANDOFF.md` (after the build)

## Concrete fix (architect-prescribed implementation)

### `tests/_helpers/mock_factory.py`

```python
"""Type-correct mock factory for MemoryService and its dependencies.

Eliminates hand-rolled MagicMock-vs-AsyncMock decisions per attribute. Uses
inspect.iscoroutinefunction() on the actual dependency classes to AsyncMock
async methods and MagicMock sync methods automatically.

Per process/issues/22a_BUILD_SPEC.md — the structural fix for the bug class
documented across issue #14a through #14e.
"""
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from claude_memory.tools import MemoryService


def _build_typed_mock(cls: type | None, *, spec: bool = True) -> MagicMock:
    """Build a Mock where async methods become AsyncMock automatically.

    Inspects cls's methods via inspect.iscoroutinefunction(). Methods detected
    as async get AsyncMock attached; sync methods stay as MagicMock defaults.
    """
    mock = MagicMock(spec=cls) if (cls and spec) else MagicMock()
    if cls is None:
        return mock
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if attr is None:
            continue
        if inspect.iscoroutinefunction(attr):
            setattr(mock, name, AsyncMock())
    return mock


def make_mock_service(
    *,
    embedding_service: MagicMock | None = None,
    allow_sync: list[str] | None = None,
    **overrides: MagicMock,
) -> "MemoryService":
    """Construct a MemoryService with type-correct mocks for every dependency.

    Args:
        embedding_service: Optional explicit Embedder mock. If None, a default
            MagicMock with encode.return_value = [0.1, 0.2, 0.3] is built.
        allow_sync: List of dotted attribute paths that should remain MagicMock
            even if the underlying method is async (e.g. ["repo.create_node"]).
            For tests that intentionally verify pre-await behavior. Use sparingly
            — pairs with @pytest.mark.allow_sync_mock for code-review visibility.
        **overrides: Replace specific top-level dependency attributes with
            caller-provided mocks (e.g. ``repo=my_custom_async_mock``).

    Returns:
        A fully-mocked MemoryService instance ready for tests. Async methods on
        repo, vector_store, activation_engine, reranker are AsyncMock by default.
        Sync targets (fts_store, ontology, context_manager, router) are MagicMock.
    """
    # Patch infrastructure constructors that would fail without real deps
    with patch("claude_memory.repository.FalkorDB"), \
         patch("claude_memory.lock_manager.redis.Redis"), \
         patch("claude_memory.vector_store.AsyncQdrantClient"):
        from claude_memory.tools import MemoryService

        if embedding_service is None:
            embedding_service = MagicMock()
            embedding_service.encode.return_value = [0.1, 0.2, 0.3]

        svc = MemoryService(embedding_service=embedding_service)

    # Import dependency classes for introspection
    from claude_memory.activation import ActivationEngine
    from claude_memory.context_manager import ContextManager
    from claude_memory.fts_store import FTSStore
    from claude_memory.lock_manager import LockManager
    from claude_memory.ontology import OntologyManager
    from claude_memory.reranker import RerankerClient
    from claude_memory.repository_async import AsyncMemoryRepository
    from claude_memory.router import QueryRouter
    from claude_memory.vector_store import VectorStore

    allow_sync_set = set(allow_sync or [])

    # Build type-correct mocks for each dependency
    dep_classes = {
        "repo": AsyncMemoryRepository,
        "vector_store": VectorStore,
        "fts_store": FTSStore,
        "reranker": RerankerClient,
        "router": QueryRouter,
        "ontology": OntologyManager,
        "context_manager": ContextManager,
        "lock_manager": LockManager,
        "activation_engine": ActivationEngine,
    }
    for attr, cls in dep_classes.items():
        if attr in overrides:
            setattr(svc, attr, overrides[attr])
            continue
        # Build the typed mock — async methods become AsyncMock
        mock = _build_typed_mock(cls)
        # Apply allow_sync overrides for explicit sync-mock-on-async-target paths
        for path in allow_sync_set:
            parts = path.split(".")
            if parts[0] == attr and len(parts) >= 2:
                # Override the specific nested method back to MagicMock
                target_method = parts[1]
                setattr(mock, target_method, MagicMock())
        setattr(svc, attr, mock)

    # activation_engine.repo must point at the (mocked) repo
    svc.activation_engine.repo = svc.repo

    return svc
```

### `tests/_helpers/conftest.py`

```python
"""Pytest fixtures exposing make_mock_service to test files.

Per process/issues/22a_BUILD_SPEC.md.
"""
from __future__ import annotations

import pytest

from tests._helpers.mock_factory import make_mock_service


@pytest.fixture()
def mock_service_factory(request: pytest.FixtureRequest):
    """Return a pre-configured mock_service_factory.

    Reads @pytest.mark.allow_sync_mock markers from the calling test and threads
    them into make_mock_service's allow_sync param. Tests using marker syntax
    don't need to pass allow_sync explicitly.
    """
    allow_sync: list[str] = []
    for marker in request.node.iter_markers(name="allow_sync_mock"):
        allow_sync.extend(marker.args)

    def _factory(**overrides) -> "MemoryService":
        return make_mock_service(allow_sync=allow_sync, **overrides)

    return _factory


def pytest_configure(config: pytest.Config) -> None:
    """Register the allow_sync_mock marker for visibility in pytest --markers."""
    config.addinivalue_line(
        "markers",
        "allow_sync_mock(*paths): Explicitly allow MagicMock for the named "
        "async-target attribute paths (e.g. 'repo.create_node'). For tests "
        "verifying pre-await production behavior. Visible in code review.",
    )
```

### `tests/_helpers/test_mock_factory.py` — required tests

3 evil + 1 sad + 1 neutral pattern. All listed sites have pre-PR/post-PR behavior documented:

| Test | Category | What it verifies | Pre-PR | Post-PR |
|------|----------|------------------|--------|---------|
| `test_evil_repo_is_asyncmock_with_async_methods` | evil | `svc.repo` is AsyncMock; `await svc.repo.get_node("x")` returns the configured coroutine value | TEST FAILS (helper doesn't exist) | TEST PASSES |
| `test_evil_vector_store_is_asyncmock` | evil | `svc.vector_store` is AsyncMock; async methods coroutine-correctly | TEST FAILS | TEST PASSES |
| `test_evil_activation_engine_methods_have_correct_types` | evil | `svc.activation_engine.spread` is AsyncMock (async def per `src/claude_memory/activation.py:98`); `svc.activation_engine.activate` is MagicMock (sync def at `:76`); `svc.activation_engine.detect_weak_connections` is MagicMock (sync def at `:264`). Architect inventory was corrected 2026-05-28 after AG flagged the discrepancy at plan stage. | TEST FAILS | TEST PASSES |
| `test_evil_sync_targets_are_magicmock` | evil | `svc.fts_store` is MagicMock; `svc.fts_store.search` is sync-callable | TEST FAILS | TEST PASSES |
| `test_sad_override_replaces_dep` | sad | `make_mock_service(repo=my_mock)` uses provided mock instead of factory-default | TEST FAILS | TEST PASSES |
| `test_sad_allow_sync_keeps_magicmock_on_async_target` | sad | `make_mock_service(allow_sync=["repo.get_node"])` keeps `repo.get_node` as MagicMock despite being async | TEST FAILS | TEST PASSES |
| `test_sad_marker_threading_via_fixture` | sad | A test with `@pytest.mark.allow_sync_mock("repo.create_node")` using `mock_service_factory()` gets MagicMock at that path | TEST FAILS | TEST PASSES |
| `test_neutral_construction_succeeds` | neutral | `make_mock_service()` returns a MemoryService instance with no errors | TEST FAILS (ImportError on helper) | TEST PASSES |

**Test-first evidence required:** All 8 tests must capture verbatim pre-PR failure output (run in worktree at pre-PR base, copy test file in, run). Document in handoff "Test-first evidence" section.

## The bar (Codex will verify)

- (a) `tests/_helpers/mock_factory.py` exists with `make_mock_service()` and `_build_typed_mock()` per spec
- (b) `tests/_helpers/conftest.py` exports `mock_service_factory` fixture + registers `allow_sync_mock` marker
- (c) All 8 unit tests pass at the new code; all 8 fail on pre-PR base (test-first evidence in handoff)
- (d) `make_mock_service()` introspection is correct: `svc.repo` IS `AsyncMock`, `svc.fts_store` IS `MagicMock`, etc. (verify via runtime `isinstance()` checks in tests, not via grep of source)
- (e) `tox -e contracts` — delta = 0 from current master baseline
- (f) `mypy --strict src/claude_memory` still passes (no source-layer changes)
- (g) `ruff check src/claude_memory tests scripts` clean
- (h) Pre-handoff checklist complete with real evidence (no `N/A` shortcuts, `tox -e contracts` not `pytest -k`)
- (i) Two-commit topology per checklist item 1

## Out of scope (do NOT do in this PR)

- Do NOT migrate any existing test file to use the helper — that's 22b through 22e
- Do NOT modify ANY file outside `tests/_helpers/` and `process/PR_ISSUE_22A_HANDOFF.md`
- Do NOT remove the autouse suppression fixtures from existing test files — those go in the per-file migration PRs (22b-22e)
- Do NOT add the contract scanner Pattern 12 — that's 22f

Write-guard via `process/issues/22_HARNESS.toml` enforces these constraints physically.

## Round 5 discipline

If introspection edge cases surface during build (e.g., `ActivationEngine.repo` is an attribute, not a method, and shouldn't be AsyncMock-ed) — escalate to architect for spec refinement before inventing solutions. The helper's correctness is the whole point of the issue #22 series; getting it right in 22a unblocks everything downstream.
