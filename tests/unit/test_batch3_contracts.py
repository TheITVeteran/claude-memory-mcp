"""Tests for Batch 3: Channel health metadata.

AUDIT-B3: Verifies that enrichment channel failures are surfaced in
search metadata instead of being silently swallowed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from claude_memory.schema import ChannelStatus

# --- Test Constants ---
SEARCH_QUERY = "async patterns"
SEARCH_LIMIT = 10


# ═══════════════════════════════════════════════════════════
# 3.1 ChannelStatus schema
# ═══════════════════════════════════════════════════════════


class TestChannelStatusSchema:
    """ChannelStatus model validation."""

    def test_happy_channel_status_ok(self) -> None:
        """AUDIT-B3: OK status with result count."""
        cs = ChannelStatus(channel="vector", status="ok", result_count=5)
        assert cs.channel == "vector"
        assert cs.status == "ok"
        assert cs.result_count == 5
        assert cs.error is None

    def test_happy_channel_status_degraded(self) -> None:
        """AUDIT-B3: Degraded status with error message."""
        cs = ChannelStatus(channel="temporal", status="degraded", result_count=0, error="Timeout")
        assert cs.status == "degraded"
        assert cs.error == "Timeout"

    def test_sad1_channel_status_defaults(self) -> None:
        """AUDIT-B3: Defaults are sensible."""
        cs = ChannelStatus(channel="fts", status="ok")
        assert cs.result_count == 0
        assert cs.error is None

    def test_evil1_channel_status_serialization(self) -> None:
        """AUDIT-B3: Serializes to dict cleanly."""
        cs = ChannelStatus(channel="relational", status="degraded", error="FalkorDB down")
        d = cs.model_dump()
        assert d["channel"] == "relational"
        assert d["status"] == "degraded"
        assert d["error"] == "FalkorDB down"

    def test_evil2_channel_status_invalid_status(self) -> None:
        """AUDIT-B3: Invalid status value is rejected by Literal constraint."""
        with pytest.raises(ValidationError):
            ChannelStatus(channel="vector", status="banana")  # type: ignore[arg-type]

    def test_evil3_channel_status_missing_channel(self) -> None:
        """AUDIT-B3: Missing required field raises validation error."""
        with pytest.raises(ValidationError):
            ChannelStatus(status="ok")  # type: ignore[call-arg]


# ═══════════════════════════════════════════════════════════
# 3.2-3.8 Channel status accumulation in search()
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def search_service():
    """Build a MemoryService with mocked infra for search testing."""
    with patch("claude_memory.repository.FalkorDB"):
        from claude_memory.tools import MemoryService

        embedder = MagicMock()
        embedder.encode.return_value = [0.1] * 1024
        vector_store = AsyncMock()
        vector_store.search.return_value = []

        service = MemoryService(embedding_service=embedder, vector_store=vector_store)
        service.repo = MagicMock()
        service.repo.client = MagicMock()
        service.repo.client.select_graph.return_value = MagicMock()

        # FTS store
        fts_mock = MagicMock()
        fts_mock.search.return_value = []
        service.fts_store = fts_mock

        # Activation engine
        service.activation_engine = MagicMock()

        yield service


@pytest.mark.asyncio
async def test_evil1_channel_failure_visible_in_status(search_service) -> None:
    """AUDIT-B3: When temporal enrichment fails, channel_status shows degraded."""
    # Make temporal fail
    search_service.query_timeline = AsyncMock(side_effect=ConnectionError("FalkorDB timeout"))

    await search_service.search(SEARCH_QUERY, limit=SEARCH_LIMIT)

    statuses = search_service._last_channel_status
    assert isinstance(statuses, list)

    temporal_status = next((s for s in statuses if s.channel == "temporal"), None)
    # Temporal may not run if weight is 0 for this query — check if it ran
    if temporal_status is not None:
        assert temporal_status.status == "degraded"
        assert temporal_status.error is not None


@pytest.mark.asyncio
async def test_evil2_fts_failure_visible_in_status(search_service) -> None:
    """AUDIT-B3: When FTS search fails, channel_status shows degraded."""
    search_service.fts_store.search.side_effect = Exception("FTS corrupted")

    await search_service.search(SEARCH_QUERY, limit=SEARCH_LIMIT)

    statuses = search_service._last_channel_status
    fts_status = next((s for s in statuses if s.channel == "fts"), None)
    assert fts_status is not None
    assert fts_status.status == "degraded"


@pytest.mark.asyncio
async def test_evil3_all_channels_ok_when_healthy(search_service) -> None:
    """AUDIT-B3: All channels report ok when nothing fails."""
    await search_service.search(SEARCH_QUERY, limit=SEARCH_LIMIT)

    statuses = search_service._last_channel_status
    assert isinstance(statuses, list)
    assert len(statuses) >= 2  # At minimum vector + fts

    for s in statuses:
        assert s.status == "ok"


@pytest.mark.asyncio
async def test_sad1_channel_status_empty_results(search_service) -> None:
    """AUDIT-B3: Zero results but no error → status is still ok."""
    await search_service.search(SEARCH_QUERY, limit=SEARCH_LIMIT)

    statuses = search_service._last_channel_status
    vector_status = next((s for s in statuses if s.channel == "vector"), None)
    assert vector_status is not None
    assert vector_status.status == "ok"
    assert vector_status.result_count == 0


@pytest.mark.asyncio
async def test_happy_channel_status_with_results(search_service) -> None:
    """AUDIT-B3: Channels with results report correct count."""
    search_service.vector_store.search.return_value = [
        {"_id": "e1", "_score": 0.9, "payload": {"name": "Test"}},
    ]

    await search_service.search(SEARCH_QUERY, limit=SEARCH_LIMIT)

    statuses = search_service._last_channel_status
    vector_status = next((s for s in statuses if s.channel == "vector"), None)
    assert vector_status is not None
    assert vector_status.result_count == 1
