"""Unit tests for mock_factory.py and its pytest conftest fixture.

Per process/issues/22a_BUILD_SPEC.md. Ensures mock_factory creates
type-correct MagicMocks and AsyncMocks for MemoryService dependencies.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests._helpers.mock_factory import make_mock_service


def test_neutral_construction_succeeds() -> None:
    """Verifies that make_mock_service constructs a MemoryService instance."""
    svc = make_mock_service()
    assert svc is not None
    # Verify the class is MemoryService
    assert svc.__class__.__name__ == "MemoryService"


def test_evil_repo_is_asyncmock_with_async_methods() -> None:
    """Verifies that svc.repo is an AsyncMock and its async methods can be awaited."""
    svc = make_mock_service()

    # Assert outer type matches the class's async dominance
    assert isinstance(svc.repo, AsyncMock)
    assert isinstance(svc.repo.get_node, AsyncMock)

    # Configure and await a return value to verify coroutine correctness
    expected = {"id": "test-node", "name": "Test Node"}
    svc.repo.get_node.return_value = expected

    async def run_test() -> None:
        result = await svc.repo.get_node("test-node")
        assert result == expected

    import asyncio

    asyncio.run(run_test())


def test_evil_vector_store_is_asyncmock() -> None:
    """Verifies that vector_store async methods are AsyncMocks and coroutine-correct."""
    svc = make_mock_service()
    assert isinstance(svc.vector_store, AsyncMock)
    assert isinstance(svc.vector_store.upsert, AsyncMock)
    assert isinstance(svc.vector_store.search, AsyncMock)

    svc.vector_store.search.return_value = [{"_id": "123"}]

    async def run_test() -> None:
        res = await svc.vector_store.search(vector=[0.1, 0.2], limit=5)
        assert res == [{"_id": "123"}]

    import asyncio

    asyncio.run(run_test())


def test_evil_activation_engine_methods_have_correct_types() -> None:
    """Verifies that activation_engine methods have their correct types per the production source."""
    svc = make_mock_service()
    assert isinstance(svc.activation_engine.spread, AsyncMock)  # async def
    assert isinstance(svc.activation_engine.activate, MagicMock)  # sync def
    assert not isinstance(svc.activation_engine.activate, AsyncMock)
    assert isinstance(svc.activation_engine.detect_weak_connections, MagicMock)  # sync def


def test_evil_sync_targets_are_magicmock() -> None:
    """Verifies sync targets like fts_store and router remain MagicMocks and sync-callable."""
    svc = make_mock_service()

    # Verify they are MagicMock but NOT AsyncMock
    assert isinstance(svc.fts_store, MagicMock)
    assert not isinstance(svc.fts_store, AsyncMock)
    assert isinstance(svc.fts_store.search, MagicMock)
    assert not isinstance(svc.fts_store.search, AsyncMock)

    assert isinstance(svc.router, MagicMock)
    assert not isinstance(svc.router, AsyncMock)
    assert isinstance(svc.router.classify, MagicMock)
    assert not isinstance(svc.router.classify, AsyncMock)

    # Should be sync callable without throwing coroutine warnings or errors
    svc.fts_store.search.return_value = ["fts-match"]
    res = svc.fts_store.search("query")
    assert res == ["fts-match"]


def test_sad_override_replaces_dep() -> None:
    """Verifies that caller-provided overrides replace the factory-default mock."""
    custom_repo = MagicMock()
    svc = make_mock_service(repo=custom_repo)
    assert svc.repo is custom_repo


def test_sad_allow_sync_keeps_magicmock_on_async_target() -> None:
    """Verifies allow_sync overrides an async method back to MagicMock."""
    svc = make_mock_service(allow_sync=["repo.get_node"])

    # repo itself is still the mock
    assert svc.repo is not None
    # But get_node is specifically degraded to a sync MagicMock
    assert isinstance(svc.repo.get_node, MagicMock)
    assert not isinstance(svc.repo.get_node, AsyncMock)

    # Other methods on repo remain AsyncMock
    assert isinstance(svc.repo.create_node, AsyncMock)


@pytest.mark.allow_sync_mock("repo.create_node")
def test_sad_marker_threading_via_fixture(mock_service_factory) -> None:
    """Verifies the allow_sync_mock marker threads into the service factory fixture."""
    svc = mock_service_factory()

    # repo.create_node should be MagicMock because of the pytest marker
    assert isinstance(svc.repo.create_node, MagicMock)
    assert not isinstance(svc.repo.create_node, AsyncMock)

    # Other async methods remain AsyncMock
    assert isinstance(svc.repo.get_node, AsyncMock)
