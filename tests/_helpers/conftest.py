"""Pytest fixtures exposing make_mock_service to test files.

Per process/issues/22a_BUILD_SPEC.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from claude_memory.tools import MemoryService

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

    def _factory(**overrides) -> MemoryService:
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
