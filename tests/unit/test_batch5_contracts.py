"""Tests for Batch 5: Lock Manager + Concurrency.

AUDIT-B5: Verifies that graph-mutating operations acquire project locks
to prevent concurrent interleaving corruption.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.schema import ObservationParams, RelationshipDeleteParams

# ═══════════════════════════════════════════════════════════
# 5.1 delete_relationship must acquire lock
# ═══════════════════════════════════════════════════════════


class TestDeleteRelationshipLocking:
    """delete_relationship must hold the project lock during graph mutation."""

    @pytest.mark.asyncio
    async def test_evil1_delete_relationship_acquires_lock(self) -> None:
        """AUDIT-B5: delete_relationship must call lock_manager.lock().

        Without this, concurrent deletes on the same project can
        corrupt graph state by interleaving with create_entity or
        update_entity on the same project.
        """
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            # delete_edge needs to find the relationship's source node
            # to get project_id — return a mock node with project_id
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[["test-project"]])
            svc.repo.delete_edge.return_value = True

            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = RelationshipDeleteParams(relationship_id="rel-123", reason="test")
            await svc.delete_relationship(params)

            # The lock MUST have been acquired
            svc.lock_manager.lock.assert_called_once()
            lock_ctx.__aenter__.assert_called_once()
            lock_ctx.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_evil2_delete_relationship_without_project_still_executes(self) -> None:
        """AUDIT-B5: If relationship has no project scope, still deletes (no lock)."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            # No project found for this edge
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[])
            svc.repo.delete_edge.return_value = True

            svc.lock_manager = MagicMock()

            params = RelationshipDeleteParams(relationship_id="orphan-rel", reason="cleanup")
            result = await svc.delete_relationship(params)

            # Should still delete even without project scope
            svc.repo.delete_edge.assert_called_once_with("orphan-rel")
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_evil3_delete_relationship_lock_uses_correct_project(self) -> None:
        """AUDIT-B5: Lock is acquired for the correct project_id from the edge."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[["project-alpha"]])
            svc.repo.delete_edge.return_value = True

            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = RelationshipDeleteParams(relationship_id="rel-456", reason="test")
            await svc.delete_relationship(params)

            # Must lock the CORRECT project
            svc.lock_manager.lock.assert_called_once_with("project-alpha")

    @pytest.mark.asyncio
    async def test_sad1_delete_relationship_returns_status(self) -> None:
        """AUDIT-B5: Successful delete returns proper status dict."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[])
            svc.repo.delete_edge.return_value = True
            svc.lock_manager = MagicMock()

            params = RelationshipDeleteParams(relationship_id="rel-789", reason="obsolete")
            result = await svc.delete_relationship(params)

            assert result == {"status": "deleted", "id": "rel-789"}

    @pytest.mark.asyncio
    async def test_happy_delete_relationship_basic(self) -> None:
        """AUDIT-B5: Basic delete flow works end-to-end."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[["proj-1"]])
            svc.repo.delete_edge.return_value = True
            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = RelationshipDeleteParams(relationship_id="rel-abc", reason="refactor")
            result = await svc.delete_relationship(params)

            assert result["status"] == "deleted"
            svc.repo.delete_edge.assert_called_once_with("rel-abc")


# ═══════════════════════════════════════════════════════════
# 5.2 add_observation must acquire lock
# ═══════════════════════════════════════════════════════════


class TestAddObservationLocking:
    """add_observation must hold the project lock during graph + vector writes."""

    @pytest.mark.asyncio
    async def test_evil1_add_observation_acquires_lock(self) -> None:
        """AUDIT-B5: add_observation must acquire project lock.

        Without this, concurrent observations on the same entity
        can cause stale re-embedding — observation A writes, then
        observation B reads stale obs list, re-embeds without A.
        """
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()

            # execute_cypher returns: first call = obs creation, second = obs fetch
            obs_node = MagicMock()
            obs_node.properties = {"id": "obs-1", "project_id": "proj-x", "content": "test"}
            svc.repo.execute_cypher.side_effect = [
                # First: get project_id for locking
                MagicMock(result_set=[["proj-x"]]),
                # Second: CREATE observation
                MagicMock(result_set=[[obs_node]]),
                # Third: fetch all observations for re-embedding
                MagicMock(result_set=[["obs content"]]),
            ]
            svc.repo.get_node.return_value = {
                "name": "TestEntity",
                "node_type": "Entity",
                "description": "",
                "project_id": "proj-x",
            }

            svc.embedder = MagicMock()
            svc.embedder.encode.return_value = [0.1] * 1024
            svc.vector_store = AsyncMock()
            svc.fts_store = MagicMock()

            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = ObservationParams(entity_id="ent-1", content="new finding")
            await svc.add_observation(params)

            # Lock MUST have been acquired
            svc.lock_manager.lock.assert_called_once_with("proj-x")
            lock_ctx.__aenter__.assert_called_once()
            lock_ctx.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_evil2_add_observation_no_entity_skips_lock(self) -> None:
        """AUDIT-B5: If entity not found, no lock needed — early return."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            # Entity lookup returns empty (no entity)
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[])
            svc.lock_manager = MagicMock()

            params = ObservationParams(entity_id="nonexistent", content="data")
            result = await svc.add_observation(params)

            assert "error" in result
            # Lock should NOT be acquired for non-existent entity
            svc.lock_manager.lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_evil3_add_observation_lock_correct_project(self) -> None:
        """AUDIT-B5: Lock uses the entity's project_id, not a hardcoded value."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()

            obs_node = MagicMock()
            obs_node.properties = {"id": "obs-2", "project_id": "my-project", "content": "x"}
            svc.repo.execute_cypher.side_effect = [
                MagicMock(result_set=[["my-project"]]),
                MagicMock(result_set=[[obs_node]]),
                MagicMock(result_set=[]),
            ]
            svc.repo.get_node.return_value = {
                "name": "E",
                "node_type": "Entity",
                "description": "",
                "project_id": "my-project",
            }

            svc.embedder = MagicMock()
            svc.embedder.encode.return_value = [0.1] * 1024
            svc.vector_store = AsyncMock()
            svc.fts_store = MagicMock()

            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = ObservationParams(entity_id="ent-2", content="data")
            await svc.add_observation(params)

            svc.lock_manager.lock.assert_called_once_with("my-project")

    @pytest.mark.asyncio
    async def test_sad1_add_observation_entity_not_found(self) -> None:
        """AUDIT-B5: Non-existent entity returns error dict."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()
            svc.repo.execute_cypher.return_value = MagicMock(result_set=[])
            svc.lock_manager = MagicMock()

            params = ObservationParams(entity_id="ghost", content="data")
            result = await svc.add_observation(params)

            assert result == {"error": "Entity not found"}

    @pytest.mark.asyncio
    async def test_happy_add_observation_with_lock(self) -> None:
        """AUDIT-B5: Full happy path with lock acquisition."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.tools import MemoryService

            svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
            svc.repo = MagicMock()

            obs_node = MagicMock()
            obs_node.properties = {"id": "obs-ok", "project_id": "p", "content": "good"}
            svc.repo.execute_cypher.side_effect = [
                MagicMock(result_set=[["p"]]),
                MagicMock(result_set=[[obs_node]]),
                MagicMock(result_set=[["existing obs"]]),
            ]
            svc.repo.get_node.return_value = {
                "name": "N",
                "node_type": "Entity",
                "description": "",
                "project_id": "p",
            }

            svc.embedder = MagicMock()
            svc.embedder.encode.return_value = [0.1] * 1024
            svc.vector_store = AsyncMock()
            svc.fts_store = MagicMock()

            lock_ctx = AsyncMock()
            svc.lock_manager = MagicMock()
            svc.lock_manager.lock.return_value = lock_ctx

            params = ObservationParams(entity_id="ent-ok", content="insight")
            result = await svc.add_observation(params)

            assert result["id"] == "obs-ok"
            svc.lock_manager.lock.assert_called_once()
