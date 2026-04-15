"""Gold Stack tests for RerankerClient (Tier 1.3).

Tests follow the 3-evil/1-sad/1-happy naming convention.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from claude_memory.reranker import _MIN_RERANK_CANDIDATES, RerankerClient


@pytest.fixture()
def client() -> RerankerClient:
    """RerankerClient pointed at a fake URL."""
    return RerankerClient(api_url="http://test-server:8000", timeout=5.0)


def _make_candidates(n: int) -> list[dict]:
    """Build N mock candidates with _text field."""
    return [
        {
            "_id": f"e{i}",
            "name": f"Entity {i}",
            "_score": 0.9 - i * 0.1,
            "_text": f"text about entity {i}",
        }
        for i in range(n)
    ]


# ── Happy Path ───────────────────────────────────────────────────────


class TestHappyReranker:
    """Core functionality: rerank candidates via cross-encoder."""

    @pytest.mark.asyncio()
    async def test_happy_rerank_reorders_candidates(self, client: RerankerClient) -> None:
        """Reranker reorders candidates based on cross-encoder scores."""
        candidates = _make_candidates(5)

        mock_response = httpx.Response(
            200,
            json={
                "scores": [0.95, 0.80, 0.60, 0.40, 0.20],
                "indices": [3, 1, 0, 4, 2],  # reversed order
            },
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates)

        assert len(result) == 5
        # First result should be index 3 from original
        assert result[0]["_id"] == "e3"
        assert result[0]["_rerank_score"] == 0.95

    @pytest.mark.asyncio()
    async def test_happy_rerank_respects_top_k(self, client: RerankerClient) -> None:
        """top_k limits the number of returned results."""
        candidates = _make_candidates(5)

        mock_response = httpx.Response(
            200,
            json={
                "scores": [0.95, 0.80, 0.60],
                "indices": [3, 1, 0],
            },
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates, top_k=3)

        assert len(result) == 3

    @pytest.mark.asyncio()
    async def test_happy_rerank_adds_rerank_score(self, client: RerankerClient) -> None:
        """Each reranked candidate gets a _rerank_score field."""
        candidates = _make_candidates(4)

        mock_response = httpx.Response(
            200,
            json={"scores": [0.9, 0.7, 0.5, 0.3], "indices": [0, 1, 2, 3]},
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates)

        for r in result:
            assert "_rerank_score" in r
            assert isinstance(r["_rerank_score"], float)


# ── Sad Path ─────────────────────────────────────────────────────────


class TestSadReranker:
    """Edge cases that should degrade gracefully."""

    @pytest.mark.asyncio()
    async def test_sad1_too_few_candidates_skips_rerank(self, client: RerankerClient) -> None:
        """Fewer than _MIN_RERANK_CANDIDATES returns candidates unchanged."""
        candidates = _make_candidates(_MIN_RERANK_CANDIDATES - 1)
        result = await client.rerank("test query", candidates)
        assert result == candidates  # unchanged, no HTTP call

    @pytest.mark.asyncio()
    async def test_sad1_empty_candidates(self, client: RerankerClient) -> None:
        """Empty candidate list returns empty, no HTTP call."""
        result = await client.rerank("test query", [])
        assert result == []

    @pytest.mark.asyncio()
    async def test_sad1_server_404_falls_back(self, client: RerankerClient) -> None:
        """404 from server (no /rerank endpoint) returns original order."""
        candidates = _make_candidates(5)

        mock_response = httpx.Response(
            404,
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates)

        # Should return original candidates unchanged
        assert result == candidates


# ── Evil Path ────────────────────────────────────────────────────────


class TestEvilReranker:
    """Adversarial inputs and failure modes."""

    @pytest.mark.asyncio()
    async def test_evil1_connection_refused(self, client: RerankerClient) -> None:
        """Server unreachable returns original candidates."""
        candidates = _make_candidates(5)

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = await client.rerank("test query", candidates)

        assert result == candidates

    @pytest.mark.asyncio()
    async def test_evil1_timeout(self, client: RerankerClient) -> None:
        """Timeout returns original candidates."""
        candidates = _make_candidates(5)

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = await client.rerank("test query", candidates)

        assert result == candidates

    @pytest.mark.asyncio()
    async def test_evil1_invalid_indices(self, client: RerankerClient) -> None:
        """Out-of-range indices are safely skipped."""
        candidates = _make_candidates(3)

        mock_response = httpx.Response(
            200,
            json={
                "scores": [0.9, 0.8, 0.7],
                "indices": [0, 999, 1],  # 999 is out of range
            },
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates)

        # Index 999 skipped, only 0 and 1 returned
        assert len(result) == 2

    @pytest.mark.asyncio()
    async def test_evil1_missing_text_key_builds_fallback(self, client: RerankerClient) -> None:
        """Candidates without _text use name+entity_type as fallback."""
        candidates = [
            {"_id": "e1", "name": "Python", "entity_type": "Language"},
            {"_id": "e2", "name": "Java", "entity_type": "Language"},
            {"_id": "e3", "name": "Go", "entity_type": "Language"},
        ]

        mock_response = httpx.Response(
            200,
            json={"scores": [0.9, 0.7, 0.5], "indices": [0, 1, 2]},
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates, text_key="_text")

        assert len(result) == 3

    @pytest.mark.asyncio()
    async def test_evil1_server_500_falls_back(self, client: RerankerClient) -> None:
        """Server error returns original order."""
        candidates = _make_candidates(5)

        mock_response = httpx.Response(
            500,
            json={"detail": "Internal error"},
            request=httpx.Request("POST", "http://test-server:8000/rerank"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await client.rerank("test query", candidates)

        assert result == candidates
