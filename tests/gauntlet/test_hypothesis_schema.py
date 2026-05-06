"""Hypothesis property tests for schema.py — Gauntlet R3A.

Tests Pydantic model validation across randomized inputs:
- EntityCreateParams construction and round-trip serialization
- RelationshipCreateParams weight constraints
- SearchResult score invariants
- GapDetectionParams boundary validation
- TemporalQueryParams date handling
- BottleQueryParams defaults
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from claude_memory.schema import (
    BottleQueryParams,
    EntityCreateParams,
    GapDetectionParams,
    RelationshipCreateParams,
    SearchResult,
    TemporalQueryParams,
)

FUZZ_EXAMPLES = 2000


# ═══════════════════════════════════════════════════════════════
#  Strategies
# ═══════════════════════════════════════════════════════════════

# Safe text: avoid surrogates that break JSON serialization
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=1,
    max_size=200,
)

node_type_strategy = st.sampled_from(
    [
        "Concept",
        "Entity",
        "Event",
        "Person",
        "Tool",
        "Decision",
        "Observation",
        "Session",
        "Breakthrough",
        "Bottle",
        "GapReport",
        "Project",
        "Custom",
    ]
)

certainty_strategy = st.sampled_from(
    ["confirmed", "speculative", "spitballing", "rejected", "revisited"]
)


# ═══════════════════════════════════════════════════════════════
#  EntityCreateParams Properties
# ═══════════════════════════════════════════════════════════════


class TestEntityCreateParamsProperties:
    """Property tests for EntityCreateParams — R3A spec."""

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(safe_text, node_type_strategy, safe_text, certainty_strategy)
    def test_happy_valid_construction(self, name, node_type, project_id, certainty):
        """P1: Any non-empty name + valid type constructs successfully."""
        params = EntityCreateParams(
            name=name,
            node_type=node_type,
            project_id=project_id,
            certainty=certainty,
        )
        assert params.name == name
        assert params.node_type == node_type

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(safe_text, node_type_strategy, safe_text)
    def test_happy_roundtrip_serialization(self, name, node_type, project_id):
        """P2: Serialize to JSON → deserialize → equals original."""
        params = EntityCreateParams(name=name, node_type=node_type, project_id=project_id)
        json_str = params.model_dump_json()
        restored = EntityCreateParams.model_validate_json(json_str)
        assert restored.name == params.name
        assert restored.node_type == params.node_type
        assert restored.project_id == params.project_id

    @settings(max_examples=500, deadline=None)
    @given(
        safe_text,
        node_type_strategy,
        safe_text,
        st.dictionaries(
            keys=safe_text,
            values=st.one_of(st.text(max_size=50), st.integers(), st.booleans(), st.none()),
            max_size=5,
        ),
    )
    def test_happy_extra_properties_accepted(self, name, node_type, project_id, props):
        """P3: Arbitrary extra properties dict is accepted without crash."""
        params = EntityCreateParams(
            name=name,
            node_type=node_type,
            project_id=project_id,
            properties=props,
        )
        assert params.properties == props


# ═══════════════════════════════════════════════════════════════
#  RelationshipCreateParams Properties
# ═══════════════════════════════════════════════════════════════


class TestRelationshipCreateParamsProperties:
    """Property tests for RelationshipCreateParams — R3A spec."""

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(
        safe_text,
        safe_text,
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_happy_weight_bounds(self, from_entity, to_entity, weight):
        """P1: Weight must be 0.0 <= w <= 1.0 — valid values accepted."""
        params = RelationshipCreateParams(
            from_entity=from_entity,
            to_entity=to_entity,
            relationship_type="RELATED_TO",
            weight=weight,
        )
        assert 0.0 <= params.weight <= 1.0

    @settings(max_examples=500, deadline=None)
    @given(st.floats().filter(lambda x: x < 0.0 or x > 1.0))
    def test_happy_weight_out_of_bounds_rejected(self, weight):
        """P2: Weight outside 0-1 raises ValidationError."""
        with pytest.raises(ValidationError):
            RelationshipCreateParams(
                from_entity="a",
                to_entity="b",
                relationship_type="RELATED_TO",
                weight=weight,
            )


# ═══════════════════════════════════════════════════════════════
#  SearchResult Properties
# ═══════════════════════════════════════════════════════════════


class TestSearchResultProperties:
    """Property tests for SearchResult — R3A spec."""

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(
        safe_text,
        safe_text,
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_happy_construction_with_valid_scores(self, name, node_type, score, distance):
        """P1: Valid scores always construct successfully."""
        result = SearchResult(
            id="test-id",
            name=name,
            node_type=node_type,
            project_id="test",
            score=score,
            distance=distance,
        )
        assert result.score == score
        assert result.distance == distance

    @settings(max_examples=500, deadline=None)
    @given(safe_text, safe_text)
    def test_sad_default_collections_empty(self, name, node_type):
        """P2: observations and relationships default to empty lists."""
        result = SearchResult(
            id="test-id",
            name=name,
            node_type=node_type,
            project_id="test",
            score=0.9,
            distance=0.1,
        )
        assert result.observations == []
        assert result.relationships == []


# ═══════════════════════════════════════════════════════════════
#  GapDetectionParams Properties
# ═══════════════════════════════════════════════════════════════


class TestGapDetectionParamsProperties:
    """Property tests for GapDetectionParams — R3A spec."""

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=1, max_value=50),
    )
    def test_happy_valid_construction(self, min_similarity, max_edges, limit):
        """P1: Valid params always construct."""
        params = GapDetectionParams(
            min_similarity=min_similarity,
            max_edges=max_edges,
            limit=limit,
        )
        assert 0.0 <= params.min_similarity <= 1.0
        assert params.max_edges >= 0
        assert 1 <= params.limit <= 50

    @settings(max_examples=500, deadline=None)
    @given(st.floats().filter(lambda x: x < 0.0 or x > 1.0))
    def test_happy_similarity_out_of_bounds_rejected(self, bad_sim):
        """P2: min_similarity outside 0-1 raises ValidationError."""
        with pytest.raises(ValidationError):
            GapDetectionParams(min_similarity=bad_sim)

    def test_happy_limit_zero_rejected(self):
        """P3: limit=0 raises ValidationError (ge=1)."""
        with pytest.raises(ValidationError):
            GapDetectionParams(limit=0)


# ═══════════════════════════════════════════════════════════════
#  TemporalQueryParams Properties
# ═══════════════════════════════════════════════════════════════


class TestTemporalQueryParamsProperties:
    """Property tests for TemporalQueryParams — R3A spec."""

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(
        st.datetimes(timezones=st.just(None)),
        st.datetimes(timezones=st.just(None)),
        st.integers(min_value=1, max_value=100),
    )
    def test_happy_valid_construction(self, start, end, limit):
        """P1: Any datetime pair + valid limit constructs."""
        params = TemporalQueryParams(start=start, end=end, limit=limit)
        assert params.start == start
        assert params.end == end

    def test_happy_limit_out_of_range_rejected(self):
        """P2: limit > 100 raises ValidationError."""
        from datetime import datetime

        with pytest.raises(ValidationError):
            TemporalQueryParams(
                start=datetime(2026, 1, 1),
                end=datetime(2026, 2, 1),
                limit=101,
            )


# ═══════════════════════════════════════════════════════════════
#  BottleQueryParams Properties
# ═══════════════════════════════════════════════════════════════


class TestBottleQueryParamsProperties:
    """Property tests for BottleQueryParams — R3A spec."""

    def test_happy_include_content_defaults_false(self):
        """P1: include_content defaults to False."""
        params = BottleQueryParams()
        assert params.include_content is False

    @settings(max_examples=500, deadline=None)
    @given(st.integers(min_value=1, max_value=100))
    def test_happy_valid_limit(self, limit):
        """P2: Valid limit always accepted."""
        params = BottleQueryParams(limit=limit)
        assert params.limit == limit
