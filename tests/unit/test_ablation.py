from __future__ import annotations

"""Gold Stack tests for ablation study infrastructure (Step 8).

TDD Red→Green — tests the weight override and table formatting
without needing a live service.
"""


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
        """Unknown channel name -> silently ignored, no crash."""
        weights = build_weight_override(["nonexistent_channel"])

        # Should still have all known channels with positive weights
        for ch in ALL_CHANNELS:
            assert weights[ch] > 0

    def test_evil2_all_channels_disabled(self) -> None:
        """Disabling ALL channels -> all weights zero, no KeyError."""
        weights = build_weight_override(ALL_CHANNELS)

        for ch in ALL_CHANNELS:
            assert weights[ch] == 0.0

    def test_evil3_disable_vector_strongest_channel(self) -> None:
        """Disabling vector (strongest channel) still preserves others."""
        weights = build_weight_override(["vector"])

        assert weights["vector"] == 0.0
        # FTS should still be the next-highest
        assert weights["fts"] > 0
        assert weights["temporal"] > 0


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

    def test_evil2_no_graph_is_triple_disable(self) -> None:
        """no_graph config disables exactly temporal+relational+associative."""
        disabled = ABLATION_CONFIGS["no_graph"]
        assert "temporal" in disabled
        assert "relational" in disabled
        assert "associative" in disabled
        # Should NOT disable vector, fts, or entity
        assert "vector" not in disabled
        assert "fts" not in disabled
        assert "entity" not in disabled

    def test_evil3_config_values_are_lists(self) -> None:
        """Every config value must be a list (not set, not tuple)."""
        for name, disabled in ABLATION_CONFIGS.items():
            assert isinstance(disabled, list), f"{name} has non-list: {type(disabled)}"

    def test_sad1_disabled_channels_are_valid_names(self) -> None:
        """All disabled channel names must exist in ALL_CHANNELS."""
        valid = set(ALL_CHANNELS)
        for name, disabled in ABLATION_CONFIGS.items():
            for ch in disabled:
                assert ch in valid, f"{name} disables unknown channel: {ch}"


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

    def test_evil2_zero_metrics_format_correctly(self) -> None:
        """All-zero metrics don't crash or produce NaN output."""
        results = [
            {
                "config": "baseline",
                "disabled_channels": [],
                "aggregate_metrics": {
                    "recall_any_at_5": 0.0,
                    "recall_any_at_10": 0.0,
                    "recall_all_at_5": 0.0,
                    "recall_all_at_10": 0.0,
                },
            },
        ]

        table = format_ablation_table(results)

        assert "0.0%" in table
        assert "NaN" not in table
        assert "nan" not in table

    def test_evil3_many_configs_table_rows_match(self) -> None:
        """8 configs -> exactly 8 data rows + 2 header rows."""
        results = []
        for name, disabled in ABLATION_CONFIGS.items():
            results.append(
                {
                    "config": name,
                    "disabled_channels": disabled,
                    "aggregate_metrics": {
                        "recall_any_at_5": 0.5,
                        "recall_any_at_10": 0.6,
                        "recall_all_at_5": 0.4,
                        "recall_all_at_10": 0.55,
                    },
                }
            )

        table = format_ablation_table(results)
        lines = [ln for ln in table.strip().split("\n") if ln.strip()]

        # 2 header rows + 8 data rows
        assert len(lines) == 2 + len(ABLATION_CONFIGS)
