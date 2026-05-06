"""Fuzz Blitz — Gauntlet R5.

Throws garbage at every input surface to find crashes:
1. Schema validation (Pydantic models) — random dicts
2. Router classification — random bytes/unicode
3. Clustering — degenerate inputs

All targets must either succeed or raise clean ValidationError — never unhandled crash.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from claude_memory.schema import (
    EntityCreateParams,
    GapDetectionParams,
    ObservationParams,
    RelationshipCreateParams,
    SearchResult,
)

HEAVY_FUZZ = 5000


# ═══════════════════════════════════════════════════════════════
#  Target 1: Schema Validation Fuzzing
# ═══════════════════════════════════════════════════════════════


class TestSchemaFuzzing:
    """Feed random dicts to Pydantic models — must not unhandled crash."""

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.dictionaries(
            keys=st.text(max_size=30),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.floats(allow_nan=False),
                st.booleans(),
                st.none(),
            ),
            max_size=10,
        )
    )
    def test_happy_entity_create_fuzz(self, data):
        """F1: Random dict → EntityCreateParams → either valid or clean ValidationError."""
        try:
            EntityCreateParams(**data)
        except (ValidationError, TypeError):
            pass  # expected for invalid input

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.dictionaries(
            keys=st.text(max_size=30),
            values=st.one_of(
                st.text(max_size=100), st.integers(), st.floats(allow_nan=False), st.none()
            ),
            max_size=10,
        )
    )
    def test_happy_relationship_create_fuzz(self, data):
        """F2: Random dict → RelationshipCreateParams → clean error or valid."""
        try:
            RelationshipCreateParams(**data)
        except (ValidationError, TypeError):
            pass

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.dictionaries(
            keys=st.text(max_size=30),
            values=st.one_of(st.text(max_size=100), st.integers(), st.booleans(), st.none()),
            max_size=10,
        )
    )
    def test_happy_search_result_fuzz(self, data):
        """F3: Random dict → SearchResult → clean error or valid."""
        try:
            SearchResult(**data)
        except (ValidationError, TypeError):
            pass

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.dictionaries(
            keys=st.text(max_size=30),
            values=st.one_of(st.text(max_size=100), st.integers(), st.none()),
            max_size=10,
        )
    )
    def test_happy_gap_detection_fuzz(self, data):
        """F4: Random dict → GapDetectionParams → clean error or valid."""
        try:
            GapDetectionParams(**data)
        except (ValidationError, TypeError):
            pass

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.dictionaries(
            keys=st.text(max_size=30),
            values=st.one_of(st.text(max_size=100), st.integers(), st.none()),
            max_size=10,
        )
    )
    def test_happy_observation_fuzz(self, data):
        """F5: Random dict → ObservationParams → clean error or valid."""
        try:
            ObservationParams(**data)
        except (ValidationError, TypeError):
            pass


# ═══════════════════════════════════════════════════════════════
#  Target 2: Router Fuzzing (heavier than R3B)
# ═══════════════════════════════════════════════════════════════


class TestRouterFuzzing:
    """Throw garbage at QueryRouter.classify() — must never crash."""

    @settings(max_examples=HEAVY_FUZZ, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.binary(max_size=5000))
    def test_happy_binary_input(self, data):
        """F6: Random binary → decode as latin-1 → classify → never crash."""
        from claude_memory.router import QueryIntent, QueryRouter

        router = QueryRouter()
        text = data.decode("latin-1", errors="replace")
        result = router.classify(text)
        assert isinstance(result, QueryIntent)


# ═══════════════════════════════════════════════════════════════
#  Target 3: Boundary Conditions
# ═══════════════════════════════════════════════════════════════


class TestBoundaryConditions:
    """Specific edge cases from spec — boundary inputs."""

    def test_sad_entity_name_empty_string(self):
        """B1: Empty name — should construct (no min_length on name field)."""
        params = EntityCreateParams(name="", node_type="Entity", project_id="test")
        assert params.name == ""

    def test_happy_entity_name_single_char(self):
        """B2: Single character name."""
        params = EntityCreateParams(name="a", node_type="Entity", project_id="test")
        assert params.name == "a"

    def test_happy_entity_name_100k_chars(self):
        """B3: 100K char name — must not crash."""
        big_name = "x" * 100_000
        params = EntityCreateParams(name=big_name, node_type="Entity", project_id="test")
        assert len(params.name) == 100_000

    def test_happy_entity_name_null_bytes(self):
        """B4: Null bytes in name — Pydantic accepts, validation elsewhere."""
        params = EntityCreateParams(name="\x00", node_type="Entity", project_id="test")
        assert params.name == "\x00"

    def test_happy_entity_name_only_whitespace(self):
        """B5: Whitespace-only name — accepted by schema."""
        params = EntityCreateParams(name="   ", node_type="Entity", project_id="test")
        assert params.name == "   "

    def test_happy_entity_name_sql_injection(self):
        """B6: SQL injection string — treated as plain text."""
        params = EntityCreateParams(name="'; DROP TABLE --", node_type="Entity", project_id="test")
        assert params.name == "'; DROP TABLE --"

    def test_happy_entity_name_cypher_injection(self):
        """B7: Cypher injection string — treated as plain text."""
        params = EntityCreateParams(name="') RETURN n //", node_type="Entity", project_id="test")
        assert params.name == "') RETURN n //"

    def test_happy_relationship_to_self(self):
        """B8: Self-relationship — schema allows, validation elsewhere."""
        params = RelationshipCreateParams(
            from_entity="same_id",
            to_entity="same_id",
            relationship_type="RELATED_TO",
        )
        assert params.from_entity == params.to_entity

    def test_happy_gap_params_extreme_similarity(self):
        """B9: Edge similarity values 0.0 and 1.0."""
        p0 = GapDetectionParams(min_similarity=0.0)
        p1 = GapDetectionParams(min_similarity=1.0)
        assert p0.min_similarity == 0.0
        assert p1.min_similarity == 1.0
