"""One-shot backfill: add `created_at` (float timestamp) to existing Qdrant payloads.

Live-safe, zero-downtime. Uses cursor-based scroll — does not block
reads/writes.  Idempotent: skips points whose payload already has
`created_at`.

Run once after PR-2 merge:
    python scripts/backfill_created_at_payload.py

Expected runtime: <2 min at ~2228 points.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime as _dt

from falkordb import FalkorDB
from qdrant_client import AsyncQdrantClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "memory_embeddings")

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
GRAPH_NAME = os.getenv("FALKORDB_GRAPH", "claude_memory")

SCROLL_BATCH = 100


async def backfill() -> None:
    """Iterate all Qdrant points and backfill missing `created_at`."""
    client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    graph = db.select_graph(GRAPH_NAME)

    scanned = 0
    updated = 0
    skipped = 0
    missing_in_graph = 0
    errors = 0

    offset = None
    while True:
        records, next_offset = await client.scroll(
            collection_name=COLLECTION,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not records:
            break

        for point in records:
            scanned += 1
            payload = point.payload or {}

            # Idempotency: skip if already tagged
            if "created_at" in payload:
                skipped += 1
                continue

            # Look up created_at from FalkorDB by point ID.
            # Try Entity label first (indexed), then Observation.
            point_id = str(point.id)
            try:
                created_at_str = None
                for label in ("Entity", "Observation"):
                    res = graph.query(
                        f"MATCH (n:{label}) WHERE n.id = $id RETURN n.created_at",
                        {"id": point_id},
                    )
                    if res.result_set and res.result_set[0][0]:
                        created_at_str = res.result_set[0][0]
                        break

                if not created_at_str:
                    missing_in_graph += 1
                    logger.warning("No created_at in graph for point %s", point_id)
                    continue

                created_at_ts = _dt.fromisoformat(created_at_str).timestamp()

                await client.set_payload(
                    collection_name=COLLECTION,
                    payload={"created_at": created_at_ts},
                    points=[point_id],
                )
                updated += 1
            except Exception:
                errors += 1
                logger.exception("Error backfilling point %s", point_id)

        if next_offset is None:
            break
        offset = next_offset

    logger.info(
        "Backfill complete: scanned=%d updated=%d skipped=%d missing_in_graph=%d errors=%d",
        scanned,
        updated,
        skipped,
        missing_in_graph,
        errors,
    )
    await client.close()


if __name__ == "__main__":
    asyncio.run(backfill())
