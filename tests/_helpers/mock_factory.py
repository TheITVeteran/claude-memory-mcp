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


def _build_typed_mock(cls: type | None, *, spec: bool = True) -> MagicMock | AsyncMock:
    """Build a Mock whose OUTER type matches the class's async dominance.

    Logic:
      - cls is None → plain MagicMock (no introspection possible)
      - cls is pure-async (every public method is `async def`) → outer is AsyncMock(spec=cls).
        AsyncMock auto-creates AsyncMock children, so methods not explicitly
        introspected still behave correctly when awaited. Safer for evolving classes.
      - cls is mixed or pure-sync → outer is MagicMock(spec=cls), with AsyncMock
        explicitly attached per async method. Prevents spurious coroutines on sync
        method calls (e.g., ActivationEngine.activate is sync, must stay MagicMock).

    Args:
        cls: The dependency class to introspect, or None.
        spec: Whether to apply `spec=cls` to the outer mock (default True for
              attribute-error safety).

    Returns:
        AsyncMock(spec=cls) for pure-async classes, MagicMock(spec=cls) otherwise
        with per-async-method AsyncMock attribute assignments.
    """
    if cls is None:
        return MagicMock()

    # Enumerate public callables on the class
    public_callables: list[tuple[str, Any]] = []
    async_method_names: list[str] = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if attr is None or not callable(attr):
            continue
        public_callables.append((name, attr))
        if inspect.iscoroutinefunction(attr):
            async_method_names.append(name)

    # Pure-async: outer = AsyncMock(spec=cls). AsyncMock auto-coroutines all child calls.
    if public_callables and len(async_method_names) == len(public_callables):
        return AsyncMock(spec=cls) if spec else AsyncMock()

    # Mixed or pure-sync: outer = MagicMock(spec=cls), AsyncMock attached per async method.
    mock = MagicMock(spec=cls) if spec else MagicMock()
    for name in async_method_names:
        setattr(mock, name, AsyncMock())
    return mock


def make_mock_service(
    *,
    embedding_service: MagicMock | None = None,
    allow_sync: list[str] | None = None,
    **overrides: MagicMock,
) -> MemoryService:
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
    with (
        patch("claude_memory.repository.FalkorDB"),
        patch("claude_memory.lock_manager.redis.Redis"),
        patch("claude_memory.vector_store.AsyncQdrantClient"),
    ):
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
    from claude_memory.repository_async import AsyncMemoryRepository
    from claude_memory.reranker import RerankerClient
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
