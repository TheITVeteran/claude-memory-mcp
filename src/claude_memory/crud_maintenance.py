"""Maintenance operations extracted from crud.py.

Provides background task management (salience updates) and observation
creation — mixed into MemoryService alongside CrudMixin.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from claude_memory.crud import _compute_entity_embedding_text

if TYPE_CHECKING:  # pragma: no cover
    from .interfaces import Embedder, VectorStore
    from .repository import MemoryRepository
    from .schema import ObservationParams

logger = logging.getLogger(__name__)


class CrudMaintenanceMixin:
    """Background tasks and observation CRUD — mixed into MemoryService."""

    # Inherited attributes (set by MemoryService.__init__)
    repo: "MemoryRepository"
    embedder: "Embedder"
    vector_store: "VectorStore"
    _background_tasks: set[asyncio.Task[None]]

    def _fire_salience_update(self, ids: list[str]) -> None:
        """Fire-and-forget salience increment so search returns immediately."""

        async def _do_update() -> None:
            """Execute the salience increment in the background."""
            try:
                self.repo.increment_salience(ids)
            except (ConnectionError, TimeoutError, OSError) as exc:
                logger.error("Background salience update failed: %s", exc)

        task = asyncio.create_task(_do_update())
        # Hold a reference so it isn't garbage-collected mid-flight
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def flush_background_tasks(self) -> None:
        """Await all pending background tasks (salience updates, etc.).

        Useful for graceful shutdown and deterministic test assertions.
        """
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks)

    async def add_observation(self, params: "ObservationParams") -> dict[str, Any]:
        """Adds an observation node linked to an entity."""
        obs_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()

        query = """
        MATCH (e) WHERE e.id = $entity_id
        CREATE (o:Observation {
            id: $obs_id,
            content: $content,
            certainty: $certainty,
            evidence: $evidence,
            created_at: $timestamp,
            project_id: e.project_id
        })
        CREATE (e)-[:HAS_OBSERVATION]->(o)
        RETURN o
        """
        params_dict = {
            "entity_id": params.entity_id,
            "obs_id": obs_id,
            "content": params.content,
            "certainty": params.certainty,
            "evidence": params.evidence,
            "timestamp": timestamp,
        }
        res = self.repo.execute_cypher(query, params_dict)
        if not res.result_set:
            return {"error": "Entity not found"}

        obs_props = cast(dict[str, Any], res.result_set[0][0].properties)

        # E-3: Embed observation content into vector store
        try:
            embedding = self.embedder.encode(params.content)
            payload = {
                "name": params.content[:80],
                "node_type": "Observation",
                "entity_id": params.entity_id,
                "project_id": obs_props.get("project_id"),
            }
            await self.vector_store.upsert(
                id=str(obs_props["id"]), vector=embedding, payload=payload
            )
        except Exception:
            logger.error(
                "observation_vector_upsert_failed for %s — graph write succeeded",
                obs_props.get("id"),
            )
            raise

        # Re-embed the parent entity with the new observation included
        try:
            entity = self.repo.get_node(params.entity_id)
            if entity:
                entity_text = _compute_entity_embedding_text(
                    self.repo,
                    entity_id=params.entity_id,
                    name=entity.get("name", ""),
                    node_type=entity.get("node_type", "Entity"),
                    description=entity.get("description", ""),
                )
                entity_embedding = self.embedder.encode(entity_text)
                entity_payload = {
                    "name": entity.get("name", ""),
                    "node_type": entity.get("node_type", "Entity"),
                    "project_id": entity.get("project_id"),
                }
                await self.vector_store.upsert(
                    id=params.entity_id,
                    vector=entity_embedding,
                    payload=entity_payload,
                )
        except Exception:
            logger.error(
                "entity_re_embed_failed after observation add for %s -- "
                "observation was stored, but entity embedding is stale",
                params.entity_id,
            )
            # Do NOT raise -- observation was successfully stored
            # Stale entity embedding is degraded quality, not data loss

        # Re-index FTS with updated content (Tier 2.4 fix)
        if hasattr(self, "fts_store"):
            try:
                entity = entity if "entity" in dir() else self.repo.get_node(params.entity_id)
                if entity:
                    # Fetch all observations for this entity
                    obs_query = (
                        "MATCH (e:Entity {id: $eid})-[:HAS_OBSERVATION]->(o) "
                        "RETURN o.content ORDER BY o.created_at ASC"
                    )
                    obs_res = self.repo.execute_cypher(obs_query, {"eid": params.entity_id})
                    obs_texts = [row[0] for row in obs_res.result_set if row[0]]

                    self.fts_store.index_entity(
                        entity_id=params.entity_id,
                        name=entity.get("name", ""),
                        node_type=entity.get("node_type", "Entity"),
                        description=entity.get("description", ""),
                        observations=" ".join(obs_texts),
                        project_id=entity.get("project_id", ""),
                    )
            except Exception:
                logger.warning(
                    "FTS re-index failed after observation add for %s",
                    params.entity_id,
                )

        return obs_props
