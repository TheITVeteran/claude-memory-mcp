"""Tests for diff_knowledge_state — knowledge graph time-diff.

3 evil, 1 sad, 1 happy per Gold Stack policy.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from claude_memory.search import SearchMixin

# ── Fixtures ──────────────────────────────────────────────────────────


def _make_mixin() -> SearchMixin:
    """Create a SearchMixin instance with a mocked repo."""
    mixin = SearchMixin.__new__(SearchMixin)
    mixin.repo = MagicMock()
    mixin.embedder = MagicMock()
    mixin.vector_store = MagicMock()
    mixin.router = MagicMock()
    mixin.activation_engine = MagicMock()
    mixin.context_manager = MagicMock()
    return mixin


def _make_node(eid: str, name: str, **kwargs: object) -> SimpleNamespace:
    """Build a fake FalkorDB node for result_set rows."""
    props = {"id": eid, "name": name, **kwargs}
    return SimpleNamespace(properties=props)


def _empty_result() -> MagicMock:
    """Return a Cypher result with no rows."""
    r = MagicMock()
    r.result_set = []
    return r


# ── Evil Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evil1_same_timestamp() -> None:
    """start == end → ValueError (degenerate window)."""
    mixin = _make_mixin()
    t = datetime(2026, 3, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="must be before"):
        await mixin.diff_knowledge_state(as_of_start=t, as_of_end=t)


@pytest.mark.asyncio
async def test_evil2_start_after_end() -> None:
    """start > end → ValueError (inverted range)."""
    mixin = _make_mixin()
    t1 = datetime(2026, 4, 1, tzinfo=UTC)
    t2 = datetime(2026, 3, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="must be before"):
        await mixin.diff_knowledge_state(as_of_start=t1, as_of_end=t2)


@pytest.mark.asyncio
async def test_evil3_archived_entity_in_window() -> None:
    """Entity archived during window → shows in removed_entities."""
    mixin = _make_mixin()
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 4, 1, tzinfo=UTC)

    # At t1: entity "alpha" exists (created before t1, not archived yet)
    node_alpha = _make_node(
        "a1",
        "Alpha",
        created_at="2025-12-01T00:00:00+00:00",
        updated_at="2025-12-01T00:00:00+00:00",
        archived_at="2026-02-15T00:00:00+00:00",  # archived during window
    )
    start_result = MagicMock()
    start_result.result_set = [[node_alpha]]

    # At t2: alpha is archived → not in snapshot
    end_result = _empty_result()

    # Relationships and supersedes: empty
    empty = _empty_result()

    mixin.repo.execute_cypher = MagicMock(
        side_effect=[start_result, end_result, empty, empty, empty]
    )

    diff = await mixin.diff_knowledge_state(as_of_start=t1, as_of_end=t2)

    assert diff["summary"]["entities_removed"] == 1
    assert len(diff["removed_entities"]) == 1
    assert diff["removed_entities"][0]["id"] == "a1"
    assert diff["summary"]["entities_added"] == 0


# ── Sad Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sad1_empty_graph() -> None:
    """Empty graph at both timestamps → empty diff, all counts zero."""
    mixin = _make_mixin()
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 4, 1, tzinfo=UTC)

    empty = _empty_result()
    # 5 cypher calls: start entities, end entities, start rels, end rels, supersedes
    mixin.repo.execute_cypher = MagicMock(return_value=empty)

    diff = await mixin.diff_knowledge_state(as_of_start=t1, as_of_end=t2)

    assert diff["summary"]["entities_added"] == 0
    assert diff["summary"]["entities_removed"] == 0
    assert diff["summary"]["entities_evolved"] == 0
    assert diff["summary"]["relationships_added"] == 0
    assert diff["summary"]["relationships_removed"] == 0
    assert diff["summary"]["total_changes"] == 0
    assert diff["added_entities"] == []
    assert diff["removed_entities"] == []
    assert diff["evolved_entities"] == []
    assert diff["superseded"] == []


# ── Happy Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_full_diff() -> None:
    """Full diff with added, removed, evolved, and superseded entities."""
    mixin = _make_mixin()
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 4, 1, tzinfo=UTC)

    # Start snapshot: entities A and B
    node_a_start = _make_node(
        "a1",
        "Alpha",
        created_at="2025-12-01T00:00:00+00:00",
        updated_at="2025-12-01T00:00:00+00:00",
    )
    node_b = _make_node(
        "b1",
        "Bravo",
        created_at="2025-12-15T00:00:00+00:00",
        updated_at="2025-12-15T00:00:00+00:00",
    )
    start_entities = MagicMock()
    start_entities.result_set = [[node_a_start], [node_b]]

    # End snapshot: A (updated), C (new) — B was removed
    node_a_end = _make_node(
        "a1",
        "Alpha Updated",
        created_at="2025-12-01T00:00:00+00:00",
        updated_at="2026-03-01T00:00:00+00:00",  # updated during window
    )
    node_c = _make_node(
        "c1",
        "Charlie",
        created_at="2026-02-01T00:00:00+00:00",
        updated_at="2026-02-01T00:00:00+00:00",
    )
    end_entities = MagicMock()
    end_entities.result_set = [[node_a_end], [node_c]]

    # Relationships: r1 exists at start, r2 added at end
    start_rels = MagicMock()
    start_rels.result_set = [["r1", "RELATES_TO", "a1", "b1", "2025-12-20T00:00:00+00:00"]]
    end_rels = MagicMock()
    end_rels.result_set = [
        ["r1", "RELATES_TO", "a1", "b1", "2025-12-20T00:00:00+00:00"],
        ["r2", "PRECEDED_BY", "a1", "c1", "2026-02-01T00:00:00+00:00"],
    ]

    # Supersedes: B superseded by C
    supersedes_result = MagicMock()
    supersedes_result.result_set = [["b1", "Bravo", "c1", "Charlie"]]

    mixin.repo.execute_cypher = MagicMock(
        side_effect=[
            start_entities,
            end_entities,
            start_rels,
            end_rels,
            supersedes_result,
        ]
    )

    diff = await mixin.diff_knowledge_state(as_of_start=t1, as_of_end=t2)

    # C was added
    assert diff["summary"]["entities_added"] == 1
    added_ids = [e["id"] for e in diff["added_entities"]]
    assert "c1" in added_ids

    # B was removed
    assert diff["summary"]["entities_removed"] == 1
    removed_ids = [e["id"] for e in diff["removed_entities"]]
    assert "b1" in removed_ids

    # A evolved (updated_at > start)
    assert diff["summary"]["entities_evolved"] == 1
    evolved_ids = [e["id"] for e in diff["evolved_entities"]]
    assert "a1" in evolved_ids

    # r2 was added
    assert diff["summary"]["relationships_added"] == 1
    assert diff["summary"]["relationships_removed"] == 0

    # Supersedes B → C
    assert len(diff["superseded"]) == 1
    assert diff["superseded"][0]["old_id"] == "b1"
    assert diff["superseded"][0]["new_id"] == "c1"

    # Window is correct
    assert diff["window"]["start"] == t1.isoformat()
    assert diff["window"]["end"] == t2.isoformat()

    # Total = 1 added + 1 removed + 1 evolved + 1 rel added + 0 rel removed = 4
    assert diff["summary"]["total_changes"] == 4
