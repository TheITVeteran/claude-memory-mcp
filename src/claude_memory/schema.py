"""Pydantic schemas for memory entities, relationships, sessions, and search results."""

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# === ENUMS ===

NodeLabel = str  # Dynamic: Validated by OntologyManager

EdgeType = Literal[
    # Structural
    "DEPENDS_ON",
    "ENABLES",
    "BLOCKS",
    "CONTAINS",
    "PART_OF",
    # Temporal
    "EVOLVED_FROM",
    "SUPERSEDES",
    "PRECEDED_BY",
    "CONCURRENT_WITH",
    # Epistemic
    "CONTRADICTS",
    "SUPPORTS",
    "REJECTED_FOR",
    "REVISITED_BECAUSE",
    # Cross-Domain
    "RHYMES_WITH",
    "ANALOGOUS_TO",
    # Learning
    "TAUGHT_THROUGH",
    "BREAKTHROUGH_IN",
    "UNLOCKED",
    # Attribution
    "CREATED_BY",
    "DECIDED_IN",
    "MENTIONED_IN",
    # Project
    "BELONGS_TO_PROJECT",
    "BRIDGES_TO",
    "RELATED_TO",  # Fallback
]

CertaintyLevel = Literal["confirmed", "speculative", "spitballing", "rejected", "revisited"]


# === CHANNEL HEALTH ===


class ChannelStatus(BaseModel):
    """Health status of a single search enrichment channel.

    Attached to search results so callers can distinguish
    'no results' from 'channel failed'.
    """

    channel: str
    status: Literal["ok", "degraded", "skipped"]
    result_count: int = 0
    error: str | None = None


# === MODELS ===


class BaseNode(BaseModel):
    """Base schema for all memory graph nodes."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str
    node_type: NodeLabel
    project_id: str = Field(description="Namespace/Project ID")

    # Temporal
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    occurred_at: datetime | None = Field(
        default=None, description="When the event actually happened"
    )

    # Epistemic
    certainty: CertaintyLevel = "confirmed"
    evidence: list[str] = Field(default_factory=list)

    # Salience
    salience_score: float = Field(default=1.0, description="Retrieval-based salience")
    retrieval_count: int = Field(default=0, description="Total times retrieved via search")

    # Search
    embedding: list[float] | None = None


class EntityCommitReceipt(BaseModel):
    """Receipt returned after committing an entity to the graph."""

    id: str
    name: str
    status: Literal["committed"] = "committed"
    operation_time_ms: float
    total_memory_count: int
    message: str = "Memory committed to graph."
    warnings: list[str] = Field(default_factory=list)


class BreakthroughParams(BaseModel):
    """Parameters for recording a learning breakthrough."""

    name: str
    moment: str
    session_id: str
    analogy_used: str | None = None
    concepts_unlocked: list[str] = Field(default_factory=list)


class EntityCreateParams(BaseModel):
    """Parameters for creating a new entity node."""

    name: str
    node_type: NodeLabel
    project_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    certainty: CertaintyLevel = "confirmed"
    evidence: list[str] = Field(default_factory=list)


class RelationshipCreateParams(BaseModel):
    """Parameters for creating a typed relationship between entities."""

    from_entity: str
    to_entity: str
    relationship_type: EdgeType
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship strength 0-1")


class EntityUpdateParams(BaseModel):
    """Parameters for updating an existing entity's properties."""

    entity_id: str
    properties: dict[str, Any]
    reason: str | None = None


class EntityDeleteParams(BaseModel):
    """Parameters for deleting (or archiving) an entity."""

    entity_id: str
    reason: str
    soft_delete: bool = True


class RelationshipDeleteParams(BaseModel):
    """Parameters for deleting a relationship."""

    relationship_id: str
    reason: str


class ObservationParams(BaseModel):
    """Parameters for adding an observation to an entity."""

    entity_id: str
    content: str
    certainty: CertaintyLevel = "confirmed"
    evidence: list[str] = Field(default_factory=list)


class SessionStartParams(BaseModel):
    """Parameters for starting a new working session."""

    project_id: str
    focus: str


class SessionEndParams(BaseModel):
    """Parameters for ending and summarizing a session."""

    session_id: str
    summary: str
    outcomes: list[str] = Field(default_factory=list)


class TemporalQueryParams(BaseModel):
    """Parameters for querying entities within a time window."""

    start: datetime
    end: datetime
    limit: int = Field(default=20, ge=1, le=100)
    project_id: str | None = None


class SearchResult(BaseModel):
    """A single result from semantic search across the memory graph."""

    id: str
    name: str
    node_type: str
    project_id: str
    content: str | None = None  # For Observations
    score: float
    distance: float
    salience_score: float = Field(default=0.0, description="Entity salience at retrieval time")
    observations: list[str] = Field(default_factory=list, description="E-2: observation texts")
    relationships: list[dict[str, str]] = Field(
        default_factory=list, description="E-2: connected edges"
    )

    # --- Hybrid search enrichment fields (ADR-007) ---
    retrieval_strategy: str = Field(
        default="semantic",
        description="What generated this result: 'semantic', 'hybrid', 'temporal', "
        "'relational', 'associative'",
    )
    recency_score: float = Field(
        default=0.0,
        description="0-1 exponential decay score. 1.0 = just created, 0.5 ≈ half-life old, "
        "0.0 = ancient. Populated for all results when timestamp available.",
    )
    path_distance: int | None = Field(
        default=None,
        description="Graph hops from query anchor. Only populated for relational results.",
    )
    activation_score: float = Field(
        default=0.0,
        description="Spreading activation energy. Only populated for associative results.",
    )
    vector_score: float | None = Field(
        default=None,
        description="Raw cosine similarity from Qdrant. None if entity had no vector match.",
    )


class HybridSearchResponse(BaseModel):
    """Response envelope for hybrid searches with temporal metadata (ADR-007).

    Only returned when the caller opts in via ``include_meta=True``.
    """

    results: list[SearchResult]
    meta: dict[str, Any] = Field(default_factory=dict)


class BottleQueryParams(BaseModel):
    """Parameters for querying 'Message in a Bottle' entities."""

    limit: int = Field(default=10, ge=1, le=100)
    search_text: str | None = None
    before_date: datetime | None = None
    after_date: datetime | None = None
    project_id: str | None = None
    include_content: bool = False


class GapDetectionParams(BaseModel):
    """Parameters for structural gap detection between knowledge clusters."""

    min_similarity: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum centroid similarity threshold"
    )
    max_edges: int = Field(
        default=2, ge=0, description="Maximum cross-cluster edges to qualify as a gap"
    )
    limit: int = Field(default=10, ge=1, le=50, description="Max gaps to return")


class RadarSuggestion(BaseModel):
    """A single relationship suggestion from the Semantic Radar."""

    candidate_id: str = Field(description="ID of the candidate entity")
    candidate_name: str = Field(description="Name of the candidate entity")
    candidate_type: str = Field(description="Node type of the candidate entity")
    cosine_similarity: float = Field(description="Vector similarity score")
    graph_distance: int | None = Field(
        default=None, description="Shortest path length, or None if disconnected"
    )
    radar_score: float = Field(description="Composite discovery score")
    suggested_relationship: str = Field(description="Heuristic EdgeType suggestion")
    reasoning: str = Field(description="Human-readable explanation")


# --- Batch 6.A: Search & Graph Traversal ---


class GetNeighborsParams(BaseModel):
    entity_id: str
    depth: int = 1
    limit: int = 20
    offset: int = 0


class TraversePathParams(BaseModel):
    from_id: str
    to_id: str


class CrossDomainPatternsParams(BaseModel):
    entity_id: str
    limit: int = 10


class GetEvolutionParams(BaseModel):
    entity_id: str


class PointInTimeQueryParams(BaseModel):
    query_text: str
    as_of: str


class AnalyzeGraphParams(BaseModel):
    algorithm: Literal["pagerank", "louvain"] = "pagerank"


class GetHologramParams(BaseModel):
    query: str
    depth: int = 1
    max_tokens: int = 8000


# --- Batch 6.B: Temporal & Maintenance ---


class ArchiveEntityParams(BaseModel):
    entity_id: str


class PruneStaleParams(BaseModel):
    days: int = 30


class GetTemporalNeighborsParams(BaseModel):
    entity_id: str
    direction: Literal["before", "after", "both", "forward", "backward"] = "both"
    limit: int = 10


class DiffKnowledgeStateParams(BaseModel):
    as_of_start: str
    as_of_end: str
    project_id: str | None = None
    include_observations: bool = False


# --- Batch 6.C: Tools Extra & System ---


class SearchMemoryParams(BaseModel):
    query: str
    project_id: str | None = None
    limit: int = 10
    offset: int = 0
    mmr: bool = False
    strategy: str | None = None
    temporal_window_days: int = 7
    include_meta: bool = False
    deep: bool = False


class SearchAssociativeParams(BaseModel):
    query: str
    limit: int = 10
    project_id: str | None = None
    decay: float = 0.6
    max_hops: int = 3
    w_sim: float | None = None
    w_act: float | None = None
    w_sal: float | None = None
    w_rec: float | None = None


class SemanticRadarParams(BaseModel):
    entity_id: str
    limit: int = 10
    similarity_threshold: float = 0.6
    project_id: str | None = None


class FindSemanticOpportunitiesParams(BaseModel):
    project_id: str | None = None
    similarity_threshold: float = 0.6
    limit: int = 20
    min_graph_distance: int = 3


class ListOrphansParams(BaseModel):
    limit: int = 50


class CreateMemoryTypeParams(BaseModel):
    name: str
    description: str
    required_properties: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name_must_be_valid_label(cls, v: str) -> str:
        """Validate that name is a safe Cypher label identifier.

        Must start with an uppercase letter and contain only
        alphanumeric + underscore (max 64 chars).  This prevents
        graph schema corruption from typos or malformed input
        when the name is interpolated into Cypher MERGE queries.
        """
        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,63}", v):
            raise ValueError(
                "Memory type name must start with an uppercase letter and contain "
                f"only alphanumeric + underscore (max 64 chars). Got: {v!r}"
            )
        return v
