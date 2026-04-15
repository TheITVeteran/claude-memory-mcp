"""Cross-encoder reranker client for post-merge result refinement.

Calls the /rerank endpoint on the embedding server to re-score
(query, document) pairs using a cross-encoder model. Falls back
gracefully if the server is unavailable or the endpoint doesn't exist.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Minimum number of results to trigger reranking — not worth the
# latency for tiny result sets.
_MIN_RERANK_CANDIDATES = 3

# HTTP status indicating the rerank endpoint is not deployed yet.
_HTTP_NOT_FOUND = 404


class RerankerClient:
    """HTTP client for the cross-encoder reranking endpoint."""

    def __init__(self, api_url: str | None = None, timeout: float = 15.0) -> None:
        self.api_url = api_url or os.getenv("EMBEDDING_API_URL", "http://localhost:8001")
        self.timeout = timeout
        self._available: bool | None = None  # tri-state: None = unchecked

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        text_key: str = "_text",
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank candidates by cross-encoder relevance score.

        Args:
            query: The search query.
            candidates: Merged result dicts from RRF. Each must have ``text_key``.
            text_key: Key in candidate dict containing the text to score against query.
            top_k: Max results to return (None = return all, reordered).

        Returns:
            Reranked list of candidates (same dicts, new order).
            Falls back to original order on any error.
        """
        if len(candidates) < _MIN_RERANK_CANDIDATES:
            return candidates

        documents = _build_documents(candidates, text_key)

        try:
            data = await self._call_rerank_api(query, documents, top_k or len(candidates))
            return _reorder_candidates(candidates, data["indices"], data["scores"])

        except httpx.HTTPStatusError as e:
            if e.response.status_code == _HTTP_NOT_FOUND:
                if self._available is not False:
                    logger.info("Rerank endpoint not available (404) — falling back to RRF order")
                    self._available = False
            else:
                logger.warning("Rerank request failed: %s", e)
            return candidates

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if self._available is not False:
                logger.info("Rerank service unreachable — falling back to RRF order: %s", e)
                self._available = False
            return candidates

        except Exception:
            logger.warning("Unexpected rerank error — falling back to RRF order", exc_info=True)
            return candidates

    async def _call_rerank_api(
        self, query: str, documents: list[str], top_k: int
    ) -> dict[str, Any]:
        """POST to the /rerank endpoint and return the JSON response."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api_url}/rerank",
                json={"query": query, "documents": documents, "top_k": top_k},
            )
            resp.raise_for_status()
            return resp.json()


def _build_documents(candidates: list[dict[str, Any]], text_key: str) -> list[str]:
    """Extract text from each candidate for the cross-encoder."""
    documents: list[str] = []
    for c in candidates:
        text = c.get(text_key, "")
        if not text:
            parts = [c.get("name", ""), c.get("entity_type", "")]
            text = " ".join(p for p in parts if p)
        documents.append(text or "unknown")
    return documents


def _reorder_candidates(
    candidates: list[dict[str, Any]],
    indices: list[int],
    scores: list[float],
) -> list[dict[str, Any]]:
    """Rebuild candidate list in cross-encoder score order."""
    reranked: list[dict[str, Any]] = []
    for idx, score in zip(indices, scores, strict=True):
        if 0 <= idx < len(candidates):
            candidate = dict(candidates[idx])
            candidate["_rerank_score"] = score
            reranked.append(candidate)

    logger.debug(
        "Reranked %d candidates (top score=%.3f, bottom=%.3f)",
        len(reranked),
        scores[0] if scores else 0,
        scores[-1] if scores else 0,
    )
    return reranked
