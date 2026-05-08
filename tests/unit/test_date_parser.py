from __future__ import annotations

"""Gold Stack tests for temporal date extraction (Tier 2.4).

TDD Red phase — tests written BEFORE implementation.

The date_parser module should:
- Parse explicit dates: "January 15, 2026", "2026-01-15"
- Parse relative dates: "last week", "yesterday", "3 days ago"
- Return (start_date, end_date) tuples or None
- Handle ambiguous/missing dates gracefully
"""


from datetime import datetime

from claude_memory.date_parser import parse_temporal_range

# ═══════════════════════════════════════════════════════════════
#  parse_temporal_range: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestParseDateRange:
    """Gold Stack tests for parse_temporal_range()."""

    # ── Happy path ───────────────────────────────────────────

    def test_happy_relative_last_week(self) -> None:
        """'last week' → 7-day window ending now."""
        result = parse_temporal_range("what happened last week")

        assert result is not None
        start, end = result
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        # Window should be approximately 7 days
        delta = end - start
        assert 6 <= delta.days <= 8

    def test_happy_relative_yesterday(self) -> None:
        """'yesterday' → 1-day window."""
        result = parse_temporal_range("tell me about yesterday")

        assert result is not None
        start, end = result
        delta = end - start
        assert 0 <= delta.days <= 2

    def test_happy_relative_n_days_ago(self) -> None:
        """'3 days ago' → window from 3 days ago to now."""
        result = parse_temporal_range("what happened 3 days ago")

        assert result is not None
        start, end = result
        # Start should be approximately 3 days before end
        delta = end - start
        assert 2 <= delta.days <= 4

    def test_happy_explicit_month_year(self) -> None:
        """'January 2026' → full month window."""
        result = parse_temporal_range("things from January 2026")

        assert result is not None
        start, _end = result
        assert start.month == 1
        assert start.year == 2026

    def test_happy_explicit_date(self) -> None:
        """'2026-01-15' → single day window."""
        result = parse_temporal_range("what happened on 2026-01-15")

        assert result is not None
        start, _end = result
        assert start.year == 2026
        assert start.month == 1
        assert start.day == 15

    # ── Sad path ─────────────────────────────────────────────

    def test_sad1_no_temporal_signal(self) -> None:
        """Query with no date signals → None."""
        result = parse_temporal_range("what is Python")
        assert result is None

    def test_sad1_empty_string(self) -> None:
        """Empty string → None."""
        result = parse_temporal_range("")
        assert result is None

    def test_sad1_none_input(self) -> None:
        """None input → None."""
        result = parse_temporal_range(None)  # type: ignore[arg-type]
        assert result is None

    # ── Evil path ────────────────────────────────────────────

    def test_evil1_last_month(self) -> None:
        """'last month' → ~30-day window."""
        result = parse_temporal_range("show me things from last month")

        assert result is not None
        start, end = result
        delta = end - start
        assert 27 <= delta.days <= 32

    def test_evil1_this_week(self) -> None:
        """'this week' → window from start of current week to now."""
        result = parse_temporal_range("what happened this week")

        assert result is not None
        start, end = result
        # Should be within the current week
        assert (end - start).days <= 7

    def test_evil1_dates_are_timezone_aware(self) -> None:
        """Returned dates must be timezone-aware (UTC)."""
        result = parse_temporal_range("what happened last week")

        assert result is not None
        start, end = result
        assert start.tzinfo is not None
        assert end.tzinfo is not None
