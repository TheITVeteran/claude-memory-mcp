"""Canonical Cypher query templates shared by sync and async repository impls.

Per process/issues/B10_5_BUILD_SPEC.md — extracted here so sync MemoryRepository
(diagnostics) and async AsyncMemoryRepository (production) cannot drift apart.
Any new query MUST be added here, not inlined in either implementation.
"""

# ─── Node operations ─────────────────────────────────────────────────

CREATE_NODE = """MERGE (n:{label}:Entity {{name: $name, project_id: $project_id}})
ON CREATE SET n = $props
ON MATCH SET n.updated_at = $updated_at
RETURN n
"""

GET_NODE_BY_ID = "MATCH (n) WHERE n.id = $id RETURN n"

UPDATE_NODE = """MATCH (n:Entity {id: $id})
SET n += $props
RETURN n"""

SOFT_DELETE_NODE = """MATCH (n) WHERE n.id = $id
SET n.deleted = true, n.deletion_reason = $reason
RETURN n"""

HARD_DELETE_NODE = "MATCH (n) WHERE n.id = $id DETACH DELETE n"

CREATE_EDGE = """MATCH (a), (b)
WHERE a.id = $from AND b.id = $to
MERGE (a)-[r:{relation_type}]->(b)
ON CREATE SET r = $props
RETURN r"""

DELETE_EDGE = "MATCH ()-[r]->() WHERE r.id = $id DELETE r"

# ─── Timeline / temporal queries ─────────────────────────────────────

QUERY_TIMELINE = """MATCH (n:Entity)
WHERE COALESCE(n.occurred_at, n.created_at) >= $start
  AND COALESCE(n.occurred_at, n.created_at) <= $end
RETURN n
ORDER BY COALESCE(n.occurred_at, n.created_at) ASC
LIMIT $limit"""

QUERY_TIMELINE_WITH_PROJECT = """MATCH (n:Entity)
WHERE COALESCE(n.occurred_at, n.created_at) >= $start
  AND COALESCE(n.occurred_at, n.created_at) <= $end
  AND n.project_id = $project_id
RETURN n
ORDER BY COALESCE(n.occurred_at, n.created_at) ASC
LIMIT $limit"""

GET_TEMPORAL_NEIGHBORS_BEFORE = """MATCH (n:Entity {id: $entity_id})
<-[r:PRECEDED_BY|EVOLVED_FROM|SUPERSEDES|CONCURRENT_WITH]-(m:Entity)
RETURN m
ORDER BY COALESCE(m.occurred_at, m.created_at) DESC
LIMIT $limit"""

GET_TEMPORAL_NEIGHBORS_AFTER = """MATCH (n:Entity {id: $entity_id})
-[r:PRECEDED_BY|EVOLVED_FROM|SUPERSEDES|CONCURRENT_WITH]->(m:Entity)
RETURN m
ORDER BY COALESCE(m.occurred_at, m.created_at) ASC
LIMIT $limit"""

GET_TEMPORAL_NEIGHBORS_BOTH = """MATCH (n:Entity {id: $entity_id})
-[r:PRECEDED_BY|EVOLVED_FROM|SUPERSEDES|CONCURRENT_WITH]-(m:Entity)
RETURN DISTINCT m
ORDER BY COALESCE(m.occurred_at, m.created_at) ASC
LIMIT $limit"""

CREATE_TEMPORAL_EDGE = """MATCH (a:Entity {{id: $from_id}}), (b:Entity {{id: $to_id}})
CREATE (a)-[r:{edge_type}]->(b)
SET r = $props
RETURN type(r) AS rel_type, a.id AS from_id, b.id AS to_id"""

# ─── Bottles (message-in-a-bottle entities) ──────────────────────────

GET_BOTTLES_TEMPLATE = """MATCH (n:Entity)
{where_clause}
RETURN n
ORDER BY COALESCE(n.occurred_at, n.created_at) DESC
LIMIT $limit"""

# ─── Graph health & edges ────────────────────────────────────────────

COUNT_ALL_NODES = "MATCH (n) RETURN count(n)"

COUNT_ENTITY_NODES = "MATCH (n:Entity) RETURN count(n)"

COUNT_OBSERVATION_NODES = "MATCH (n:Observation) RETURN count(n)"

COUNT_ALL_EDGES = "MATCH ()-[r]->() RETURN count(r)"

COUNT_ORPHAN_NODES = "MATCH (n) WHERE NOT (n)--() RETURN count(n)"

LIST_ORPHANS = """MATCH (n)
WHERE NOT (n)--()
RETURN n.id AS id,
       n.name AS name,
       n.node_type AS node_type,
       n.project_id AS project_id,
       n.focus AS focus,
       labels(n) AS labels,
       n.created_at AS created_at
ORDER BY n.created_at DESC
LIMIT $limit"""

GET_ALL_EDGES = "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id, b.id, type(r)"

GET_ALL_NODE_IDS = "MATCH (n:Entity) RETURN n.id LIMIT $limit"

GET_OBSERVATIONS_FOR_ENTITY = """MATCH (e)-[:HAS_OBSERVATION]->(o:Observation)
WHERE e.id = $entity_id
RETURN o
ORDER BY o.created_at DESC
LIMIT $limit"""

# ─── Subgraph / Traversal / Salience ─────────────────────────────────

GET_SUBGRAPH_DEPTH_ZERO = """MATCH (n:Entity) WHERE n.id IN $ids
RETURN collect(distinct {
    id: n.id,
    labels: labels(n),
    properties: properties(n)
}) as nodes"""

GET_SUBGRAPH_TEMPLATE = """MATCH path = (root:Entity)-[*0..{depth}]-(neighbor)
WHERE root.id IN $ids
UNWIND relationships(path) as r
WITH distinct r, startNode(r) as s, endNode(r) as e
RETURN collect(distinct {{
    id: r.id,
    source: s.id,
    target: e.id,
    type: type(r),
    properties: properties(r)
}}) as edges,
collect(distinct {{
    id: s.id,
    labels: labels(s),
    properties: properties(s)
}}) + collect(distinct {{
    id: e.id,
    labels: labels(e),
    properties: properties(e)
}}) as nodes"""

GET_ALL_NODES = """MATCH (n:Entity)
RETURN n
LIMIT $limit"""

INCREMENT_SALIENCE = """MATCH (n:Entity)
WHERE n.id IN $ids
SET n.retrieval_count = COALESCE(n.retrieval_count, 0) + 1,
    n.salience_score = 1.0 + log(1 + COALESCE(n.retrieval_count, 0) + 1) / log(2)
RETURN n.id AS id, n.salience_score AS salience_score, n.retrieval_count AS retrieval_count"""

GET_MOST_RECENT_ENTITY = """MATCH (n:Entity {project_id: $pid})
RETURN n
ORDER BY COALESCE(n.occurred_at, n.created_at) DESC
LIMIT 1"""

SHORTEST_PATH_FORWARD = """MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})
WITH shortestPath((a)-[*..10]->(b)) AS p
RETURN length(p)"""

SHORTEST_PATH_REVERSE = """MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})
WITH shortestPath((b)-[*..10]->(a)) AS p
RETURN length(p)"""
