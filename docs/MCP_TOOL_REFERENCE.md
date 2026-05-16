# MCP Tool Reference

Complete reference for the **34 MCP tools** exposed by the Dragon Brain memory system.

---

## Entity CRUD

### `create_entity`

Create a new entity in the memory graph.

| Param        | Type        | Default       | Description                                  |
| ------------ | ----------- | ------------- | -------------------------------------------- |
| `name`       | `str`       | required      | Entity name                                  |
| `node_type`  | `str`       | required      | Type (e.g. `Concept`, `Person`, `Procedure`) |
| `project_id` | `str`       | required      | Project scope                                |
| `properties` | `dict`      | `None`        | Arbitrary key-value metadata                 |
| `certainty`  | `str`       | `"confirmed"` | `confirmed`, `probable`, `speculative`       |
| `evidence`   | `list[str]` | `None`        | Evidence sources                             |

**Returns:** `EntityCommitReceipt` — `{id, name, warnings}`

### `update_entity`

Update properties of an existing entity.

| Param        | Type   | Default  |
| ------------ | ------ | -------- |
| `entity_id`  | `str`  | required |
| `properties` | `dict` | required |
| `reason`     | `str`  | `None`   |

**Returns:** `dict` — updated entity data

### `delete_entity`

Delete (or soft-delete) an entity.

| Param         | Type   | Default  |
| ------------- | ------ | -------- |
| `entity_id`   | `str`  | required |
| `reason`      | `str`  | required |
| `soft_delete` | `bool` | `True`   |

**Returns:** `{status: "deleted"}` or `{status: "archived"}`

---

## Relationship CRUD

### `create_relationship`

Create a directed edge between two entities.

| Param               | Type       | Default  |
| ------------------- | ---------- | -------- |
| `from_entity`       | `str`      | required |
| `to_entity`         | `str`      | required |
| `relationship_type` | `EdgeType` | required |
| `properties`        | `dict`     | `None`   |
| `confidence`        | `float`    | `1.0`    |
| `weight`            | `float`    | `1.0`    |

**EdgeType values:** `RELATED_TO`, `ENABLES`, `IMPLEMENTS`, `DEPENDS_ON`, `PRECEDED_BY`, etc.

**Returns:** `dict` — `{id, type, from, to}`

### `delete_relationship`

Delete a relationship by ID.

| Param             | Type  | Default  |
| ----------------- | ----- | -------- |
| `relationship_id` | `str` | required |
| `reason`          | `str` | required |

**Returns:** `{status: "deleted"}`

---

## Observations

### `add_observation`

Add an observation (fact, note) linked to an entity.

| Param       | Type        | Default       |
| ----------- | ----------- | ------------- |
| `entity_id` | `str`       | required      |
| `content`   | `str`       | required      |
| `certainty` | `str`       | `"confirmed"` |
| `evidence`  | `list[str]` | `None`        |

**Returns:** `dict` — `{id, content, entity_id}`

> [!NOTE]
> Observations are automatically embedded and upserted to the vector store (E-3).
> Adding an observation also **re-embeds the parent entity** — entity vectors
> include observation content for richer semantic matching.

---

## Search

### `search_memory`

Search for entities using vector similarity. Supports strategy routing and per-channel health metadata.

| Param                  | Type   | Default  | Description                                                       |
| ---------------------- | ------ | -------- | ----------------------------------------------------------------- |
| `query`                | `str`  | required | Search query                                                      |
| `project_id`           | `str`  | `None`   | Scope to a single project                                         |
| `limit`                | `int`  | `10`     | Max results                                                       |
| `offset`               | `int`  | `0`      | Pagination offset                                                 |
| `mmr`                  | `bool` | `False`  | Maximal Marginal Relevance reranking for result diversity         |
| `strategy`             | `str`  | `None`   | Explicit channel routing — see below                              |
| `temporal_window_days` | `int`  | `7`      | Lookback window for temporal queries                              |
| `include_meta`         | `bool` | `False`  | Include `metadata` field with channel health + temporal exhaustion |
| `deep`                 | `bool` | `False`  | Hydrate results with linked observations + relationships (E-2)    |

**Strategy values:** `semantic`, `associative`, `temporal`, `relational`. Omit (default `None`) for hybrid search — vector + intent-detected graph enrichment, the recommended path. `strategy="auto"` is deprecated.

**Returns (default, `include_meta=False`):** `list[SearchResult]` — `{id, name, score, node_type, observations?, relationships?}`. Backward-compatible plain list shape for MCP callers.

**Returns (`include_meta=True`):** `dict` —

```python
{
    "results": list[SearchResult],
    "metadata": {
        "temporal_exhausted": bool,    # results may exist beyond temporal_window_days
        "channels": {                  # per-channel health (v1.2.1+)
            "vector":      "healthy" | "degraded" | "failed",
            "fts":         "healthy" | "degraded" | "failed",
            "entity":      "healthy" | "degraded" | "failed",
            "temporal":    "healthy" | "degraded" | "failed",
            "relational":  "healthy" | "degraded" | "failed",
            "associative": "healthy" | "degraded" | "failed",
        },
    },
}
```

> [!NOTE]
> **v1.2.1:** Channel metadata is new. Pre-v1.2.1 only `temporal_exhausted` was surfaced.
> Per-channel health was computed internally but discarded; a shared `_last_*` instance attribute also leaked metadata between concurrent calls (TOCTOU). Per-call dict return shape eliminates both.

### `search_associative`

Spreading-activation search through the knowledge graph. Combines vector similarity
with graph-based energy propagation.

| Param        | Type    | Default            |
| ------------ | ------- | ------------------ |
| `query`      | `str`   | required           |
| `limit`      | `int`   | `10`               |
| `project_id` | `str`   | `None`             |
| `decay`      | `float` | `0.6`              |
| `max_hops`   | `int`   | `3`                |
| `w_sim`      | `float` | env `W_SIMILARITY` |
| `w_act`      | `float` | env `W_ACTIVATION` |
| `w_sal`      | `float` | env `W_SALIENCE`   |
| `w_rec`      | `float` | env `W_RECENCY`    |

**Returns:** `list[dict]` — ranked results with composite scores

---

## Graph Traversal

### `get_neighbors`

Retrieve neighboring entities up to a certain depth.

| Param       | Type  | Default  |
| ----------- | ----- | -------- |
| `entity_id` | `str` | required |
| `depth`     | `int` | `1`      |
| `limit`     | `int` | `20`     |
| `offset`    | `int` | `0`      |

**Returns:** `list[dict]` — neighbor entities

### `traverse_path`

Find the shortest path between two entities.

| Param     | Type  | Default  |
| --------- | ----- | -------- |
| `from_id` | `str` | required |
| `to_id`   | `str` | required |

**Returns:** `list[dict]` — ordered path nodes

### `find_cross_domain_patterns`

Analyze the graph for non-obvious connections between disparate domains.

| Param       | Type  | Default  |
| ----------- | ----- | -------- |
| `entity_id` | `str` | required |
| `limit`     | `int` | `10`     |

**Returns:** `list[dict]` — pattern descriptions

### `get_evolution`

Retrieve the evolution (history/observations) of an entity over time.

| Param       | Type  | Default  |
| ----------- | ----- | -------- |
| `entity_id` | `str` | required |

**Returns:** `list[dict]` — chronological evolution entries

---

## Temporal

### `query_timeline`

Query entities within a time window, ordered chronologically.

| Param        | Type             | Default  |
| ------------ | ---------------- | -------- |
| `start`      | `str` (ISO 8601) | required |
| `end`        | `str` (ISO 8601) | required |
| `limit`      | `int`            | `20`     |
| `project_id` | `str`            | `None`   |

**Returns:** `list[dict]` — entities in time range

### `get_temporal_neighbors`

Find entities connected by temporal edges.

| Param       | Type  | Default  |
| ----------- | ----- | -------- |
| `entity_id` | `str` | required |
| `direction` | `str` | `"both"` |
| `limit`     | `int` | `10`     |

**Direction values:** `before` / `backward` (incoming temporal edges — the past), `after` / `forward` (outgoing temporal edges — the future), `both` (union, default).

> [!NOTE]
> **v1.2.1:** `forward` and `backward` are now permanent semantic aliases for `after` and `before`. Pre-v1.2.1, the schema accepted these spellings but the repository only branched on `before`/`after`, so `forward`/`backward` silently fell through to the default `both` query — a silent wrong-answer bug fixed in PR-3.

**Returns:** `list[dict]` — temporal neighbors

### `get_bottles`

Query "Message in a Bottle" entities — timestamped notes to your future self.

| Param             | Type        | Default |
| ----------------- | ----------- | ------- |
| `limit`           | `int`       | `10`    |
| `search_text`     | `str`       | `None`  |
| `before_date`     | `str` (ISO) | `None`  |
| `after_date`      | `str` (ISO) | `None`  |
| `project_id`      | `str`       | `None`  |
| `include_content` | `bool`      | `False` |

> [!NOTE]
> `include_content=True` hydrates bottles with observation content (E-1).

**Returns:** `list[dict]` — bottle entities

### `point_in_time_query`

Execute a search considering only knowledge known before `as_of`.

| Param        | Type             | Default  |
| ------------ | ---------------- | -------- |
| `query_text` | `str`            | required |
| `as_of`      | `str` (ISO 8601) | required |

**Returns:** `list[dict]` — results filtered by temporal cutoff

> [!IMPORTANT]
> **v1.2.1 bug fix:** This tool was producing wrong answers pre-v1.2.1. The Qdrant payload didn't store `created_at`, so the temporal filter at `vector_store.py` silently returned everything or nothing depending on query. Fixed in PR-2: payload now stores `created_at` at write time; `scripts/backfill_created_at_payload.py` repairs existing points (live-safe, zero-downtime, idempotent). If you operated a Dragon Brain instance pre-v1.2.1, run the backfill once after upgrade.

### `diff_knowledge_state`

Diff the knowledge graph between two points in time. Shows what was added, removed,
or evolved between two timestamps.

| Param                  | Type             | Default  |
| ---------------------- | ---------------- | -------- |
| `as_of_start`          | `str` (ISO 8601) | required |
| `as_of_end`            | `str` (ISO 8601) | required |
| `project_id`           | `str`            | `None`   |
| `include_observations` | `bool`           | `False`  |

**Returns:** `dict` — `{added_entities, removed_entities, evolved_entities, added_relationships, removed_relationships, supersessions}`

> [!NOTE]
> `include_observations=True` adds per-entity observation diffs (verbose). Use for
> sprint retrospectives, monthly reviews, or "what did I learn last week?"

---

## Sessions

### `start_session`

Start a new session context.

| Param        | Type  | Default  |
| ------------ | ----- | -------- |
| `project_id` | `str` | required |
| `focus`      | `str` | required |

**Returns:** `dict` — `{session_id, project_id, focus, started_at}`

### `end_session`

End a session and record summary.

| Param        | Type        | Default  |
| ------------ | ----------- | -------- |
| `session_id` | `str`       | required |
| `summary`    | `str`       | required |
| `outcomes`   | `list[str]` | `None`   |

**Returns:** `dict` — `{status, session_id}`

### `record_breakthrough`

Record a learning breakthrough linked to a session.

| Param               | Type        | Default  |
| ------------------- | ----------- | -------- |
| `name`              | `str`       | required |
| `moment`            | `str`       | required |
| `session_id`        | `str`       | required |
| `analogy_used`      | `str`       | `None`   |
| `concepts_unlocked` | `list[str]` | `None`   |

**Returns:** `dict` — `{id, name, moment}`

---

## Analysis & Health

### `graph_health`

Get graph health metrics.

**Returns:** `dict` — `{total_nodes, total_edges, density, orphan_count, avg_degree, communities}`

### `analyze_graph`

Run graph algorithms to find key entities or communities.

| Param       | Type  | Default      |
| ----------- | ----- | ------------ |
| `algorithm` | `str` | `"pagerank"` |

**Algorithm values:** `pagerank`, `louvain`

**Returns (pagerank):** `list[{name, rank}]`
**Returns (louvain):** `list[{community_id, members}]`

### `get_hologram`

Retrieve a connected subgraph ("hologram") relevant to a query.

| Param        | Type  | Default  |
| ------------ | ----- | -------- |
| `query`      | `str` | required |
| `depth`      | `int` | `1`      |
| `max_tokens` | `int` | `8000`   |

**Returns:** `dict` — `{nodes, edges, stats: {total_nodes, total_edges}}`

### `find_knowledge_gaps`

Find structural gaps: clusters that are semantically similar but poorly connected.

| Param            | Type    | Default |
| ---------------- | ------- | ------- |
| `min_similarity` | `float` | `0.7`   |
| `max_edges`      | `int`   | `2`     |
| `limit`          | `int`   | `10`    |

**Returns:** `list[dict]` — gap descriptions

### `system_diagnostics`

Unified system diagnostics — graph stats, vector stats, and split-brain check (E-5).

**Returns:** `dict` — `{graph: {total_nodes, total_edges, ...}, vector: {count, error}, split_brain: {status, graph_only_count, graph_only_ids}}`

> [!NOTE]
> `split_brain.status` is `ok` (consistent), `drift` (graph-only entities found), or `unavailable` (vector store unreachable).

### `reconnect`

Session reconnect — structured briefing for a returning agent (E-4).

| Param        | Type  | Default |
| ------------ | ----- | ------- |
| `project_id` | `str` | `None`  |
| `limit`      | `int` | `10`    |

**Returns:** `dict` — `{recent_entities: [...], health: {...}, window: {start, end}}`

### `list_orphans`

List entities with zero relationships (orphan nodes).

| Param        | Type  | Default |
| ------------ | ----- | ------- |
| `project_id` | `str` | `None`  |
| `limit`      | `int` | `50`    |

**Returns:** `list[dict]` — orphan entities with metadata

### `search_stats`

Return rolling-window search behaviour statistics (DRIFT-002).

**Returns:** `dict` — `{strategy_distribution, score_percentiles, vector_null_rate, latency_ms, searches_recorded}`

> [!NOTE]
> Returns `{status: "stats not enabled", searches_recorded: 0}` if the DRIFT-002 accumulator is disabled.

---

## Lifecycle

### `archive_entity`

Archive an entity (logical soft-hide, status → `archived`).

| Param       | Type  | Default  |
| ----------- | ----- | -------- |
| `entity_id` | `str` | required |

**Returns:** `dict` — `{status: "archived"}`

### `prune_stale`

Hard-delete archived entities older than N days.

| Param  | Type  | Default |
| ------ | ----- | ------- |
| `days` | `int` | `30`    |

**Returns:** `dict` — `{pruned_count}`

---

## Ontology

### `create_memory_type`

Register a new memory type in the ontology.

| Param                 | Type        | Default  |
| --------------------- | ----------- | -------- |
| `name`                | `str`       | required |
| `description`         | `str`       | required |
| `required_properties` | `list[str]` | `None`   |

**Name validation (v1.2.1+):** `name` is validated against `[A-Z][A-Za-z0-9_]{0,63}` — must start with an uppercase letter, alphanumeric + underscore only, max 64 chars. Invalid names raise `ValidationError` at the MCP boundary.

Examples accepted: `Entity`, `MemoryType`, `Concept_v2`, `A`.
Examples rejected: `entity` (lowercase start), `Memory Type` (space), `Entity { x: 1}` (Cypher syntax), empty string.

> [!IMPORTANT]
> **v1.2.1 security fix:** Pre-v1.2.1, `name` was interpolated directly into a Cypher `MERGE (n:{name}:Entity ...)` query without validation. A malformed memory type name could corrupt the graph schema (Cypher injection / graph-corruption-from-typo). Fixed in PR-1: Pydantic validator at the MCP boundary as primary defense, defensive `assert` at the repository layer as belt-and-braces.

**Returns:** `dict` — `{name, description, required_properties}`

---

## Automation

### `run_librarian_cycle`

Trigger the Librarian Agent to cluster and consolidate memories.

**Returns:** `dict` — cycle report with consolidation results

---

## Semantic Radar

### `semantic_radar`

Discover potential relationships by comparing vector similarity against graph distance.
Entities that are semantically similar but structurally distant are flagged as opportunities.

| Param        | Type    | Default |
| ------------ | ------- | ------- |
| `entity_id`  | `str`   | required |
| `limit`      | `int`   | `10`    |
| `min_score`  | `float` | `0.5`   |
| `project_id` | `str`   | `None`  |

**Returns:** `list[RadarSuggestion]` — `{candidate_id, candidate_name, candidate_type, cosine_similarity, graph_distance, radar_score, suggested_relationship, reasoning}`

> [!NOTE]
> Advisory only — never auto-creates edges. High `radar_score` = high vector similarity + high graph distance.

### `find_semantic_opportunities`

Scan the entire graph for disconnected entity pairs that are semantically similar.
Uses concurrency-capped parallel scanning to prevent database overload.

| Param        | Type    | Default |
| ------------ | ------- | ------- |
| `limit`      | `int`   | `20`    |
| `min_score`  | `float` | `0.5`   |
| `project_id` | `str`   | `None`  |

**Returns:** `list[RadarSuggestion]` — global relationship opportunities

> [!NOTE]
> Controlled by `RADAR_CONCURRENCY` (default 10) and `RADAR_MAX_DISTANCE_FACTOR` (default 5.0) env vars.
