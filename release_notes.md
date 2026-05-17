## Dragon Brain v1.2.1 — Round 2 Audit Remediation

This release closes the second adversarial audit arc, formalizing **ChatGPT Codex 5.5 as the Auditor seat** in the AI Council trifecta workflow (Architect / Builder / Auditor / Director). Codex independently caught three production bugs that 10 batches of the previous trifecta had missed — a Cypher label injection vector, a silently-broken `point_in_time_query`, and a temporal direction enum drift — all fixed in this release.

### What's new for users

- **`search_memory(include_meta=True)`** now exposes per-channel health metadata (`metadata.channels`) for all 6 retrieval channels (`vector`, `fts`, `entity`, `temporal`, `relational`, `associative`). Tells you when a result set is partial due to infrastructure degradation rather than genuine emptiness.
- **`get_temporal_neighbors`** now accepts `forward`/`backward` as permanent aliases for `after`/`before` — both naming conventions first-class.
- **`create_memory_type`** validates `name` against a strict regex; invalid names raise `ValidationError` at the MCP boundary.
- **`point_in_time_query`** actually works now (was silently producing wrong answers pre-v1.2.1). If you've been running Dragon Brain, run `scripts/backfill_created_at_payload.py` once after upgrade to repair existing Qdrant points (live-safe, zero-downtime, <2 min on ~2228 points).

### Backward compatibility

MCP boundary preserved — callers using `search_memory` with the default `include_meta=False` continue to receive a plain list. Only direct `MemoryService.search()` callers see the new dict shape. No breaking changes for MCP consumers.

### Full detail

- [CHANGELOG.md § 1.2.1](CHANGELOG.md#121---2026-05-17) — per-PR breakdown
- [README.md § Forged in Audit § Round 2](README.md#round-2-may-2026-v121--the-adversarial-auditor) — narrative
- [`process/`](process/) — public worked-example artifacts (build spec, audit spec, per-PR handoff docs)

---

## Dragon Brain V2 — Initial Public Release

Persistent memory for AI agents. A hybrid knowledge graph (FalkorDB) + vector search
(Qdrant) MCP server that gives any MCP-compatible AI long-term memory across conversations.
Works with Claude, Gemini CLI, Cursor, Windsurf, Cline, and more.

### Highlights
- 31 MCP tools for memory management
- Hybrid semantic + graph search with Reciprocal Rank Fusion
- Autonomous clustering agent ("The Librarian")
- Time travel queries — explore your memory graph at any point in history
- CUDA GPU support for embedding acceleration
- 1,116 tests, mutation testing, property-based testing, fuzz testing
- Dragon Brain Gauntlet: A- (95/100)

### Quick Start
```bash
docker-compose up -d
```

See [README](https://github.com/iikarus/claude-memory-mcp#quick-start) for full setup.
