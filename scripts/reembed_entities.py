"""Re-embed all existing entities with observation content.

One-shot migration to fix the entity embedding quality issue
documented in SPEC-embedding-fix.md.

Usage:
    python scripts/reembed_entities.py [--dry-run] [--project PROJECT_ID]

Safe to run multiple times — idempotent. Progress is logged per entity.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from claude_memory.crud import _compute_entity_embedding_text
from claude_memory.embedding import EmbeddingService
from claude_memory.tools import MemoryService

logger = logging.getLogger(__name__)


async def main(dry_run: bool = False, project_id: str | None = None) -> None:
    """Re-embed all entities using observation-enriched text."""
    embedder = EmbeddingService()
    service = MemoryService(embedding_service=embedder)

    # Fetch all entity nodes
    all_ids = service.repo.get_all_node_ids(limit=10000)
    entities = []
    for eid in all_ids:
        node = service.repo.get_node(eid)
        if node:
            entities.append(node)

    if project_id:
        entities = [e for e in entities if e.get("project_id") == project_id]

    total = len(entities)
    print(f"Re-embedding {total} entities {'(DRY RUN)' if dry_run else ''}...")

    success = 0
    failed = 0
    skipped = 0
    start = time.monotonic()

    for i, entity in enumerate(entities):
        entity_id = entity.get("id", "")
        entity_name = entity.get("name", entity_id)[:50]
        try:
            text = _compute_entity_embedding_text(
                service.repo,
                entity_id=entity_id,
                name=entity.get("name", ""),
                node_type=entity.get("node_type", "Entity"),
                description=entity.get("description", ""),
            )

            if dry_run:
                print(f"[DRY] {i + 1}/{total} {entity_name} -> {len(text)} chars")
                skipped += 1
                continue

            embedding = service.embedder.encode(text)
            payload = {
                "name": entity.get("name", ""),
                "node_type": entity.get("node_type", "Entity"),
                "project_id": entity.get("project_id"),
            }
            await service.vector_store.upsert(id=entity_id, vector=embedding, payload=payload)
            success += 1
            if (i + 1) % 50 == 0 or i + 1 == total:
                elapsed = time.monotonic() - start
                rate = (i + 1) / elapsed
                print(f"{i + 1}/{total} OK ({rate:.1f} entities/s) {entity_name}")
        except Exception as e:
            failed += 1
            print(f"{i + 1}/{total} FAIL {entity_id}: {e}")

    elapsed = time.monotonic() - start
    print(f"\nDone in {elapsed:.1f}s: {success} success, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed entities with observation content")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would change, don't write"
    )
    parser.add_argument("--project", default=None, help="Filter to a specific project_id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(main(dry_run=args.dry_run, project_id=args.project))
