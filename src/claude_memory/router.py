"""Adaptive query routing — rule-based intent classification and dispatch.

Routes queries to the optimal retrieval strategy based on keyword patterns.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from claude_memory.schema import (
    SearchAssociativeParams,
    SearchMemoryParams,
    TemporalQueryParams,
    TraversePathParams,
)

if TYPE_CHECKING:  # pragma: no cover
    from claude_memory.tools import MemoryService

_MIN_QUOTED_ENTITIES = 2

logger = logging.getLogger(__name__)


class QueryIntent(StrEnum):
    """Classified intent of a user query."""

    SEMANTIC = "semantic"
    ASSOCIATIVE = "associative"
    TEMPORAL = "temporal"
    RELATIONAL = "relational"


# ── Keyword patterns (compiled once at import time) ─────────────────

_TEMPORAL_KEYWORDS: list[str] = [
    "when",
    "timeline",
    "chronolog",
    "history of",
    "last week",
    "last month",
    "yesterday",
    "before",
    "after",
    "recent",
    "earliest",
    "latest",
    "over time",
    "sequence",
]

_RELATIONAL_KEYWORDS: list[str] = [
    "connect",
    "path between",
    "link between",
    "bridge",
    "relationship between",
    "how does .+ relate to",
    "what connects",
]

_ASSOCIATIVE_KEYWORDS: list[str] = [
    "associated with",
    "related to",
    "similar to",
    "reminds me of",
    "in the context of",
    "neighbourhood of",
    "neighborhood of",
    "cluster around",
    "spreading",
]

_TEMPORAL_RE = re.compile(
    "|".join(re.escape(k) if "." not in k else k for k in _TEMPORAL_KEYWORDS),
    re.IGNORECASE,
)
_RELATIONAL_RE = re.compile(
    "|".join(k for k in _RELATIONAL_KEYWORDS),
    re.IGNORECASE,
)
_ASSOCIATIVE_RE = re.compile(
    "|".join(k for k in _ASSOCIATIVE_KEYWORDS),
    re.IGNORECASE,
)


class QueryRouter:
    """Rule-based query router — classifies intent and dispatches to strategy."""

    def classify(self, query: str) -> QueryIntent:
        """Classify the intent of a natural-language query.

        Priority order: TEMPORAL > RELATIONAL > ASSOCIATIVE > SEMANTIC.
        """
        if not query:
            return QueryIntent.SEMANTIC

        # 1. Temporal — strongest signal
        if _TEMPORAL_RE.search(query):
            return QueryIntent.TEMPORAL

        # 2. Relational — mentions connections between things
        if _RELATIONAL_RE.search(query):
            return QueryIntent.RELATIONAL

        # 3. Associative — context / neighbourhood queries
        if _ASSOCIATIVE_RE.search(query):
            return QueryIntent.ASSOCIATIVE

        # 4. Default: semantic vector search
        return QueryIntent.SEMANTIC

    @staticmethod
    def get_channel_weights(intent: QueryIntent) -> dict[str, float]:
        """Return per-channel weights for soft routing.

        All channels always get non-zero base weights. The detected
        intent AMPLIFIES the relevant channel instead of suppressing
        the others (soft routing vs hard routing).

        Returns:
            Dict mapping channel name to weight multiplier.
        """
        # Base weights — every channel always contributes
        weights = {
            "vector": 1.0,
            "fts": 0.8,
            "entity": 0.6,
            "temporal": 0.3,
            "relational": 0.3,
            "associative": 0.3,
        }

        # Intent-specific boosts
        if intent == QueryIntent.TEMPORAL:
            weights["temporal"] = 1.5
            weights["vector"] = 0.7
        elif intent == QueryIntent.RELATIONAL:
            weights["relational"] = 1.5
            weights["vector"] = 0.7
        elif intent == QueryIntent.ASSOCIATIVE:
            weights["associative"] = 1.5
            weights["vector"] = 0.8
        # SEMANTIC: vector stays at 1.0, others at base

        return weights

    async def route(  # noqa: PLR0913
        self,
        query: str,
        service: MemoryService,
        *,
        intent: QueryIntent | None = None,
        limit: int = 10,
        project_id: str | None = None,
        temporal_window_days: int = 7,
        **kwargs: Any,
    ) -> list[Any]:
        """Dispatch query to the appropriate retrieval strategy.

        Args:
            query: The natural-language query string.
            service: MemoryService providing all retrieval backends.
            intent: Optional override — skips auto-classification.
            limit: Maximum results to return.
            project_id: Optional project scope.
            temporal_window_days: Lookback window for temporal queries (default 7).
            **kwargs: Extra params forwarded to the underlying method.

        Returns:
            List of results from the selected strategy.
        """
        if not query:
            return []

        resolved_intent = intent or self.classify(query)
        logger.info("Routing query to %s strategy", resolved_intent.value)

        if resolved_intent == QueryIntent.TEMPORAL:
            return await self._route_temporal(
                service, query, limit, project_id, temporal_window_days
            )

        if resolved_intent == QueryIntent.RELATIONAL:
            return await self._route_relational(service, query)

        if resolved_intent == QueryIntent.ASSOCIATIVE:
            return await self._route_associative(service, query, limit, project_id, **kwargs)

        # Default: SEMANTIC — search() returns {"results": [...], "metadata": {...}}
        params = SearchMemoryParams(query=query, limit=limit, project_id=project_id)
        response = await service.search(params)
        return response.get("results", []) if isinstance(response, dict) else response

    # ── Private dispatch helpers ─────────────────────────────────────

    @staticmethod
    async def _route_temporal(
        service: MemoryService,
        query: str,
        limit: int,
        project_id: str | None,
        temporal_window_days: int = 7,
    ) -> list[Any]:
        """Route to timeline query with parameterised window.

        Since temporal queries from natural language rarely include exact
        date ranges, we default to the last ``temporal_window_days`` days.
        """
        now = datetime.now(UTC)
        params = TemporalQueryParams(
            start=now - timedelta(days=temporal_window_days),
            end=now,
            limit=limit,
            project_id=project_id,
        )
        return await service.query_timeline(params)

    @staticmethod
    async def _route_relational(
        service: MemoryService,
        query: str,
    ) -> list[Any]:
        """Route to graph traversal.

        Attempts to extract two entity references from the query.
        Falls back to semantic search if entity extraction fails.
        """
        # Simple heuristic: find quoted strings or CamelCase words
        quoted = re.findall(r'"([^"]+)"', query)
        if len(quoted) >= _MIN_QUOTED_ENTITIES:
            t_params = TraversePathParams(from_id=quoted[0], to_id=quoted[1])
            return await service.traverse_path(t_params)  # type: ignore[no-any-return]

        # Fallback: semantic search (we can't reliably extract entities)
        response = await service.search(SearchMemoryParams(query=query, limit=10))
        return response.get("results", []) if isinstance(response, dict) else response

    @staticmethod
    async def _route_associative(
        service: MemoryService,
        query: str,
        limit: int,
        project_id: str | None,
        **kwargs: Any,
    ) -> list[Any]:
        """Route to spreading-activation search."""
        # Assume decay, max_hops might be in kwargs, but we will safely pass known defaults
        decay = kwargs.get("decay", 0.5)
        max_hops = kwargs.get("max_hops", 3)
        return await service.search_associative(
            SearchAssociativeParams(
                query=query, limit=limit, project_id=project_id, decay=decay, max_hops=max_hops
            )
        )
