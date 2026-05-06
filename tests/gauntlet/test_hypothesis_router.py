"""Hypothesis property tests for router.py — Gauntlet R3B.

Tests QueryRouter.classify() with randomized inputs:
- Always returns a valid QueryIntent enum member
- Empty string → SEMANTIC (default fallback)
- Temporal/relational/associative keywords → correct intent
- Random gibberish → never crashes
- Very long strings → doesn't hang
- Unicode/emoji → doesn't crash
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from claude_memory.router import QueryIntent, QueryRouter

FUZZ_EXAMPLES = 2000


# ═══════════════════════════════════════════════════════════════
#  Router Classification Properties
# ═══════════════════════════════════════════════════════════════


class TestQueryRouterClassifyProperties:
    """Property tests for QueryRouter.classify — R3B spec."""

    def setup_method(self):
        self.router = QueryRouter()

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(st.text(max_size=500))
    def test_happy_always_returns_valid_intent(self, query):
        """P1: classify() always returns a valid QueryIntent, never crashes."""
        result = self.router.classify(query)
        assert isinstance(result, QueryIntent)
        assert result in list(QueryIntent)

    def test_sad_empty_string_returns_semantic(self):
        """P2: Empty string → SEMANTIC fallback."""
        assert self.router.classify("") == QueryIntent.SEMANTIC

    @settings(max_examples=500, deadline=None)
    @given(st.sampled_from(["when", "timeline", "before", "after", "recent", "latest"]))
    def test_happy_temporal_keywords(self, keyword):
        """P3: Temporal keywords → TEMPORAL intent."""
        query = f"tell me {keyword} something happened"
        result = self.router.classify(query)
        assert result == QueryIntent.TEMPORAL

    @settings(max_examples=500, deadline=None)
    @given(st.sampled_from(["path between", "what connects", "relationship between"]))
    def test_happy_relational_keywords(self, keyword):
        """P4: Relational keywords → RELATIONAL intent."""
        query = f"show me {keyword} these concepts"
        result = self.router.classify(query)
        assert result == QueryIntent.RELATIONAL

    @settings(max_examples=500, deadline=None)
    @given(st.sampled_from(["similar to", "related to", "associated with", "cluster around"]))
    def test_happy_associative_keywords(self, keyword):
        """P5: Associative keywords → ASSOCIATIVE intent."""
        query = f"find things {keyword} entropy"
        result = self.router.classify(query)
        assert result == QueryIntent.ASSOCIATIVE

    @settings(max_examples=FUZZ_EXAMPLES, deadline=None)
    @given(st.binary(max_size=1000))
    def test_happy_random_bytes_never_crash(self, data):
        """P6: Random binary as text → never crashes."""
        text = data.decode("latin-1", errors="replace")
        result = self.router.classify(text)
        assert isinstance(result, QueryIntent)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.large_base_example, HealthCheck.data_too_large],
    )
    @given(st.text(min_size=5000, max_size=15000))
    def test_happy_very_long_strings(self, query):
        """P7: Very long strings → doesn't hang, returns valid intent."""
        result = self.router.classify(query)
        assert isinstance(result, QueryIntent)

    @settings(max_examples=500, deadline=None)
    @given(
        st.text(
            alphabet=st.characters(categories=("So", "Sk", "Sm")),
            min_size=1,
            max_size=100,
        )
    )
    def test_happy_unicode_emoji_never_crash(self, query):
        """P8: Unicode symbols/emoji → doesn't crash."""
        result = self.router.classify(query)
        assert isinstance(result, QueryIntent)

    def test_happy_no_keywords_returns_semantic(self):
        """P9: Query with no keywords → SEMANTIC (default)."""
        result = self.router.classify("tell me about quantum physics")
        assert result == QueryIntent.SEMANTIC

    @settings(max_examples=500, deadline=None)
    @given(st.text(min_size=1, max_size=200))
    def test_happy_deterministic(self, query):
        """P10: Same input → same output every time."""
        r1 = self.router.classify(query)
        r2 = self.router.classify(query)
        assert r1 == r2
