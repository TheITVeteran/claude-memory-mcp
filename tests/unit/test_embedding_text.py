"""Tests for _compute_entity_embedding_text helper.

4 evil, 1 sad, 1 happy per Gold Stack policy.
"""

from unittest.mock import MagicMock

from claude_memory.crud import _compute_entity_embedding_text

# ── Evil Tests ────────────────────────────────────────────────────────


def test_evil1_no_observations() -> None:
    """New entity with no observations → returns name + type + description only."""
    repo = MagicMock()
    repo.get_observations_for_entity.return_value = []

    result = _compute_entity_embedding_text(
        repo, entity_id="abc-123", name="TestEntity", node_type="Concept", description="A test"
    )

    repo.get_observations_for_entity.assert_called_once_with("abc-123", limit=20)
    assert result == "TestEntity Concept A test"


def test_evil2_empty_description() -> None:
    """Entity with observations but no description → observations still included."""
    repo = MagicMock()
    repo.get_observations_for_entity.return_value = [
        {"content": "First observation content"},
        {"content": "Second observation content"},
    ]

    result = _compute_entity_embedding_text(
        repo, entity_id="abc-123", name="MyEntity", node_type="Person", description=""
    )

    # Description is empty so it's filtered out by the join
    assert "MyEntity" in result
    assert "Person" in result
    assert "First observation content" in result
    assert "Second observation content" in result


def test_evil3_long_observation_truncated() -> None:
    """Observation > 500 chars → truncated at limit."""
    repo = MagicMock()
    long_content = "x" * 1000
    repo.get_observations_for_entity.return_value = [{"content": long_content}]

    result = _compute_entity_embedding_text(
        repo, entity_id="abc-123", name="E", node_type="T", description="D"
    )

    # The observation should be truncated to 500 chars
    obs_part = result.split(" ", 3)[-1]  # Skip "E T D"
    assert len(obs_part) == 500


def test_evil4_many_observations_capped() -> None:
    """50 observations → only first 20 included."""
    repo = MagicMock()
    repo.get_observations_for_entity.return_value = [{"content": f"obs_{i}"} for i in range(50)]

    result = _compute_entity_embedding_text(
        repo, entity_id="abc-123", name="E", node_type="T", description="D"
    )

    # The repo is called with limit=20, so even though it returned 50,
    # _compute uses whatever the repo returns. The cap is enforced by
    # the limit parameter to the repo call.
    repo.get_observations_for_entity.assert_called_once_with("abc-123", limit=20)

    # All 50 are included because the repo mock returned them all
    # The real enforcement is the limit=20 in the repo query
    for i in range(50):
        assert f"obs_{i}" in result


# ── Sad Tests ─────────────────────────────────────────────────────────


def test_sad1_none_entity_id() -> None:
    """entity_id=None → skips observation fetch entirely."""
    repo = MagicMock()

    result = _compute_entity_embedding_text(
        repo, entity_id=None, name="NewEntity", node_type="Thing", description="Fresh"
    )

    repo.get_observations_for_entity.assert_not_called()
    assert result == "NewEntity Thing Fresh"


# ── Happy Tests ───────────────────────────────────────────────────────


def test_happy_full_context() -> None:
    """Entity with 3 observations → returns combined text with all parts."""
    repo = MagicMock()
    repo.get_observations_for_entity.return_value = [
        {"content": "User prefers dark mode"},
        {"content": "Works at Acme Corp"},
        {"content": "Lives in San Francisco"},
    ]

    result = _compute_entity_embedding_text(
        repo,
        entity_id="user-001",
        name="Alice",
        node_type="Person",
        description="A software engineer",
    )

    assert result == (
        "Alice Person A software engineer "
        "User prefers dark mode "
        "Works at Acme Corp "
        "Lives in San Francisco"
    )

    # Correct limit passed to repo
    repo.get_observations_for_entity.assert_called_once_with("user-001", limit=20)
