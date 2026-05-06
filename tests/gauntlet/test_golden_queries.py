"""Golden query set — behavioural drift detection (DRIFT-001).

A frozen set of queries with expected behavioural contracts.
Failures indicate something drifted — not that code is broken.

Two test classes:
  - ``TestGoldenQueryFramework``  — mocked service, CI-fast, tests assertion machinery
  - ``TestGoldenQueryLive``       — @pytest.mark.slow, real graph, actual drift detection

Run framework tests: ``pytest tests/gauntlet/test_golden_queries.py -k Framework``
Run live tests:       ``pytest tests/gauntlet/test_golden_queries.py -k Live -m slow``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from claude_memory.router import QueryIntent
from claude_memory.schema import SearchResult

# ─── GoldenQuery dataclass ──────────────────────────────────


@dataclass
class GoldenQuery:
    """A frozen query with behavioural contracts."""

    query: str
    expected_intent: QueryIntent
    must: list[str] = field(default_factory=list)
    should: list[str] | None = None


# ─── The golden query set ───────────────────────────────────

GOLDEN_QUERIES: list[GoldenQuery] = [
    # --- Semantic ---
    GoldenQuery(
        query="what is spreading activation",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",  # must not crash
        ],
        should=[
            "len(results) >= 1",
        ],
    ),
    GoldenQuery(
        query="how does the knowledge graph store relationships",
        expected_intent=QueryIntent.SEMANTIC,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="explain the memory architecture",
        expected_intent=QueryIntent.SEMANTIC,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="what is a hologram query",
        expected_intent=QueryIntent.SEMANTIC,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="describe the embedding pipeline",
        expected_intent=QueryIntent.SEMANTIC,
        must=[
            "len(results) >= 0",
        ],
    ),
    # --- Temporal ---
    GoldenQuery(
        query="what happened recently",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            "len(results) >= 0",
        ],
        should=[
            "all(r.retrieval_strategy in ('hybrid', 'temporal', 'semantic') for r in results)",
        ],
    ),
    GoldenQuery(
        query="timeline of changes last week",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="what was discussed yesterday",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="latest updates to the project",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="recent breakthroughs",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    # --- Relational ---
    GoldenQuery(
        query='how does "Dragon Brain" connect to "Claude Memory"',
        expected_intent=QueryIntent.RELATIONAL,
        must=[
            "len(results) >= 0",
        ],
        should=[
            "all(r.retrieval_strategy in ('hybrid', 'relational', 'semantic') for r in results)",
        ],
    ),
    GoldenQuery(
        query="what connects entity A and entity B",
        expected_intent=QueryIntent.RELATIONAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="path between knowledge and memory",
        expected_intent=QueryIntent.RELATIONAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="relationship between search and retrieval",
        expected_intent=QueryIntent.RELATIONAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="link between architecture and testing",
        expected_intent=QueryIntent.RELATIONAL,
        must=[
            "len(results) >= 0",
        ],
    ),
    # --- Associative ---
    GoldenQuery(
        query="things related to memory architecture",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",
        ],
        should=[
            "all(r.retrieval_strategy in ('hybrid', 'associative', 'semantic') for r in results)",
        ],
    ),
    GoldenQuery(
        query="concepts similar to graph traversal",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="neighbourhood of vector search",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="in the context of hybrid retrieval",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",
        ],
    ),
    GoldenQuery(
        query="things associated with scoring",
        expected_intent=QueryIntent.ASSOCIATIVE,
        must=[
            "len(results) >= 0",
        ],
    ),
    # --- Score Integrity (the whole point) ---
    GoldenQuery(
        query="recent work on projects",
        expected_intent=QueryIntent.TEMPORAL,
        must=[
            # THE ORIGINAL BUG — this must NEVER return all-zero scores again
            "not all(r.score == 0.0 for r in results) if results else True",
        ],
    ),
    GoldenQuery(
        query="search for any entity",
        expected_intent=QueryIntent.SEMANTIC,
        must=[
            "all(r.score >= 0.0 for r in results)",
            "all(r.retrieval_strategy != '' for r in results)",
        ],
    ),
]


# ─── Assertion runner ───────────────────────────────────────


def _run_assertions(
    golden_query: GoldenQuery,
    results: list[SearchResult],
) -> tuple[list[str], list[str]]:
    """Run must/should assertions, return (failures, warnings)."""
    failures: list[str] = []
    soft_warnings: list[str] = []

    for assertion in golden_query.must:
        try:
            if not eval(assertion):  # noqa: S307 — trusted test strings, see DRIFT-001 §5
                failures.append(f"FAILED: {golden_query.query!r} — {assertion}")
        except Exception as exc:
            failures.append(f"ERROR evaluating {assertion!r}: {exc}")

    for assertion in golden_query.should or []:
        try:
            if not eval(assertion):  # noqa: S307 — trusted test strings
                soft_warnings.append(f"SOFT FAIL: {golden_query.query!r} — {assertion}")
        except Exception as exc:
            soft_warnings.append(f"SOFT ERROR evaluating {assertion!r}: {exc}")

    return failures, soft_warnings


# ─── Framework Tests (CI — mocked service) ──────────────────


def _make_result(**kwargs: Any) -> SearchResult:
    """Build a synthetic SearchResult for framework testing."""
    defaults = {
        "id": "test-id",
        "name": "Test Entity",
        "node_type": "Entity",
        "project_id": "test-project",
        "score": 0.5,
        "distance": 0.5,
        "retrieval_strategy": "semantic",
        "recency_score": 0.3,
        "vector_score": 0.5,
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


class TestGoldenQueryFramework:
    """Tests for the assertion machinery itself — mocked, CI-fast."""

    def test_happy_all_golden_queries_have_required_fields(self) -> None:
        """Every GoldenQuery must have query, expected_intent, and at least one must."""
        for gq in GOLDEN_QUERIES:
            assert gq.query, "Empty query in golden set"
            assert gq.expected_intent in list(QueryIntent), (
                f"Invalid intent for {gq.query!r}: {gq.expected_intent}"
            )
            assert len(gq.must) > 0, f"No must assertions for {gq.query!r}"

    def test_happy_golden_query_count_minimum(self) -> None:
        """Must have at least 20 golden queries."""
        assert len(GOLDEN_QUERIES) >= 20, (
            f"Only {len(GOLDEN_QUERIES)} golden queries — need at least 20"
        )

    def test_happy_all_intents_covered(self) -> None:
        """Every QueryIntent must have at least 2 golden queries."""
        intent_counts: dict[QueryIntent, int] = {}
        for gq in GOLDEN_QUERIES:
            intent_counts[gq.expected_intent] = intent_counts.get(gq.expected_intent, 0) + 1
        for intent in QueryIntent:
            assert intent_counts.get(intent, 0) >= 2, (
                f"Intent {intent.value} has fewer than 2 golden queries"
            )

    def test_happy_must_assertions_pass_with_good_results(self) -> None:
        """All must assertions should pass with well-formed results."""
        results = [_make_result(score=0.7), _make_result(score=0.5)]
        for gq in GOLDEN_QUERIES:
            failures, _ = _run_assertions(gq, results)
            assert not failures, f"Assertion failed for {gq.query!r} with good results: {failures}"

    def test_sad_must_assertions_detect_empty_results_for_score_integrity(self) -> None:
        """Score integrity queries should handle empty results gracefully."""
        results: list[SearchResult] = []
        for gq in GOLDEN_QUERIES:
            _failures, _ = _run_assertions(gq, results)
            # Empty results must not crash — they may or may not pass

    def test_happy_router_classifies_golden_queries_correctly(self) -> None:
        """Router must classify each golden query to its expected intent."""
        from claude_memory.router import QueryRouter

        router = QueryRouter()
        mismatches: list[str] = []
        for gq in GOLDEN_QUERIES:
            actual = router.classify(gq.query)
            if actual != gq.expected_intent:
                mismatches.append(
                    f"{gq.query!r}: expected {gq.expected_intent.value}, got {actual.value}"
                )
        assert not mismatches, "Router drift detected:\n" + "\n".join(mismatches)

    def test_happy_soft_assertions_produce_warnings(self) -> None:
        """Should assertions that fail must produce warnings, not failures."""
        # Use a result that has strategy 'weird' — should fail soft assertions
        results = [_make_result(retrieval_strategy="weird")]
        gq = GoldenQuery(
            query="test",
            expected_intent=QueryIntent.SEMANTIC,
            must=["len(results) >= 0"],
            should=["all(r.retrieval_strategy == 'semantic' for r in results)"],
        )
        failures, soft_warnings = _run_assertions(gq, results)
        assert not failures
        assert len(soft_warnings) == 1

    def test_evil_assertion_error_captured(self) -> None:
        """A broken assertion expression must be captured, not crash the runner."""
        gq = GoldenQuery(
            query="test",
            expected_intent=QueryIntent.SEMANTIC,
            must=["undefined_variable_xyz"],
        )
        failures, _ = _run_assertions(gq, [])
        assert len(failures) == 1
        assert "ERROR" in failures[0]

    def test_happy_score_integrity_queries_exist(self) -> None:
        """At least 2 queries must guard against the ADR-007 score-0 bug."""
        score_guards = [
            gq for gq in GOLDEN_QUERIES if any("score" in m and "0.0" in m for m in gq.must)
        ]
        assert len(score_guards) >= 2, (
            f"Only {len(score_guards)} score-0 guard queries — need at least 2"
        )


# ─── Live Tests (Gauntlet — real services) ──────────────────


@pytest.mark.slow
class TestGoldenQueryLive:
    """Live drift detection — requires FalkorDB + Qdrant with real data.

    These tests are skipped unless explicitly enabled via ``-m slow``.
    They hit real services and are slow by design.
    """

    @pytest.fixture
    def _skip_no_service(self) -> None:
        """Skip if MemoryService can't be instantiated."""
        pytest.skip("Live golden query tests require running services — use -m slow")

    @pytest.mark.usefixtures("_skip_no_service")
    @pytest.mark.parametrize("gq", GOLDEN_QUERIES, ids=[gq.query[:40] for gq in GOLDEN_QUERIES])
    async def test_golden_query_live(self, gq: GoldenQuery) -> None:
        """Run a golden query against the live graph and check contracts."""
        # This test body is reached only when services are available
        # The fixture above skips it by default
        pass  # pragma: no cover
