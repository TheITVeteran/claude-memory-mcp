"""Temporal date extraction from natural language queries.

Parses both explicit dates ("January 2026", "2026-01-15") and relative
dates ("last week", "yesterday", "3 days ago") into (start, end)
datetime windows for use as hard filters in temporal retrieval (Tier 2.4).
"""

from __future__ import annotations

import logging
import re
from calendar import monthrange
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# ── Relative date patterns ───────────────────────────────────────────

_RELATIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\byesterday\b", re.IGNORECASE), "yesterday"),
    (re.compile(r"\blast\s+week\b", re.IGNORECASE), "last_week"),
    (re.compile(r"\bthis\s+week\b", re.IGNORECASE), "this_week"),
    (re.compile(r"\blast\s+month\b", re.IGNORECASE), "last_month"),
    (re.compile(r"\bthis\s+month\b", re.IGNORECASE), "this_month"),
    (re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE), "n_days_ago"),
    (re.compile(r"\b(\d+)\s+weeks?\s+ago\b", re.IGNORECASE), "n_weeks_ago"),
    (re.compile(r"\btoday\b", re.IGNORECASE), "today"),
    (re.compile(r"\brecently\b", re.IGNORECASE), "recently"),
]

# Month name → number
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Explicit date patterns
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(_MONTHS.keys()) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)


def parse_temporal_range(
    text: str | None,
) -> tuple[datetime, datetime] | None:
    """Extract a temporal date range from natural language text.

    Args:
        text: Query text that may contain date signals.

    Returns:
        (start, end) datetime tuple (UTC-aware), or None if no
        temporal signal was detected.
    """
    if not text:
        return None

    now = datetime.now(UTC)

    # Phase 1: Check explicit ISO date (2026-01-15)
    m = _ISO_DATE.search(text)
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            start = datetime(year, month, day, tzinfo=UTC)
            end = start + timedelta(days=1)
            return (start, end)
        except ValueError:  # noqa: contract
            logger.debug("Phase 1 date parsing failed")

    # Phase 2: Check explicit month + year (January 2026)
    m = _MONTH_YEAR.search(text)
    if m:
        month_name = m.group(1).lower()
        year = int(m.group(2))
        month_num = _MONTHS.get(month_name)
        if month_num:
            _, days_in_month = monthrange(year, month_num)
            start = datetime(year, month_num, 1, tzinfo=UTC)
            end = datetime(year, month_num, days_in_month, 23, 59, 59, tzinfo=UTC)
            return (start, end)

    # Phase 3: Check relative patterns
    for pattern, kind in _RELATIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            return _resolve_relative(kind, m, now)

    return None


def _resolve_relative(
    kind: str,
    match: re.Match[str],
    now: datetime,
) -> tuple[datetime, datetime]:
    """Resolve a relative date pattern to a concrete range."""
    if kind == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif kind == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif kind == "last_week":
        start = now - timedelta(days=7)
        end = now
    elif kind == "this_week":
        # Monday of current week
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = now
    elif kind == "last_month":
        start = now - timedelta(days=30)
        end = now
    elif kind == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif kind == "n_days_ago":
        n = int(match.group(1))
        start = now - timedelta(days=n)
        end = now
    elif kind == "n_weeks_ago":
        n = int(match.group(1))
        start = now - timedelta(weeks=n)
        end = now
    elif kind == "recently":
        start = now - timedelta(days=7)
        end = now
    else:
        start = now - timedelta(days=7)
        end = now

    return (start, end)
