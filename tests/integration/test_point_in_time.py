"""PR-2: Point-in-time query integration test (regression witness).

Creates 3 entities at known timestamps, queries with a middle-timestamp
cutoff, and asserts only the 2 oldest are returned.

This test FAILS on the pre-PR codebase (Qdrant payload lacks created_at)
and PASSES after PR-2 adds the created_at field.

Requires: RUN_INTEGRATION=1, Docker, testcontainers-python.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from testcontainers.qdrant import QdrantContainer
from testcontainers.redis import RedisContainer

from claude_memory.schema import EntityCreateParams, PointInTimeQueryParams
from claude_memory.tools import MemoryService
from claude_memory.vector_store import QdrantVectorStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 to run testcontainers integration suite",
    ),
]


@pytest.fixture
def falkordb_container():
    """Spin up a FalkorDB container matching production v4.14.11."""
    container = RedisContainer("falkordb/falkordb:v4.14.11")
    container.start()
    yield container
    try:
        container.stop()
    except Exception:  # noqa: S110
        pass


@pytest.fixture
def qdrant_container():
    """Spin up a Qdrant container matching production v1.16.3."""
    container = QdrantContainer("qdrant/qdrant:v1.16.3")
    container.start()
    yield container
    try:
        container.stop()
    except Exception:  # noqa: S110
        pass


@pytest.fixture
async def memory_service(
    falkordb_container,
    qdrant_container,
) -> AsyncGenerator[MemoryService, None]:
    """Configure MemoryService against the running test containers."""
    host = falkordb_container.get_container_host_ip()
    port = int(falkordb_container.get_exposed_port(6379))

    q_host = qdrant_container.get_container_host_ip()
    q_port = int(qdrant_container.get_exposed_port(6333))

    vector_store = QdrantVectorStore(host=q_host, port=q_port, vector_size=1536)

    embedder = MagicMock()
    embedder.encode.return_value = [0.1] * 1536

    svc = MemoryService(
        embedding_service=embedder,
        vector_store=vector_store,
        host=host,
        port=port,
    )

    yield svc


@pytest.mark.asyncio
async def test_point_in_time_returns_only_entities_before_cutoff(memory_service):
    """Regression witness: PIT query filters on created_at.

    Pre-PR-2: created_at is absent from Qdrant payload → Range filter
    returns empty (wrong answer).
    Post-PR-2: created_at is stored as float timestamp → filter works.
    """
    # Create 3 entities with controlled timestamps.
    # We can't control the created_at directly (it's set inside create_entity),
    # so we create them with small delays and capture the timestamps.
    entities = []
    for i in range(3):
        params = EntityCreateParams(
            name=f"pit_entity_{i}",
            node_type="Concept",
            project_id="test_pit",
            properties={"description": f"Entity {i} for PIT test"},
        )
        result = await memory_service.create_entity(params)
        entities.append(result)
        # Small delay to ensure distinct created_at timestamps
        time.sleep(0.1)

    # Use the 3rd entity's creation time as the cutoff — should return
    # entities 0 and 1 (created before entity 2).
    # We need a timestamp AFTER entity 1 but BEFORE entity 2.
    # Since we have a 100ms gap, use the midpoint.

    # Get the created_at timestamps from the graph
    node_0 = await memory_service.repo.get_node(entities[0].id)
    node_1 = await memory_service.repo.get_node(entities[1].id)
    node_2 = await memory_service.repo.get_node(entities[2].id)

    assert node_0 is not None
    assert node_1 is not None
    assert node_2 is not None

    ts_1 = datetime.fromisoformat(node_1["created_at"])
    ts_2 = datetime.fromisoformat(node_2["created_at"])

    # Cutoff: after entity 1, before entity 2
    cutoff = ts_1 + (ts_2 - ts_1) / 2

    # Query with cutoff
    pit_params = PointInTimeQueryParams(
        query_text="Entity for PIT test",
        as_of=cutoff.isoformat(),
    )
    results = await memory_service.point_in_time_query(pit_params)

    # Should return exactly entities 0 and 1
    result_ids = {r["id"] for r in results}
    expected_ids = {entities[0].id, entities[1].id}

    assert expected_ids.issubset(result_ids), (
        f"Expected PIT query to include entities 0 and 1. "
        f"Got IDs: {result_ids}, expected at least: {expected_ids}"
    )
    assert entities[2].id not in result_ids, (
        f"Entity 2 (created after cutoff) should NOT be in PIT results. Got IDs: {result_ids}"
    )
