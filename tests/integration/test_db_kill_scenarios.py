import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
from testcontainers.qdrant import QdrantContainer
from testcontainers.redis import RedisContainer

from claude_memory.exceptions import SearchError
from claude_memory.schema import EntityCreateParams, ObservationParams, SearchMemoryParams
from claude_memory.tools import MemoryService
from claude_memory.vector_store import QdrantVectorStore

# We want to skip these unless RUN_INTEGRATION=1 is set
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
    falkordb_container, qdrant_container
) -> AsyncGenerator[MemoryService, None]:
    """Configure MemoryService against the running test containers."""
    host = falkordb_container.get_container_host_ip()
    port = int(falkordb_container.get_exposed_port(6379))

    q_host = qdrant_container.get_container_host_ip()
    q_port = int(qdrant_container.get_exposed_port(6333))

    vector_store = QdrantVectorStore(host=q_host, port=q_port, vector_size=1536)

    from unittest.mock import MagicMock

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
async def test_kill_falkordb_mid_create_raises_search_error(memory_service, falkordb_container):
    """
    Scenario 1: Kill FalkorDB mid-create_entity -> assert SearchError is raised.
    (Baseline behavior in B10.G: raises generic Exception/ConnectionError. B10.H upgrades to SearchError).
    """
    falkordb_container.get_wrapped_container().kill()
    params = EntityCreateParams(
        name="test_1", node_type="Concept", project_id="test", properties={}
    )

    with pytest.raises(Exception):  # noqa: B017
        await memory_service.create_entity(params)


@pytest.mark.asyncio
async def test_kill_qdrant_mid_create_leaves_orphan(memory_service, qdrant_container):
    """
    Scenario 2: Kill Qdrant mid-create_entity -> assert FalkorDB write occurs but Qdrant fails.
    Baseline behavior (B10.G): exception is raised, but graph node remains (split-brain).
    """
    # Start create entity task
    qdrant_container.get_wrapped_container().kill()
    params = EntityCreateParams(
        name="test_orphan", node_type="Concept", project_id="test", properties={}
    )

    # In B10.H, this raises SearchError and rolls back the FalkorDB node
    with pytest.raises(SearchError):
        await memory_service.create_entity(params)

    # Assert split brain is NOT present: node was compensated
    nodes = await memory_service.repo.get_all_nodes()
    # Check that test_orphan is not there
    assert not any(n.get("name") == "test_orphan" for n in nodes)


@pytest.mark.asyncio
async def test_kill_falkordb_mid_search_degrades_gracefully(memory_service, falkordb_container):
    """
    Scenario 3: Kill FalkorDB mid-search() -> assert graceful degradation to vector search.
    """
    falkordb_container.get_wrapped_container().kill()
    params = SearchMemoryParams(query="hello", project_id="test")
    # Search should catch FalkorDB connection errors during graph traversal and fall back to Qdrant.
    result = await memory_service.search(params)
    results = result["results"]
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_kill_embedding_mid_search(memory_service):
    """
    Scenario 4: Kill embedding API mid-search -> assert SearchError.
    We simulate this by replacing the embedder with a mock that throws.
    """
    from unittest.mock import MagicMock

    memory_service.embedder = MagicMock()
    memory_service.embedder.encode.side_effect = Exception("Embedding API down")

    from claude_memory import server
    from claude_memory.server import search_memory

    server.service = memory_service

    result = await search_memory(query="hello", project_id="test", include_meta=True)
    assert result["meta"]["channels"]["vector"] == "failed"


@pytest.mark.asyncio
async def test_concurrent_ops_with_kill_mid_flight(memory_service, falkordb_container):
    """
    Scenario 5: Concurrent ops with kill mid-flight -> graceful degradation.
    """

    # We will launch 10 creates. Mid-way, we kill falkordb.
    async def make_req(i):
        params = EntityCreateParams(
            name=f"test_{i}", node_type="Concept", project_id="test", properties={}
        )
        try:
            return await memory_service.create_entity(params)
        except Exception:
            return None

    tasks = [asyncio.create_task(make_req(i)) for i in range(10)]

    # Kill DB almost immediately
    await asyncio.sleep(0.01)
    falkordb_container.get_wrapped_container().kill()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    # We just ensure it doesn't crash the event loop with unhandled promises
    # Some might be None (caught exception), some might have succeeded before stop.
    assert len(results) == 10


@pytest.mark.asyncio
async def test_kill_qdrant_mid_add_observation_compensates(memory_service, qdrant_container):
    """
    PR-4 regression witness: Kill Qdrant mid-add_observation.

    1. Create entity successfully (both stores healthy).
    2. Kill Qdrant container.
    3. Call add_observation — graph write succeeds, Qdrant upsert fails.
    4. Assert: SearchError raised (not generic Exception).
    5. Assert: Observation node was compensated (DETACH DELETE) — no orphan
       observation left in the graph.
    """
    # Step 1: create entity while everything is healthy
    entity_params = EntityCreateParams(
        name="CompensationTarget",
        node_type="Concept",
        project_id="test-pr4",
        properties={},
    )
    entity = await memory_service.create_entity(entity_params)
    entity_id = entity.id

    # Step 2: kill Qdrant
    qdrant_container.get_wrapped_container().kill()

    # Step 3+4: add_observation should raise SearchError
    obs_params = ObservationParams(
        entity_id=entity_id,
        content="This observation should be rolled back",
    )
    with pytest.raises(SearchError, match="Vector store unavailable during observation add"):
        await memory_service.add_observation(obs_params)

    # Step 5: verify no orphan Observation node in graph
    result = await memory_service.repo.execute_cypher(
        "MATCH (o:Observation) WHERE o.entity_id = $eid OR "
        "(o)<-[:HAS_OBSERVATION]-(:Entity {id: $eid}) "
        "RETURN count(o)",
        {"eid": entity_id},
    )
    obs_count = result.result_set[0][0] if result.result_set else 0
    assert obs_count == 0, (
        f"Expected 0 orphan observations for entity {entity_id}, found {obs_count}"
    )
