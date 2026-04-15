"""Gold Stack tests for ablation study infrastructure (Step 8).

TDD Red→Green — tests the weight override and table formatting
without needing a live service.
"""

from __future__ import annotations

from benchmarks.longmemeval.ablation import (
    ABLATION_CONFIGS,
    ALL_CHANNELS,
    build_weight_override,
    format_ablation_table,
)

# ═══════════════════════════════════════════════════════════════
#  Ablation infrastructure: 3-evil / 1-sad / 1-happy
# ═══════════════════════════════════════════════════════════════


class TestBuildWeightOverride:
    """Tests for build_weight_override()."""

    def test_happy_disabling_fts_zeroes_weight(self) -> None:
        """Disabling 'fts' sets its weight to 0.0."""
        weights = build_weight_override(["fts"])

        assert weights["fts"] == 0.0
        # Other channels should be > 0
        assert weights["vector"] > 0
        assert weights["temporal"] > 0

    def test_happy_baseline_no_disabled(self) -> None:
        """Empty disabled list → all weights positive."""
        weights = build_weight_override([])

        for ch in ALL_CHANNELS:
            assert weights[ch] > 0, f"{ch} should be positive in baseline"

    def test_sad1_multiple_disabled(self) -> None:
        """Multiple channels disabled → all zeroed."""
        weights = build_weight_override(["temporal", "relational", "associative"])

        assert weights["temporal"] == 0.0
        assert weights["relational"] == 0.0
        assert weights["associative"] == 0.0
        # Vector and FTS should still be active
        assert weights["vector"] > 0
        assert weights["fts"] > 0

    def test_evil1_unknown_channel_ignored(self) -> None:
        """Unknown channel name → silently ignored, no crash."""
        weights = build_weight_override(["nonexistent_channel"])

        # Should still have all known channels with positive weights
        for ch in ALL_CHANNELS:
            assert weights[ch] > 0


class TestAblationConfigs:
    """Tests for ABLATION_CONFIGS structure."""

    def test_happy_baseline_exists(self) -> None:
        """Baseline config exists with empty disabled list."""
        assert "baseline" in ABLATION_CONFIGS
        assert ABLATION_CONFIGS["baseline"] == []

    def test_happy_all_single_channel_configs_exist(self) -> None:
        """Each main channel has a no_X config."""
        for ch in ["fts", "entity", "temporal", "relational", "associative"]:
            config_name = f"no_{ch}"
            assert config_name in ABLATION_CONFIGS, f"Missing config: {config_name}"
            assert ch in ABLATION_CONFIGS[config_name]

    def test_evil1_vector_only_disables_all_but_vector(self) -> None:
        """vector_only config disables everything except vector."""
        disabled = ABLATION_CONFIGS["vector_only"]
        # vector should NOT be disabled
        assert "vector" not in disabled
        # All other channels should be disabled
        for ch in ALL_CHANNELS:
            if ch != "vector":
                assert ch in disabled, f"{ch} should be disabled in vector_only"


class TestFormatAblationTable:
    """Tests for format_ablation_table()."""

    def test_happy_table_has_header_and_rows(self) -> None:
        """Table output has header row + data rows."""
        results = [
            {
                "config": "baseline",
                "disabled_channels": [],
                "aggregate_metrics": {
                    "recall_any_at_5": 0.8,
                    "recall_any_at_10": 0.9,
                    "recall_all_at_5": 0.7,
                    "recall_all_at_10": 0.85,
                },
            },
            {
                "config": "no_fts",
                "disabled_channels": ["fts"],
                "aggregate_metrics": {
                    "recall_any_at_5": 0.75,
                    "recall_any_at_10": 0.85,
                    "recall_all_at_5": 0.65,
                    "recall_all_at_10": 0.80,
                },
            },
        ]

        table = format_ablation_table(results)

        assert "baseline" in table
        assert "no_fts" in table
        assert "80.0%" in table  # 0.8 * 100
        assert "-5.0pp" in table  # 75 - 80 = -5

    def test_sad1_empty_results(self) -> None:
        """Empty results → table with just headers."""
        table = format_ablation_table([])

        assert "|" in table  # Has table markers
        lines = table.strip().split("\n")
        assert len(lines) == 2  # Header + separator only

    def test_evil1_no_baseline_no_delta(self) -> None:
        """If baseline is missing, delta column is empty."""
        results = [
            {
                "config": "no_fts",
                "disabled_channels": ["fts"],
                "aggregate_metrics": {
                    "recall_any_at_5": 0.75,
                    "recall_any_at_10": 0.85,
                    "recall_all_at_5": 0.65,
                    "recall_all_at_10": 0.80,
                },
            },
        ]

        table = format_ablation_table(results)

        # Should not crash and should not have delta value
        assert "no_fts" in table
        # Delta column should be empty (no baseline to diff against)
        assert "pp" not in table
