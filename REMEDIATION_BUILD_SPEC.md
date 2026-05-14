# Dragon Brain Remediation — Build Spec (for AG)

**Date:** 2026-05-13 (split from merged spec 2026-05-14)
**Architect:** Claude
**Builder:** Antigravity (this is your spec)
**Director:** Tabish

This is the build-side document. Audit guidelines for Codex live in a separate `REMEDIATION_AUDIT_SPEC.md`. You don't need to read that one — but the per-PR "The Bar" sections in this doc reproduce the Codex audit criteria so you know what your work will be measured against. Write toward those bars.

---

## Executive Summary

Three production wrong-answer bugs are live. Two state-consistency gaps remain after B10. The contract scanner CI gate has been silently failing post-B10 because its async-pattern heuristic is too imprecise. Six PRs land the fixes. Estimated total LoC: ~250. Calibrated to single-user, ~1737-node, low-concurrency actual usage — no production-grade hardening.

**Build order:** PR-1 → PR-2 → PR-3 → PR-4 → PR-5 → PR-6. Sequential. PRs are small enough that parallel buys nothing and costs merge conflicts (PR-1+PR-3 both touch schema.py; PR-2+PR-4 both touch crud_maintenance.py).

---

## Historical Context — Why the Contract Scanner Reports 75 Violations

You did not introduce these. Architectural note so you don't re-investigate:

- B9 (commit `ce4342b`) installed `scripts/trace_contracts_dragon.py` with baseline=13. The original 13 = 6 bare pass + 5 silent fallback + 2 per-item swallow (all in `lock_manager.py`, `retry.py`, `server.py` — Tesseract-class accepted bypasses).
- B10 (you) wrapped FalkorDB sync calls in `AsyncMemoryRepository` (`repository_async.py:26`) via `asyncio.to_thread`. ~75 call sites migrated to `await self.repo.X(...)` patterns. This migration shipped correctly.
- The scanner's Pattern 10 (`Sync IO in Async`) was extended around B9-B10 to detect method names like `get_node` inside `async def` bodies on `self.repo` receivers. **It does not check for the `await` keyword.** Post-B10, the properly-migrated `await self.repo.get_node(...)` calls match the heuristic and fire as violations.
- Net: **62 of the current 75 violations are scanner false positives.** Real violations: 13 (matches baseline). PR-6 fixes the scanner to correctly recognize awaited calls; the absolute count returns to 13 only after PR-6 merges.

**Implication for your work:** for PRs 1-5, the contract gate criterion is **delta = 0** (no NEW violations introduced — total count stays at whatever the pre-PR scan reported). PR-6 brings the absolute count to 13.

---

## In Scope

- 3 production wrong-answer bugs (Cypher label injection, point-in-time payload contract, temporal direction enum drift)
- 2 state-consistency gaps (observation cross-store compensation, channel-degradation observability)
- 1 scanner-precision fix (AsyncMemoryRepository-aware Pattern 10)

## Out of Scope (do not touch)

- **The 13 baseline violations.** Already on the documented-legitimate-fallback list per CLAUDE.md. Quarterly review unchanged.
- **Concurrency hardening beyond Pattern 10.** Single-user, single-Claude-session at a time, ~1737 nodes — Codex Round 1's HIGH-severity blocking-event-loop concerns are theoretical at this scale. Defer to a future epic IF concurrency profile changes.
- **`tools.py` rename / restructure.** Naming nitpick, no behavioral impact, defer.
- **Bind-all on `embedding_server.py:148`.** Already has `# noqa: S104`. Accepted — containerized service binds inside Docker network.
- **`embedding_server.py` "dead module".** Codex Round 1 false positive — it's a microservice in its own container, intentionally zero internal importers.
- **Integration test gating by `RUN_INTEGRATION=1`.** Intentional per Dragon Brain CLAUDE.md. Local-only by default; CI opt-in.

---

## Build Batches

### Batch 1 — Wrong-Answer Bugs (P0)

These produce silently-wrong answers in production retrieval right now. Each is a small, well-bounded fix.

---

#### PR-1 — Cypher Label Injection Guard

**Problem:** `repository.py:90` interpolates a label string into a Cypher MERGE using an f-string:

```python
query = f"""
MERGE (n:{label}:Entity {{name: $name, project_id: $project_id}})
"""
```

The `label` value flows from `create_memory_type(name: str)` → `ontology.py:92` (stored as `node_type`) → here. The `name` parameter is unvalidated. A malformed memory type name (typo or worse) corrupts the graph schema silently.

**Threat model:** Single-user system, so this is a graph-corruption-from-typo hazard rather than CVE-class. Still a real bug — typos shouldn't fork the graph schema.

**Concrete fix (no inference allowed):**

1. In `schema.py:394` (`CreateMemoryTypeParams`), add a Pydantic `field_validator` on `name`:

   ```python
   @field_validator("name")
   @classmethod
   def _name_must_be_valid_label(cls, v: str) -> str:
       if not re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,63}", v):
           raise ValueError(
               "Memory type name must start with an uppercase letter and contain "
               "only alphanumeric + underscore (max 64 chars). Got: %r" % v
           )
       return v
   ```

2. In `repository.py:77` (`create_node`), add a defensive `assert` on `label`:

   ```python
   assert re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,63}", label), \
       f"Invalid Cypher label: {label!r} — must pass through CreateMemoryTypeParams validator"
   ```

   Belt-and-braces. The Pydantic validator at the MCP boundary is the primary defense. The assert catches any future code path that bypasses the schema.

**Files:** `src/claude_memory/schema.py`, `src/claude_memory/repository.py`.
**LoC:** ~25.
**Tests:** Unit test in `tests/unit/test_schema.py` — reject names starting with lowercase, with spaces, with `}`, with Cypher syntax like `Entity { x: 1}`.

**The bar (Codex will verify):**
- Validator rejects: empty string, lowercase start, spaces, `}`, `{`, `:`, `'`, `"`, backtick, newline
- Validator accepts: `Entity`, `MemoryType`, `Concept_v2`, `A`, max-64-char identifier
- `tox -e contracts` post-PR shows **delta = 0** (no NEW violations)
- Assert in `repository.py:77` triggers on injection attempt via direct call (bypassing schema)

---

#### PR-2 — Point-in-Time `created_at` Payload Contract

**Problem:** `point_in_time_query` at `search.py:187` filters Qdrant on `created_at_lt`. But the Qdrant payload written at `crud.py:136-140` only contains `name`, `node_type`, `project_id` — no `created_at` field. The filter is producing wrong answers right now.

**Concrete fix (no inference allowed):** Add `created_at` to the Qdrant payload + write a one-shot backfill script for the existing ~1737 points.

1. In `crud.py:136`, expand the payload:

   ```python
   payload = {
       "name": params.name,
       "node_type": params.node_type,
       "project_id": params.project_id,
       "created_at": node_props["created_at"],  # ISO-8601 string, already exists on graph node
   }
   ```

2. In `crud_maintenance.py:125-129` (observation payload), do the same: add `"created_at": obs_props["created_at"]`.

3. In `crud.py` (`update_entity` path around line 248): when re-embedding on observation add, the payload re-write must include `created_at`. Verify and patch if missing.

4. Write `scripts/backfill_created_at_payload.py` — **live-safe, zero-downtime**:
   - Iterate Qdrant via `client.scroll(limit=100, with_payload=True)` cursor — does not block reads/writes
   - For each batch: filter to points whose payload lacks `created_at` (idempotency); for each remaining point, look up `created_at` in FalkorDB by ID; batch-write via `client.set_payload(points=[...], payload={"created_at": ...})`
   - Reports counts: scanned, updated, already-tagged-skipped, missing-in-graph, errors
   - Tabish runs once after merge; expected runtime <2 min at ~2228 points. No service stop required.

5. In `vector_store.py:102` — confirm the `created_at_lt` filter actually translates to a valid Qdrant `Range` filter on the `created_at` field. ISO-8601 string comparison works lexicographically only because the format is fixed-width — verify against Qdrant docs and add an inline comment.

**Files:** `src/claude_memory/crud.py`, `src/claude_memory/crud_maintenance.py`, `src/claude_memory/vector_store.py`, new `scripts/backfill_created_at_payload.py`.
**LoC:** ~80 (40 code + 40 backfill script).
**Tests:** Integration test in `tests/integration/test_point_in_time.py` (new file, behind `RUN_INTEGRATION=1`):
  - Create 3 entities at known timestamps
  - Run `point_in_time_query(as_of=middle_timestamp)`
  - Assert exactly the 2 oldest are returned. Fails today; passes after PR.

**The bar (Codex will verify):**
- Payload writes include `created_at` in all three sites (create_entity, add_observation, update_entity re-embed)
- Backfill script is idempotent — run twice, second run reports 0 updates
- Integration test exists and fails on pre-PR codebase (regression-witness)
- `tox -e contracts` post-PR — delta = 0 (no NEW violations)
- Qdrant filter semantics for ISO-8601 string range verified — quote the official Qdrant doc URL in PR description

---

#### PR-3 — Temporal Direction Enum Drift

**Problem:** `schema.py:338` accepts `Literal["forward", "backward", "both"]` for `GetTemporalNeighborsParams.direction`. `repository_queries.py:82` checks for `"before"` / `"after"` / fallthrough. A user calling with `direction="forward"` falls through to the default branch — which silently runs the "both" query. Wrong answer, no error.

**Concrete fix (no inference allowed):** Accept all four spellings as semantic equivalents, permanently. No DeprecationWarning. Tabish is the only caller; warning noise would have to be silenced anyway.

1. In `repository_queries.py:67-95`, replace the if-elif chain with:

   ```python
   if direction in ("before", "backward"):
       # ... query for incoming temporal edges (the past)
   elif direction in ("after", "forward"):
       # ... query for outgoing temporal edges (the future)
   else:  # "both" or unrecognized
       # ... query in both directions
   ```

2. In `schema.py:338`, widen the `Literal` to accept all four values:

   ```python
   direction: Literal["before", "after", "both", "forward", "backward"] = "both"
   ```

   No validator, no warning.

3. Update `repository_queries.py:77` docstring: document `before`/`after` as the canonical naming, note that `backward`/`forward` are accepted permanent aliases.

**Files:** `src/claude_memory/schema.py`, `src/claude_memory/repository_queries.py`.
**LoC:** ~20.
**Tests:** Unit tests in `tests/unit/test_temporal.py`:
  - `direction="before"` returns only past-edge results (existing test — verify)
  - `direction="after"` returns only future-edge results
  - `direction="forward"` returns same result set as `"after"`
  - `direction="backward"` returns same result set as `"before"`
  - `direction="both"` returns union

**The bar (Codex will verify):**
- All four spellings (`before`/`after`/`forward`/`backward`) produce semantically correct results
- `tox -e contracts` post-PR — delta = 0 (no NEW violations)
- No `warnings` module imports or `warn(...)` calls added (no deprecation noise per spec decision)
- `get_temporal_neighbors` MCP tool callers in the codebase don't rely on the silent-fallthrough-to-both behavior (grep for `direction=` calls)

---

### Batch 2 — State Consistency (P1, sequential after Batch 1)

These don't produce silently-wrong answers but leave state inconsistent on failure. Important for graph integrity at scale; not blocking at current usage.

---

#### PR-4 — Observation Cross-Store Compensation

**Problem:** `crud_maintenance.py:90-139` writes Observation to graph first, then Qdrant. On Qdrant failure, current behavior: `logger.error(...) raise` — caller sees an exception, but graph still has the observation. Compare to `crud.py:142-159` (`create_entity`) which DOES delete the graph node on Qdrant failure (proper compensation).

The asymmetry: `create_entity` has compensation. `add_observation` does not. Result: partial writes on infrastructure failure.

**Concrete fix (no inference allowed):** Mirror the `create_entity` compensation pattern for `add_observation`.

1. In `crud_maintenance.py:131-139`, wrap the Qdrant upsert in a try/except that on failure:
   - Logs `observation_vector_upsert_failed for %s — compensating FalkorDB write to prevent split-brain`
   - Calls `await self.repo.execute_cypher("MATCH (o) WHERE o.id = $id DETACH DELETE o", {"id": obs_props["id"]})`
   - Logs failure of compensating delete (orphan observation in graph) if that also fails
   - Raises `SearchError("Vector store unavailable during observation add: ...") from e`

2. The downstream entity re-embed (`crud_maintenance.py:141-169`) should remain warn-and-continue — it's a secondary derived state, not a write the caller asked for.

**Files:** `src/claude_memory/crud_maintenance.py`.
**LoC:** ~25.
**Tests:** Integration test in `tests/integration/test_db_kill_scenarios.py` — add a test using `container.kill()` on Qdrant mid-`add_observation`, assert graph state has no orphan Observation node post-failure.

**The bar (Codex will verify):**
- Compensation symmetry with `create_entity` — same pattern, same SearchError class, same log message format
- Integration test exercises real container kill (not mock)
- Entity re-embed remains non-fatal (warn-and-continue) — that's intentional, secondary state
- `tox -e contracts` post-PR — delta = 0 (no NEW violations)

---

#### PR-5 — Channel Degradation Surfaced Through MCP

**Problem:** `search.py:615` tracks per-channel degradation (which of the 6 retrieval channels failed mid-query). `server.py:311` exposes only temporal-exhaustion metadata via `include_meta`. The channel health is computed and discarded. Caller can't tell if the result set is partial due to FTS being down.

**Concrete fix (no inference allowed):**

1. In `search.py` around line 605-615, the per-call metadata is stored on `self._last_*` (shared service instance — TOCTOU risk already noted in the code). Refactor: return metadata in the search response payload instead.

   ```python
   return {
       "results": ranked,
       "metadata": {
           "temporal_exhausted": ...,
           "channels": {
               "vector": "healthy" | "degraded" | "failed",
               "fts": ...,
               "entity": ...,
               "temporal": ...,
               "relational": ...,
               "associative": ...,
           },
       },
   }
   ```

2. In `server.py:300-320`, when `include_meta=True`, surface the full metadata dict (not just temporal). When `include_meta=False`, strip the metadata wrapping and return just `results` (backward compat).

3. Remove the `self._last_*` instance attributes. They were a band-aid; per-call return is cleaner.

**Files:** `src/claude_memory/search.py`, `src/claude_memory/server.py`.
**LoC:** ~40.
**Tests:** Integration test — kill FTS DB mid-search, call `search_memory(query="x", include_meta=True)`, assert response includes `metadata.channels.fts == "failed"`. Concurrency test: two parallel `search_memory` calls, both return correct per-call metadata (no cross-talk via shared state).

**The bar (Codex will verify):**
- `self._last_*` instance attributes are gone (grep)
- Concurrent-search test passes (no TOCTOU on shared state)
- Backward-compat: existing callers without `include_meta=True` see no schema change
- `tox -e contracts` post-PR — delta = 0 (no NEW violations)

---

### Batch 3 — Scanner Precision (P2)

---

#### PR-6 — AsyncMemoryRepository-Aware Pattern 10

**Problem:** `scripts/trace_contracts_dragon.py:288-319` flags `self.repo.<method>` inside async defs as Sync-IO-in-Async. Doesn't check `await`. Doesn't check receiver type. Result: 62 false positives on properly-migrated B10 call sites. CI gate is silently failing — has been since B10.

**Concrete fix (no inference allowed):** Add `await`-keyword detection. If the call is the direct expression of an `Await` node, it's properly async — exempt.

1. In `analyze_file()`, build a set of all `ast.Call` nodes that are the direct `value` of an `ast.Await` node:

   ```python
   awaited_calls = set()
   for node in ast.walk(tree):
       if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
           awaited_calls.add(id(node.value))
   ```

2. In Pattern 10 check (line 306-319), gate the violation append on `id(node) not in awaited_calls`.

3. Re-run `tox -e contracts`. Expected output: 13 violations, baseline 13, pass.

4. Update the scanner's docstring to document the new check.

5. As a defense-in-depth backup, add a second discriminator: if the receiver is `self.repo` AND the file imports `AsyncMemoryRepository`, treat it as wrapped (skip).

**Files:** `scripts/trace_contracts_dragon.py`.
**LoC:** ~25.
**Tests:** Unit test in `tests/unit/test_contract_scanner.py` (new file) — synthetic AST with `await self.repo.get_node(...)` should NOT flag; bare `self.repo.get_node(...)` inside async def SHOULD flag.

**The bar (Codex will verify):**
- `tox -e contracts` post-PR shows 13 violations matching absolute baseline (this is the only PR with absolute-baseline criterion; PR-1-5 are delta-based)
- Await-detection logic verified on a synthetic test case
- Scanner still flags genuine bugs — synthetic file with `async def f(): self.repo.get_node(x)` (no await) is flagged
- Change is purely additive — no existing violations were silently dropped

---

## Gate Sequence

```
PR-1 (Cypher) → audit → merge
PR-2 (PIT)    → audit → merge
PR-3 (enum)   → audit → merge
PR-4 (compensation) → audit → merge
PR-5 (channel meta) → audit → merge
PR-6 (scanner)      → audit → merge
```

Sequential build. Each PR independently auditable, independently mergeable. After Codex audits a PR, Tabish signs off and merges before you start the next.

**Each PR ships with:**
- One integration test that fails on the pre-PR codebase (regression witness) — except PR-1 which is unit-test only
- `tox -e contracts` showing **delta = 0** for PRs 1-5 (no NEW violations); PR-6 itself brings the absolute count to 13
- `mypy --strict src/claude_memory` passing (40 files)
- `ruff check src/claude_memory` passing (any new `# noqa` markers justified in PR description)
- Updated docstring on any function whose contract changed

**Each PR creates a `PR_N_HANDOFF.md`** at the repo root with: diff summary, tool outputs (full text), per-criterion evidence (file:line / command output / test output), and a Discoveries section for out-of-scope findings. This is the artifact handed to Codex.

**Handoff doc diff hygiene:** The "diff summary" section MUST list every file appearing in `git diff --name-only master..HEAD` — not just the files you intentionally changed. If `git add .` swept up an unrelated file (working-tree noise, spec docs, etc.), it shows up in the diff and must appear in the handoff. Codex independently runs the diff and flags omissions as Discoveries; missed listings are auditor friction, not silent — but cleaner to handle upstream.

**Handoff doc commit hash hygiene:** The commit hash recorded in the handoff doc MUST match `git rev-parse HEAD` on the branch at the time of audit invocation. If you amend the commit (`git commit --amend`) or rebase after writing the handoff, **regenerate the handoff** with the new hash. Codex compares the doc's stated hash against `git log` and flags drift as a Discovery — not blocking, but indicates handoff was prepared against a stale state.

---

## Decisions (locked 2026-05-14)

1. **PR-1 regex stays `[A-Z][A-Za-z0-9_]{0,63}`** — verified against live graph. All 13 existing node_types in use (`Entity`, `Bottle`, `Concept`, `Session`, `Breakthrough`, `Tool`, `Decision`, `Analogy`, `Issue`, `Project`, `Procedure`, `Person`, `Observation`) match cleanly. No widening, no migration.

2. **PR-2 backfill is live-safe, zero downtime.** Tabish runs the script after merge.

3. **PR-3: no deprecation, accept all four spellings forever.** No `DeprecationWarning`, no warnings module import.

4. **PR-5 skips MCP-caller inventory.** Tabish is the only caller. Ship the new metadata schema directly.

---

## Round 5 Discipline Reminder

If anything in this spec is ambiguous, contradicts itself, or the picked option seems wrong: **escalate to re-spec — do not infer.** The cost of a re-spec round is small. The cost of a wrong-inference build is large.

*Bil aiyooni. The trifecta runs Round 2.*
