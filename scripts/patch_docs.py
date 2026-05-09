file_path = "docs/CODE_INVENTORY.md"

with open(file_path, encoding="utf-8") as f:
    text = f.read()

text = text.replace("Last updated: April 10, 2026.", "Last updated: May 9, 2026.")

# Insert repository_async and fts_store
text = text.replace(
    "| `repository.py`           | **Data Access Layer**. FalkorDB connections, Cypher queries, Graph Algorithms, Temporal queries.                          |",
    "| `repository.py`           | **Data Access Layer**. FalkorDB connections, Cypher queries, Graph Algorithms, Temporal queries.                          |\n| `repository_async.py`     | **Async Data Access Layer**. Asynchronous thread-pool wrapper over the synchronous FalkorDB GraphRepository.              |\n| `fts_store.py`            | **Full Text Search Layer**. SQLite-based FTS5 index for lexical search backup.                                            |",
)

# Insert search_channels, search_radar, entity_extraction, date_parser
text = text.replace(
    "| `search.py`               | **SearchMixin**. Vector search, hologram retrieval, hybrid pipeline (ADR-007), salience updates.                          |\n| `search_advanced.py`",
    "| `search.py`               | **SearchMixin**. Vector search, hologram retrieval, hybrid pipeline (ADR-007), salience updates.                          |\n| `search_channels.py`      | **Retrieval Channels**. Definitions for the 6 parallel retrieval channels (Semantic, Lexical, Temporal, Associative, Entity, Relational). |\n| `search_radar.py`         | **Semantic Radar**. Vector-graph gap analysis logic separated from advanced search.                                       |\n| `search_advanced.py`",
)

text = text.replace(
    "| `clustering.py`           | **ML Layer**. `scikit-learn` DBSCAN clustering + structural gap detection (`detect_gaps`).                                |\n| `activation.py`",
    "| `clustering.py`           | **ML Layer**. `scikit-learn` DBSCAN clustering + structural gap detection (`detect_gaps`).                                |\n| `activation.py`           | **ML Layer**. `ActivationEngine` — spreading activation through graph edges for associative retrieval.                    |\n| `date_parser.py`          | **NLP Layer**. Temporal parsing logic for converting relative dates into absolute timestamps.                             |\n| `entity_extraction.py`    | **NLP Layer**. Lightweight entity extraction via spaCy for query processing.                                              |",
)

# Update the tests section
text = text.replace("### E2E / UAT (`tests/`)", "### E2E / UAT / Integration (`tests/`)")

text = text.replace(
    "| `e2e_functional.py` | **Exhaustive UAT**.",
    "| `integration/test_db_kill_scenarios.py` | **Behavioral Contracts**. Spin up FalkorDB/Qdrant in `testcontainers`, kill them mid-flight, verify fail-loud propagation and cross-store rollback consistency (Split-Brain resilience). |\n| `e2e_functional.py` | **Exhaustive UAT**.",
)

text = text.replace(
    "**Total: 1,166 tests (1,027 unit + 139 gauntlet) across 76 files, ~98% coverage.**",
    "**Total: 1,337 tests (106 files), ~98% coverage.**",
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("docs/CODE_INVENTORY.md updated successfully")
