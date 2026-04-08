"""Startup update checker — fire-and-forget GitHub releases comparison.

Runs once on MCP server boot. Notification only (never modifies files).
Disable via ``UPDATE_CHECK=false`` environment variable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_REPO = "iikarus/claude-memory-mcp"
_RELEASES_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_TIMEOUT_SECONDS = 5.0
_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read_local_version() -> str:
    """Read the local version from the VERSION file."""
    try:
        return _VERSION_FILE.read_text().strip()
    except (OSError, ValueError):
        return "0.0.0"


async def check_for_updates() -> None:
    """Compare local VERSION against the latest GitHub release.

    Logs a friendly message if a newer version is available.
    Fails silently on any error — never blocks server startup.
    """
    if os.getenv("UPDATE_CHECK", "true").lower() == "false":
        return

    try:
        local = _read_local_version()
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                _RELEASES_URL,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:  # noqa: PLR2004
                return

            data = resp.json()
            remote_tag = data.get("tag_name", "").lstrip("v")
            release_url = data.get("html_url", "")

            if not remote_tag:
                return

            if _is_newer(remote_tag, local):
                logger.info("✨ Update available: v%s (you have v%s)", remote_tag, local)
                logger.info("   Release notes: %s", release_url)
                logger.info("   To update: git pull && pip install -e .")

    except Exception:  # noqa: S110 — intentional silent failure; must never crash server  # nosec B110
        pass  # Fire-and-forget: server starts regardless


def _is_newer(remote: str, local: str) -> bool:
    """Compare version strings (major.minor.patch)."""
    try:
        r_parts = [int(x) for x in remote.split(".")]
        l_parts = [int(x) for x in local.split(".")]
        return r_parts > l_parts
    except (ValueError, TypeError):
        return False
