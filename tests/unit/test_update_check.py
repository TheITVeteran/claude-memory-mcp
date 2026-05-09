"""Tests for update_check.py — 3 evil / 1 sad / 1 happy."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from claude_memory.update_check import _is_newer, _read_local_version, check_for_updates

# Patch target: module-level import in update_check.py
_HTTPX_CLIENT = "claude_memory.update_check.httpx.AsyncClient"


def _make_mock_client(
    status: int = 200,
    json_data: dict | None = None,
    get_side_effect: Exception | None = None,
) -> MagicMock:
    """Build a mock httpx.AsyncClient that works with ``async with ... as client:``."""
    # httpx.Response.json() is SYNC — must be MagicMock, not AsyncMock
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}

    client_instance = AsyncMock()
    if get_side_effect:
        client_instance.get = AsyncMock(side_effect=get_side_effect)
    else:
        client_instance.get = AsyncMock(return_value=resp)

    # httpx.AsyncClient(...) returns the context manager itself
    mock_cls = MagicMock(return_value=client_instance)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


# ─── Evil Path Tests ────────────────────────────────────────


class TestCheckForUpdatesEvil:
    """Adversarial inputs and hostile environments."""

    @pytest.mark.asyncio
    async def test_evil_malformed_json_response(self) -> None:
        """GitHub returns garbage JSON — must not crash."""
        mock_cls = _make_mock_client(200, {"unexpected": "shape"})
        with patch(_HTTPX_CLIENT, mock_cls):
            await check_for_updates()  # Must not raise

    @pytest.mark.asyncio
    async def test_evil_network_timeout(self) -> None:
        """Network timeout — must fail silently."""
        mock_cls = _make_mock_client(get_side_effect=httpx.TimeoutException("timeout"))
        with patch(_HTTPX_CLIENT, mock_cls):
            await check_for_updates()  # Must not raise

    @pytest.mark.asyncio
    async def test_evil_opt_out_makes_zero_network_calls(self) -> None:
        """UPDATE_CHECK=false must not make ANY network call."""
        with (
            patch.dict("os.environ", {"UPDATE_CHECK": "false"}),
            patch(_HTTPX_CLIENT) as mock_httpx,
        ):
            await check_for_updates()
            mock_httpx.assert_not_called()


# ─── Sad Path Test ──────────────────────────────────────────


class TestCheckForUpdatesSad:
    """Expected error conditions."""

    @pytest.mark.asyncio
    async def test_sad_github_returns_403(self) -> None:
        """GitHub rate-limited — must fail silently."""
        mock_cls = _make_mock_client(403)
        with patch(_HTTPX_CLIENT, mock_cls):
            await check_for_updates()  # Must not raise


# ─── Happy Path Test ────────────────────────────────────────


class TestCheckForUpdatesHappy:
    """Normal operations."""

    @pytest.mark.asyncio
    async def test_happy_newer_version_logs_message(self, caplog: pytest.LogCaptureFixture) -> None:
        """A newer release is available — must log a friendly message."""
        mock_cls = _make_mock_client(
            200,
            {
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/iikarus/claude-memory-mcp/releases/tag/v2.0.0",
            },
        )
        with (
            patch(_HTTPX_CLIENT, mock_cls),
            patch("claude_memory.update_check._read_local_version", return_value="1.0.0"),
            caplog.at_level(logging.INFO, logger="claude_memory.update_check"),
        ):
            await check_for_updates()

        assert "Update available" in caplog.text
        assert "2.0.0" in caplog.text


# ─── Helper Tests ───────────────────────────────────────────


class TestIsNewer:
    """Version comparison edge cases."""

    def test_happy_newer_major(self) -> None:
        assert _is_newer("2.0.0", "1.0.0") is True

    def test_happy_same_version(self) -> None:
        assert _is_newer("1.0.0", "1.0.0") is False

    def test_happy_older_version(self) -> None:
        assert _is_newer("0.9.0", "1.0.0") is False

    def test_happy_garbage_input(self) -> None:
        assert _is_newer("not.a.version", "1.0.0") is False

    def test_sad1_empty_strings(self) -> None:
        assert _is_newer("", "") is False


class TestReadLocalVersion:
    """VERSION file reading."""

    def test_evil1_missing_file_returns_fallback(self) -> None:
        with patch("claude_memory.update_check._VERSION_FILE") as mock_path:
            mock_path.read_text.side_effect = FileNotFoundError
            assert _read_local_version() == "0.0.0"
