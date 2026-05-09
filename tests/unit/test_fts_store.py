"""Gold Stack tests for FTSStore (Tier 1.2).

Tests follow the 3-evil/1-sad/1-happy naming convention.
"""

from __future__ import annotations

import pytest

from claude_memory.fts_store import FTSStore


@pytest.fixture()
def fts() -> FTSStore:
    """In-memory FTS store for isolated testing."""
    store = FTSStore(db_path=":memory:")
    yield store
    store.close()


@pytest.fixture()
def populated_fts(fts: FTSStore) -> FTSStore:
    """FTS store pre-loaded with test data."""
    fts.index_entity("e1", "Python Programming", "Concept", "A high-level scripting language")
    fts.index_entity("e2", "Java Spring", "Framework", "Enterprise Java framework for web apps")
    fts.index_entity("e3", "Python Flask", "Framework", "Lightweight Python web framework")
    fts.index_entity("e4", "Database Design", "Concept", "Relational schema normalization")
    return fts


# ── Happy Path ───────────────────────────────────────────────────────


class TestHappyFTSSearch:
    """Core functionality: index, search, remove."""

    def test_happy_search_returns_matching_entities(self, populated_fts: FTSStore) -> None:
        """Search finds entities matching query terms."""
        results = populated_fts.search("Python")
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"Python Programming", "Python Flask"}

    def test_happy_search_returns_bm25_scores(self, populated_fts: FTSStore) -> None:
        """BM25 scores are non-negative floats."""
        results = populated_fts.search("enterprise Java framework")
        assert len(results) >= 1
        for r in results:
            assert isinstance(r["bm25_score"], float)
            assert r["bm25_score"] >= 0.0

    def test_happy_index_and_count(self, fts: FTSStore) -> None:
        """Indexing entities increments the count."""
        assert fts.count() == 0
        fts.index_entity("e1", "Test", "Entity", "test description")
        assert fts.count() == 1
        fts.index_entity("e2", "Test2", "Entity", "another description")
        assert fts.count() == 2

    def test_happy_remove_entity(self, populated_fts: FTSStore) -> None:
        """Removing an entity decrements the count and excludes from search."""
        before = populated_fts.count()
        populated_fts.remove_entity("e1")
        assert populated_fts.count() == before - 1
        results = populated_fts.search("Python Programming")
        assert not any(r["entity_id"] == "e1" for r in results)

    def test_happy_reindex_updates_content(self, fts: FTSStore) -> None:
        """Re-indexing an entity replaces old content, not duplicates."""
        fts.index_entity("e1", "Old Name", "Entity", "old description")
        assert fts.count() == 1
        fts.index_entity("e1", "New Name", "Entity", "new description unique_keyword")
        assert fts.count() == 1  # should NOT duplicate
        results = fts.search("unique_keyword")
        assert len(results) == 1
        assert results[0]["name"] == "New Name"


# ── Sad Path ─────────────────────────────────────────────────────────


class TestSadFTSSearch:
    """Edge cases that should degrade gracefully."""

    def test_sad1_empty_query_returns_empty(self, populated_fts: FTSStore) -> None:
        """Empty string query returns empty list, no crash."""
        assert populated_fts.search("") == []

    def test_sad1_whitespace_query_returns_empty(self, populated_fts: FTSStore) -> None:
        """Whitespace-only query returns empty list."""
        assert populated_fts.search("   ") == []

    def test_sad1_no_match_returns_empty(self, populated_fts: FTSStore) -> None:
        """Query with no matches returns empty list."""
        assert populated_fts.search("xyznotfoundzzz") == []

    def test_sad1_remove_nonexistent_no_crash(self, fts: FTSStore) -> None:
        """Removing a non-existent entity doesn't crash."""
        fts.remove_entity("nonexistent_id")  # should not raise


# ── Evil Path ────────────────────────────────────────────────────────


class TestEvilFTSSearch:
    """Adversarial inputs that should not crash the system."""

    def test_evil1_fts5_syntax_injection(self, populated_fts: FTSStore) -> None:
        """FTS5 special characters in query don't crash."""
        # These would cause syntax errors in raw FTS5 MATCH
        dangerous_queries = [
            'name:"Python" OR 1=1',
            "NEAR(Python Flask)",
            "Python*",
            "(Python) AND (Java)",
            "Python ^ 2",
        ]
        for q in dangerous_queries:
            # Should not raise — graceful degradation
            results = populated_fts.search(q)
            assert isinstance(results, list), f"Query {q!r} returned non-list"

    def test_evil1_unicode_query(self, populated_fts: FTSStore) -> None:
        """Unicode in query doesn't crash."""
        results = populated_fts.search("Python 编程 日本語")
        assert isinstance(results, list)

    def test_evil1_very_long_query(self, populated_fts: FTSStore) -> None:
        """Extremely long query doesn't crash."""
        long_query = "Python " * 500
        results = populated_fts.search(long_query)
        assert isinstance(results, list)

    def test_evil1_sql_injection(self, populated_fts: FTSStore) -> None:
        """SQL injection attempt in query is safely handled."""
        results = populated_fts.search("'; DROP TABLE entities_fts; --")
        assert isinstance(results, list)
        # Table should still work
        assert populated_fts.count() > 0

    def test_evil1_empty_entity_fields(self, fts: FTSStore) -> None:
        """Indexing entity with empty/None fields doesn't crash."""
        fts.index_entity("e1", "", "", "", "")
        assert fts.count() == 1

    def test_evil1_observations_field_searchable(self, fts: FTSStore) -> None:
        """Observations text is searchable via FTS."""
        fts.index_entity(
            "e1",
            "Meeting Notes",
            "Event",
            "Team standup",
            observations="Alice mentioned the deployment pipeline is broken",
        )
        results = fts.search("deployment pipeline broken")
        assert len(results) == 1
        assert results[0]["entity_id"] == "e1"
