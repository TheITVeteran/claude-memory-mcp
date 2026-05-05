"""SQLite FTS5 full-text search store for lexical retrieval.

Provides BM25-based keyword search as a complementary channel to
vector (semantic) search. FTS5 excels at exact term matching, rare
keywords, and named entities that embedding models may miss.

Architecture:
    - SQLite database stored at ``~/.claude-memory/fts_index.db``
    - Single ``entities_fts`` virtual table with FTS5 tokenizer
    - Write path: called from CRUD on entity create/update/observe
    - Read path: called from search pipeline as a retrieval channel

Thread safety: SQLite in WAL mode supports concurrent readers with
one writer. All writes go through ``_get_conn()`` which returns a
per-thread connection.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default location for the FTS index
_DEFAULT_DB_DIR = Path.home() / ".claude-memory"
_DB_FILENAME = "fts_index.db"


class FTSStore:
    """SQLite FTS5 full-text search index for memory entities.

    Each entity is indexed by its ID, name, node_type, description,
    and observations (concatenated). BM25 scoring is used for ranking.

    Args:
        db_path: Path to the SQLite database file. If None, uses
            the default location (``~/.claude-memory/fts_index.db``).
            Pass ``:memory:`` for in-memory testing.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_dir = Path(os.getenv("CLAUDE_MEMORY_DIR", str(_DEFAULT_DB_DIR)))
            db_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = str(db_dir / _DB_FILENAME)
        else:
            self._db_path = str(db_path)

        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Create the FTS5 virtual table if it doesn't exist.

        Includes migration: if the old schema (without project_id) is
        detected, drops and recreates with the new column.
        """
        conn = self._get_conn()

        # Check if table exists and has the project_id column
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entities_fts'"
        )
        row = cursor.fetchone()
        if row and "project_id" not in row[0]:
            logger.info("Migrating FTS schema to add project_id column")
            conn.execute("DROP TABLE entities_fts")

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                entity_id UNINDEXED,
                project_id UNINDEXED,
                name,
                node_type,
                description,
                observations,
                tokenize='porter unicode61'
            )
        """)
        conn.commit()

    def index_entity(  # noqa: PLR0913
        self,
        entity_id: str,
        name: str,
        node_type: str = "Entity",
        description: str = "",
        observations: str = "",
        project_id: str = "",
    ) -> None:
        """Index or update an entity in the FTS store.

        Uses DELETE + INSERT (FTS5 doesn't support UPDATE well).
        Silently handles empty or None fields.

        Args:
            entity_id: Unique entity identifier.
            name: Entity name.
            node_type: Entity type label.
            description: Entity description/content.
            observations: Concatenated observation text.
            project_id: Project scope for filtering.
        """
        conn = self._get_conn()
        try:
            # Delete existing entry if present
            conn.execute(
                "DELETE FROM entities_fts WHERE entity_id = ?",
                (entity_id,),
            )
            # Insert new entry
            conn.execute(
                """INSERT INTO entities_fts
                   (entity_id, project_id, name, node_type, description, observations)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    project_id or "",
                    name or "",
                    node_type or "Entity",
                    description or "",
                    observations or "",
                ),
            )
            conn.commit()
        except sqlite3.Error:
            logger.error("FTS index_entity failed for %s", entity_id, exc_info=True)
            raise

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from the FTS index.

        Args:
            entity_id: Entity to remove.
        """
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM entities_fts WHERE entity_id = ?",
                (entity_id,),
            )
            conn.commit()
        except sqlite3.Error:
            logger.error("FTS remove_entity failed for %s", entity_id, exc_info=True)
            raise

    def search(
        self,
        query: str,
        limit: int = 10,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for entities matching the query using BM25.

        Args:
            query: Free-text search query.
            limit: Maximum number of results.
            project_id: Optional project scope filter.

        Returns:
            List of dicts with keys: entity_id, name, node_type,
            snippet, bm25_score. Sorted by BM25 relevance (best first).
        """
        if not query or not query.strip():
            return []

        conn = self._get_conn()
        try:
            # Escape FTS5 special characters and build query
            safe_query = self._sanitize_query(query)
            if not safe_query:
                return []

            if project_id:
                cursor = conn.execute(
                    """SELECT entity_id, name, node_type,
                              snippet(entities_fts, 4, '<b>', '</b>', '...', 32) as snippet,
                              bm25(entities_fts) as score
                       FROM entities_fts
                       WHERE entities_fts MATCH ? AND project_id = ?
                       ORDER BY score
                       LIMIT ?""",
                    (safe_query, project_id, limit),
                )
            else:
                cursor = conn.execute(
                    """SELECT entity_id, name, node_type,
                              snippet(entities_fts, 4, '<b>', '</b>', '...', 32) as snippet,
                              bm25(entities_fts) as score
                       FROM entities_fts
                       WHERE entities_fts MATCH ?
                       ORDER BY score
                       LIMIT ?""",
                    (safe_query, limit),
                )
            results = []
            for row in cursor:
                results.append(
                    {
                        "entity_id": row[0],
                        "name": row[1],
                        "node_type": row[2],
                        "snippet": row[3],
                        "bm25_score": -row[
                            4
                        ],  # FTS5 bm25() returns negative; negate for natural order
                    }
                )
            return results
        except sqlite3.OperationalError:
            # Malformed query or FTS error — return empty gracefully
            logger.debug("FTS search failed for query=%r", query, exc_info=True)
            return []

    def count(self) -> int:
        """Return the number of indexed entities."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM entities_fts")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """Delete all entries from the FTS index."""
        conn = self._get_conn()
        conn.execute("DELETE FROM entities_fts")
        conn.commit()

    def close(self) -> None:
        """Close the thread-local database connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Sanitize a user query for FTS5 MATCH syntax.

        Strips FTS5 operators and wraps individual terms with implicit
        AND semantics (FTS5 default). Handles quoted phrases.
        """
        # Remove FTS5 special operators that could cause syntax errors
        cleaned = query.replace("*", "").replace("(", "").replace(")", "")
        cleaned = cleaned.replace(":", " ").replace("^", " ")

        # Split into terms, rejecting empty ones
        terms = [t.strip() for t in cleaned.split() if t.strip()]
        if not terms:
            return ""

        # FTS5 implicit AND: space-separated terms
        return " ".join(terms)
