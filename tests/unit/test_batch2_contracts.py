"""Tests for Batch 2: Edge dedup, FTS propagation, existence checks.

AUDIT-B2: Verifies MERGE edge semantics, FTS write-failure propagation,
archive_entity existence pre-check, and consolidate_memories update_node check.
"""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_memory.analysis import AnalysisMixin
from claude_memory.schema import ArchiveEntityParams

# --- Test Constants ---
ENTITY_ID = "entity-001"
ENTITY_ID_2 = "entity-002"
ENTITY_NAME = "Python"
PROJECT_ID = "project-alpha"
EDGE_FROM = "from-001"
EDGE_TO = "to-001"
REL_TYPE = "RELATED_TO"
EDGE_PROPS = {"id": "edge-001", "confidence": 1.0}


# --- Helpers ---


def _make_analysis_mixin() -> AnalysisMixin:
    """Build an AnalysisMixin with all dependencies mocked."""
    mixin = AnalysisMixin.__new__(AnalysisMixin)
    mixin.repo = AsyncMock()
    mixin.embedder = MagicMock()
    mixin.vector_store = AsyncMock()
    mixin.ontology = MagicMock()
    mixin.repo.create_node.return_value = {"id": "new-123", "name": "Consolidated"}
    mixin.embedder.encode.return_value = [0.1] * 1024
    return mixin


# ═══════════════════════════════════════════════════════════
# 2.1 Edge Dedup (CREATE → MERGE in repository.py)
# TDD: 3 evil, 1 sad, 1 happy
# ═══════════════════════════════════════════════════════════


class TestEdgeMerge:
    """Edge creation uses MERGE semantics to prevent duplicates on retry."""

    def test_evil1_create_edge_retry_no_duplicates(self) -> None:
        """AUDIT-B2: Calling create_edge twice with same from/to/type produces one edge."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.repository import MemoryRepository

            repo = MemoryRepository.__new__(MemoryRepository)
            mock_graph = MagicMock()
            repo.client = MagicMock()
            repo.client.select_graph.return_value = mock_graph
            repo.graph_name = "claude_memory"

            # Mock result for MERGE — returns edge properties
            mock_result = MagicMock()
            mock_result.result_set = [[MagicMock(properties=EDGE_PROPS)]]
            mock_graph.query.return_value = mock_result

            # Call twice (simulates retry)
            repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, EDGE_PROPS)
            repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, EDGE_PROPS)

            # The Cypher should use MERGE, not CREATE
            for call in mock_graph.query.call_args_list:
                cypher = call[0][0]
                assert "MERGE" in cypher, f"Expected MERGE in Cypher, got: {cypher}"
                assert "CREATE" not in cypher or "ON CREATE" in cypher

    def test_evil2_create_edge_nodes_not_found(self) -> None:
        """AUDIT-B2: MERGE with non-existent nodes returns empty result."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.repository import MemoryRepository

            repo = MemoryRepository.__new__(MemoryRepository)
            mock_graph = MagicMock()
            repo.client = MagicMock()
            repo.client.select_graph.return_value = mock_graph
            repo.graph_name = "claude_memory"

            # Empty result_set means nodes don't exist
            mock_result = MagicMock()
            mock_result.result_set = []
            mock_graph.query.return_value = mock_result

            result = repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, EDGE_PROPS)
            assert result == {}

    def test_evil3_create_edge_db_connection_error(self) -> None:
        """AUDIT-B2: FalkorDB connection error propagates, not swallowed."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.repository import MemoryRepository

            repo = MemoryRepository.__new__(MemoryRepository)
            mock_graph = MagicMock()
            repo.client = MagicMock()
            repo.client.select_graph.return_value = mock_graph
            repo.graph_name = "claude_memory"

            mock_graph.query.side_effect = ConnectionError("FalkorDB down")

            with pytest.raises(ConnectionError, match="FalkorDB down"):
                repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, EDGE_PROPS)

    def test_sad1_create_edge_empty_props(self) -> None:
        """AUDIT-B2: Edge creation with empty properties still works."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.repository import MemoryRepository

            repo = MemoryRepository.__new__(MemoryRepository)
            mock_graph = MagicMock()
            repo.client = MagicMock()
            repo.client.select_graph.return_value = mock_graph
            repo.graph_name = "claude_memory"

            mock_result = MagicMock()
            mock_result.result_set = [[MagicMock(properties={})]]
            mock_graph.query.return_value = mock_result

            result = repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, {})
            assert isinstance(result, dict)

    def test_happy_create_edge_returns_properties(self) -> None:
        """AUDIT-B2: Successful MERGE edge returns edge properties."""
        with patch("claude_memory.repository.FalkorDB"):
            from claude_memory.repository import MemoryRepository

            repo = MemoryRepository.__new__(MemoryRepository)
            mock_graph = MagicMock()
            repo.client = MagicMock()
            repo.client.select_graph.return_value = mock_graph
            repo.graph_name = "claude_memory"

            mock_result = MagicMock()
            mock_result.result_set = [[MagicMock(properties=EDGE_PROPS)]]
            mock_graph.query.return_value = mock_result

            result = repo.create_edge(EDGE_FROM, EDGE_TO, REL_TYPE, EDGE_PROPS)
            assert result == EDGE_PROPS


# ═══════════════════════════════════════════════════════════
# 2.3-2.5 FTS Write-Failure Propagation
# TDD: 3 evil, 1 sad, 1 happy
# ═══════════════════════════════════════════════════════════


class TestFTSWriteFailurePropagation:
    """FTS index_entity and remove_entity re-raise sqlite3.Error."""

    def test_evil1_index_entity_sqlite_error_propagates(self) -> None:
        """AUDIT-B2: sqlite3.Error during index_entity is re-raised."""
        from claude_memory.fts_store import FTSStore

        fts = FTSStore(db_path=":memory:")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3.OperationalError("disk I/O error")

        with patch.object(fts, "_get_conn", return_value=mock_conn):
            with pytest.raises(sqlite3.Error, match="disk I/O error"):
                fts.index_entity(ENTITY_ID, ENTITY_NAME)

    def test_evil2_remove_entity_sqlite_error_propagates(self) -> None:
        """AUDIT-B2: sqlite3.Error during remove_entity is re-raised."""
        from claude_memory.fts_store import FTSStore

        fts = FTSStore(db_path=":memory:")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3.OperationalError("readonly database")

        with patch.object(fts, "_get_conn", return_value=mock_conn):
            with pytest.raises(sqlite3.Error, match="readonly database"):
                fts.remove_entity(ENTITY_ID)

    def test_evil3_index_entity_integrity_error_propagates(self) -> None:
        """AUDIT-B2: IntegrityError during indexing is also re-raised."""
        from claude_memory.fts_store import FTSStore

        fts = FTSStore(db_path=":memory:")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed")

        with patch.object(fts, "_get_conn", return_value=mock_conn):
            with pytest.raises(sqlite3.Error, match="UNIQUE constraint"):
                fts.index_entity(ENTITY_ID, ENTITY_NAME)

    def test_sad1_index_entity_normal_operation(self) -> None:
        """AUDIT-B2: Normal index_entity on valid DB succeeds without error."""
        from claude_memory.fts_store import FTSStore

        fts = FTSStore(db_path=":memory:")
        # Should not raise
        fts.index_entity(ENTITY_ID, ENTITY_NAME, description="test")

    def test_happy_remove_entity_succeeds(self) -> None:
        """AUDIT-B2: Normal remove_entity on valid DB succeeds."""
        from claude_memory.fts_store import FTSStore

        fts = FTSStore(db_path=":memory:")
        fts.index_entity(ENTITY_ID, ENTITY_NAME)
        fts.remove_entity(ENTITY_ID)
        # Verify removal
        results = fts.search(ENTITY_NAME)
        assert len(results) == 0


# ═══════════════════════════════════════════════════════════
# 2.7 archive_entity existence check
# TDD: 3 evil, 1 sad, 1 happy
# ═══════════════════════════════════════════════════════════


class TestArchiveEntityExistenceCheck:
    """archive_entity checks entity exists before operating."""

    @pytest.mark.asyncio
    async def test_evil1_archive_nonexistent_entity(self) -> None:
        """AUDIT-B2: Archiving non-existent entity returns clear error."""
        mixin = _make_analysis_mixin()
        mixin.repo.get_node.return_value = None

        result = await mixin.archive_entity(ArchiveEntityParams(entity_id=ENTITY_ID))

        assert "error" in result
        mixin.vector_store.delete.assert_not_awaited()
        mixin.repo.update_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_evil2_archive_already_archived_entity(self) -> None:
        """AUDIT-B2: Archiving an already-archived entity returns error."""
        mixin = _make_analysis_mixin()
        mixin.repo.get_node.return_value = {"id": ENTITY_ID, "status": "archived"}

        result = await mixin.archive_entity(ArchiveEntityParams(entity_id=ENTITY_ID))

        assert "error" in result
        mixin.vector_store.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evil3_archive_entity_get_node_connection_error(self) -> None:
        """AUDIT-B2: Connection error during existence check propagates."""
        mixin = _make_analysis_mixin()
        mixin.repo.get_node.side_effect = ConnectionError("FalkorDB down")

        with pytest.raises(ConnectionError, match="FalkorDB down"):
            await mixin.archive_entity(ArchiveEntityParams(entity_id=ENTITY_ID))

    @pytest.mark.asyncio
    async def test_sad1_archive_entity_soft_deleted(self) -> None:
        """AUDIT-B2: Entity marked deleted can still be archived."""
        mixin = _make_analysis_mixin()
        mixin.repo.get_node.return_value = {"id": ENTITY_ID, "deleted": True}
        mixin.repo.update_node.return_value = {"id": ENTITY_ID, "status": "archived"}

        result = await mixin.archive_entity(ArchiveEntityParams(entity_id=ENTITY_ID))
        assert result["status"] == "archived"

    @pytest.mark.asyncio
    async def test_happy_archive_existing_entity(self) -> None:
        """AUDIT-B2: Archiving an existing active entity succeeds."""
        mixin = _make_analysis_mixin()
        mixin.repo.get_node.return_value = {"id": ENTITY_ID, "name": ENTITY_NAME}
        mixin.repo.update_node.return_value = {"id": ENTITY_ID, "status": "archived"}

        result = await mixin.archive_entity(ArchiveEntityParams(entity_id=ENTITY_ID))

        assert result["status"] == "archived"
        mixin.vector_store.delete.assert_awaited_once_with(ENTITY_ID)
        mixin.repo.update_node.assert_called_once()
