import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
from testcontainers.qdrant import QdrantContainer
from testcontainers.redis import RedisContainer

from claude_memory.schema import SearchMemoryParams
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
    container = RedisContainer("falkordb/falkordb:v4.14.11")
    container.start()
    yield container
    try:
        container.stop()
    except Exception:
        pass


@pytest.fixture
def qdrant_container():
    container = QdrantContainer("qdrant/qdrant:v1.16.3")
    container.start()
    yield container
    try:
        container.stop()
    except Exception:
        pass


@pytest.fixture
async def memory_service(
    falkordb_container, qdrant_container
) -> AsyncGenerator[MemoryService, None]:
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
async def test_evil_kill_falkordb_mid_search(memory_service, falkordb_container):
    falkordb_container.get_wrapped_container().kill()
    result = await memory_service.search(SearchMemoryParams(query="test"))
    assert result["metadata"]["channels"]["temporal"] == "degraded"


@pytest.mark.asyncio
async def test_evil_kill_qdrant_mid_search(memory_service, qdrant_container):
    qdrant_container.get_wrapped_container().kill()
    result = await memory_service.search(SearchMemoryParams(query="test"))
    assert result["metadata"]["channels"]["vector"] == "failed"


@pytest.mark.asyncio
async def test_evil_concurrent_search_no_crosstalk(memory_service):
    original_search = memory_service.fts_store.search

    def side_effect(*args, **kwargs):
        query_arg = kwargs.get("query", args[0] if args else "")
        if "q1" in query_arg:
            import time

            time.sleep(0.5)
            raise Exception("FTS down")
        return original_search(*args, **kwargs)

    from unittest.mock import MagicMock

    memory_service.fts_store.search = MagicMock(side_effect=side_effect)

    t1 = asyncio.create_task(memory_service.search(SearchMemoryParams(query="q1")))
    await asyncio.sleep(0.1)
    t2 = asyncio.create_task(memory_service.search(SearchMemoryParams(query="q2")))

    r1, r2 = await asyncio.gather(t1, t2)
    # Check that they don't crosstalk metadata
    assert r1["metadata"]["channels"]["fts"] == "failed"
    assert r2["metadata"]["channels"]["fts"] == "ok"


@pytest.mark.asyncio
async def test_sad_include_meta_false_strips_metadata(memory_service):
    from claude_memory.schema import EntityCreateParams

    await memory_service.create_entity(
        EntityCreateParams(
            name="test_entity", node_type="Concept", project_id="test", properties={}
        )
    )
    from claude_memory import server
    from claude_memory.server import search_memory

    server.service = memory_service
    result = await search_memory(query="test_entity", include_meta=False)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_neutral_service_returns_dict_shape(memory_service):
    result = await memory_service.search(SearchMemoryParams(query="test"))
    assert isinstance(result, dict)
    assert "metadata" in result
