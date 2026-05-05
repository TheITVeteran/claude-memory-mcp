"""CRUD operations for the Claude Memory system.

Provides entity, relationship, and observation create/update/delete logic.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .interfaces import Embedder, VectorStore
    from .lock_manager import LockManager
    from .ontology import OntologyManager
    from .repository import MemoryRepository
    from .schema import (
        EntityCommitReceipt,
        EntityCreateParams,
        EntityDeleteParams,
        EntityUpdateParams,
        RelationshipCreateParams,
        RelationshipDeleteParams,
    )

logger = logging.getLogger(__name__)


def _compute_entity_embedding_text(
    repo: "MemoryRepository",
    entity_id: str | None,
    name: str,
    node_type: str,
    description: str,
) -> str:
    """Compute the text used to embed an entity.

    Combines entity metadata with observation content for semantically
    rich embeddings. This is the **single source of truth** for entity
    embedding text — all create/update paths must use this function.

    Caps at 20 observations x 500 chars each to stay well under
    BGE-M3's 8K token context window.

    Args:
        repo: Memory repository (for fetching observations).
        entity_id: Entity ID (None for new entities during creation).
        name: Entity name.
        node_type: Entity type.
        description: Entity description.

    Returns:
        Combined text string ready for ``embedder.encode()``.
    """
    max_observations = 20
    max_chars_per_obs = 500

    parts = [name, node_type, description]

    if entity_id:
        observations = repo.get_observations_for_entity(entity_id, limit=max_observations)
        for obs in observations:
            content = obs.get("content", "")
            if content:
                parts.append(content[:max_chars_per_obs])

    return " ".join(p for p in parts if p)


class CrudMixin:
    """Entity/Relationship/Observation CRUD — mixed into MemoryService."""

    # Inherited attributes (set by MemoryService.__init__)
    repo: "MemoryRepository"
    embedder: "Embedder"
    vector_store: "VectorStore"
    ontology: "OntologyManager"
    lock_manager: "LockManager"

    async def create_entity(self, params: "EntityCreateParams") -> "EntityCommitReceipt":
        """Creates an entity node in the graph."""
        from .schema import EntityCommitReceipt  # noqa: PLC0415

        project_id = params.project_id

        async with self.lock_manager.lock(project_id):
            # Validate Dynamic Type
            if not self.ontology.is_valid_type(params.node_type):
                raise ValueError(
                    f"Invalid memory type: '{params.node_type}'. "
                    f"Allowed types: {self.ontology.list_types()}"
                )

            start_time = datetime.now()
            logger.info("Creating entity: %s (%s)", params.name, params.node_type)

            props = params.properties.copy()
            props["id"] = params.properties.get("id") or str(uuid.uuid4())
            props.update(
                {
                    "name": params.name,
                    "node_type": params.node_type,
                    "project_id": params.project_id,
                    "certainty": params.certainty,
                    "evidence": params.evidence,
                    "salience_score": 1.0,
                    "retrieval_count": 0,
                    "occurred_at": params.properties.get(
                        "occurred_at", datetime.now(UTC).isoformat()
                    ),
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )

            # Compute embedding (AI Layer)
            text_to_embed = _compute_entity_embedding_text(
                self.repo,
                entity_id=None,  # new entity, no observations yet
                name=params.name,
                node_type=params.node_type,
                description=props.get("description", ""),
            )
            embedding = self.embedder.encode(text_to_embed)

            # 1. Write to Graph (FalkorDB) - Source of Truth for Structure
            node_props = self.repo.create_node(params.node_type, props)

            # 2. Write to Vector Engine (Qdrant) - Source of Truth for Search
            node_id = str(node_props["id"])

            payload = {
                "name": params.name,
                "node_type": params.node_type,
                "project_id": params.project_id,
            }
            try:
                await self.vector_store.upsert(id=node_id, vector=embedding, payload=payload)
            except Exception:
                logger.error(
                    "vector_upsert_failed for %s — raising to prevent split-brain", node_id
                )
                raise

            # 3. Index in FTS5 (lexical search channel)
            if hasattr(self, "fts_store"):
                try:
                    self.fts_store.index_entity(
                        entity_id=node_id,
                        name=params.name,
                        node_type=params.node_type,
                        description=props.get("description", ""),
                        project_id=params.project_id,
                    )
                except Exception:
                    logger.warning("FTS index failed for %s — non-fatal", node_id, exc_info=True)

            # 4. Link to most recent entity in same project via PRECEDED_BY
            warnings: list[str] = []
            try:
                prev = self.repo.get_most_recent_entity(project_id)
                if prev and prev.get("id") != node_id:
                    self.repo.create_edge(
                        prev["id"],
                        node_id,
                        "PRECEDED_BY",
                        {"created_at": datetime.now(UTC).isoformat()},
                    )
            except (ConnectionError, TimeoutError, OSError):
                msg = "PRECEDED_BY link failed — entity created without temporal link"
                logger.error(msg, exc_info=True)
                warnings.append(msg)

            result = node_props

            final_id = str(result["id"])
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            status = "created"

            # Get total count (for receipt)
            total_count = self.repo.get_total_node_count()

            return EntityCommitReceipt(
                id=final_id,
                name=params.name,
                status="committed",
                operation_time_ms=duration,
                total_memory_count=total_count,
                message=f"Successfully {status} '{params.name}' in the Infinite Graph.",
                warnings=warnings,
            )

    async def create_relationship(self, params: "RelationshipCreateParams") -> dict[str, Any]:
        """Creates a typed relationship between two entities."""

        source_node = self.repo.get_node(params.from_entity)

        if source_node and "project_id" in source_node:
            pass

        project_id = source_node.get("project_id") if source_node else None

        async def _do_create() -> dict[str, Any]:
            """Execute relationship creation inside the optional lock."""
            logger.info(
                "Creating relationship: %s -[%s]-> %s",
                params.from_entity,
                params.relationship_type,
                params.to_entity,
            )

            props = params.properties.copy()
            props["confidence"] = params.confidence
            props["weight"] = params.weight
            props["created_at"] = datetime.now(UTC).isoformat()
            if "id" not in props:
                props["id"] = str(uuid.uuid4())

            res = self.repo.create_edge(
                params.from_entity, params.to_entity, params.relationship_type, props
            )
            if not res:
                return {"error": "Could not create relationship. Check entity IDs."}
            return res

        if project_id:
            async with self.lock_manager.lock(project_id):
                return await _do_create()
        else:
            return await _do_create()

    async def update_entity(self, params: "EntityUpdateParams") -> dict[str, Any]:
        """Updates properties of an existing entity."""

        existing_node = self.repo.get_node(params.entity_id)
        if not existing_node:
            return {"error": "Entity not found"}

        project_id = existing_node.get("project_id")

        async def _do_update() -> dict[str, Any]:
            """Execute entity update inside the optional lock."""
            logger.info("Updating entity: %s", params.entity_id)

            props = params.properties.copy()
            timestamp = datetime.now(UTC).isoformat()
            props["updated_at"] = timestamp

            embedding = None
            merged_props = existing_node.copy()
            merged_props.update(props)

            desc = merged_props.get("description", "")
            name = merged_props.get("name", "")
            node_type = merged_props.get("node_type", "Entity")

            text_to_embed = _compute_entity_embedding_text(
                self.repo,
                entity_id=params.entity_id,
                name=name,
                node_type=node_type,
                description=desc,
            )
            embedding = self.embedder.encode(text_to_embed)

            # 1. Update Graph
            updated_node = self.repo.update_node(params.entity_id, props)

            # 2. Update Vector Store
            payload = {
                "name": name,
                "node_type": node_type,
                "project_id": project_id,
            }
            try:
                await self.vector_store.upsert(
                    id=params.entity_id,
                    vector=embedding,
                    payload=payload,
                )
            except Exception:
                logger.error(
                    "vector_upsert_failed for %s — raising to prevent split-brain", params.entity_id
                )
                raise

            return updated_node  # type: ignore[no-any-return]

        if project_id:
            async with self.lock_manager.lock(project_id):
                return await _do_update()
        else:
            return await _do_update()

    async def _safe_vector_delete(self, entity_id: str) -> None:
        """Delete vector — raises on failure to prevent split-brain."""
        try:
            await self.vector_store.delete(entity_id)
        except Exception:
            logger.error("vector_delete_failed for %s — raising to prevent split-brain", entity_id)
            raise

    def _safe_fts_delete(self, entity_id: str) -> None:
        """Remove entity from FTS index — non-fatal on failure."""
        if hasattr(self, "fts_store"):
            try:
                self.fts_store.remove_entity(entity_id)
            except Exception:
                logger.warning("FTS delete failed for %s — non-fatal", entity_id, exc_info=True)

    async def delete_entity(self, params: "EntityDeleteParams") -> dict[str, Any]:
        """Deletes an entity."""

        existing_node = self.repo.get_node(params.entity_id)
        if not existing_node:
            return {"error": "Entity not found"}

        project_id = existing_node.get("project_id")

        async def _do_delete() -> dict[str, Any]:
            """Execute entity deletion inside the optional lock."""
            logger.info("Deleting entity: %s (%s)", params.entity_id, params.reason)

            if params.soft_delete:
                self.repo.update_node(
                    params.entity_id,
                    {"status": "archived", "archived_at": datetime.now(UTC).isoformat()},
                )
                await self._safe_vector_delete(params.entity_id)
                self._safe_fts_delete(params.entity_id)
                return {"status": "archived", "id": params.entity_id}
            else:
                self.repo.delete_node(params.entity_id)
                await self._safe_vector_delete(params.entity_id)
                self._safe_fts_delete(params.entity_id)
                return {"status": "deleted", "id": params.entity_id}

        if project_id:
            async with self.lock_manager.lock(project_id):
                return await _do_delete()
        else:
            return await _do_delete()

    async def delete_relationship(self, params: "RelationshipDeleteParams") -> dict[str, Any]:
        """Deletes a relationship.

        Acquires project lock if the edge's source node has a project_id,
        to prevent interleaving with concurrent graph mutations.
        """
        # Look up the edge's source node project_id for locking
        project_id: str | None = None
        try:
            res = self.repo.execute_cypher(
                "MATCH (s)-[r]->() WHERE r.id = $id RETURN s.project_id",
                {"id": params.relationship_id},
            )
            if res.result_set and res.result_set[0][0]:
                project_id = str(res.result_set[0][0])
        except Exception:
            logger.warning(
                "Could not resolve project_id for relationship %s — proceeding unlocked",
                params.relationship_id,
                exc_info=True,
            )

        async def _do_delete() -> dict[str, Any]:
            self.repo.delete_edge(params.relationship_id)
            return {"status": "deleted", "id": params.relationship_id}

        if project_id:
            async with self.lock_manager.lock(project_id):
                return await _do_delete()
        else:
            return await _do_delete()
