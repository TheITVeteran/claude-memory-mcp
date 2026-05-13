# Dragon Brain Remediation Spec — Round 2

**Date:** 2026-05-13
**Architect:** Claude (Architect seat, AI Council)
**Builder:** Antigravity (AG)
**Auditor:** ChatGPT Codex 5.5 (Round 2 sceptical adversarial seat)
**Director:** Tabish

**Triggered by:** Codex Round 1 audit of Dragon Brain (v1.2.0). Claude re-audited Codex's audit, verified findings, ran the deterministic AST contract scanner Codex skipped. This spec is the result.

---

## Executive Summary

Three production wrong-answer bugs are live in Dragon Brain right now. Two state-consistency gaps remain after B10. The contract scanner CI gate has been silently failing post-B10 because its async-pattern heuristic is too imprecise. Six PRs land the fixes, each separately gated by Codex. Estimated total LoC: ~250 across all PRs. Calibrated to single-user, ~1737-node, low-concurrency actual usage — no production-grade hardening.

**Gate sequence:** PR-1 → PR-2 → PR-3 (independent, parallelizable wrong-answer fixes) → PR-4 → PR-5 (state consistency) → PR-6 (scanner precision). Each PR is independently mergeable.

---

## Historical Record — "Did the 62 violations resurface?"

**They didn't.** Architectural note for future-Claude / future-Tabish so this isn't re-investigated:

- B9 (commit `ce4342b`) installed `scripts/trace_contracts_dragon.py` with baseline=13. The original 13 = 6 bare pass + 5 silent fallback + 2 per-item swallow (all in `lock_manager.py`, `retry.py`, `server.py` — Tesseract-class accepted bypasses).
- B10 wrapped FalkorDB sync calls in `AsyncMemoryRepository` (`repository_async.py:26`) via `asyncio.to_thread`. ~75 call sites migrated to `await self.repo.X(...)` patterns. This migration shipped correctly.
- The contract scanner's Pattern 10 (`Sync IO in Async`) detects method names like `get_node`, `execute_cypher` inside `async def` bodies on `self.repo` receivers. **It does not check for the `await` keyword and does not introspect the receiver type.** Post-B10, the properly-migrated `await self.repo.get_node(...)` calls match the heuristic and fire as violations.
- Net: **62 of the current 75 violations are scanner false positives.** Wrapper completeness verified — every method in the scanner's `sync_io_methods` set has a real `asyncio.to_thread` wrapper in `AsyncMemoryRepository`. Real violations: 13. Baseline: 13. Match.

PR-6 fixes the scanner. The remediation order puts user-facing wrong-answer bugs first, scanner second.

---

## What's In Scope

- 3 production wrong-answer bugs (Cypher label injection, point-in-time payload contract, temporal direction enum drift)
- 2 state-consistency gaps (observation cross-store compensation, channel-degradation observability)
- 1 scanner-precision fix (AsyncMemoryRepository-aware Pattern 10)

## What's Explicitly NOT In Scope

- **The 13 baseline violations.** Already on the documented-legitimate-fallback list per CLAUDE.md. Quarterly review unchanged.
- **Concurrency hardening for the async/sync findings beyond Pattern 10.** Single-user, single-Claude-session at a time, ~1737 nodes — Codex's HIGH-severity blocking-event-loop concerns are theoretical at this scale (per calibrate-prescriptions-to-actual-usage feedback). Defer to a future epic IF concurrency profile changes.
- **`tools.py` rename / restructure.** Codex's #20 finding. Naming nitpick, no behavioral impact, defer.
- **Bind-all on `embedding_server.py:148`.** Already has `# noqa: S104`. Accepted — containerized service binds inside Docker network.
- **`embedding_server.py` "dead module".** Codex false positive — it's a microservice in its own container, intentionally zero internal importers.
- **Integration test gating by `RUN_INTEGRATION=1`.** Intentional per Dragon Brain CLAUDE.md. Local-only by default; CI opt-in. Codex's HIGH framing rejected.

---

## Build Batches

### Batch 1 — Wrong-Answer Bugs (parallelizable, P0)

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

   This is belt-and-braces; the Pydantic validator at the MCP boundary is the primary defense. The assert catches any future code path that bypasses the schema.

**Files:** `src/claude_memory/schema.py`, `src/claude_memory/repository.py`.
**LoC:** ~25.
**Tests:** Unit test in `tests/unit/test_schema.py` — reject names starting with lowercase, with spaces, with `}`, with Cypher syntax like `Entity { x: 1}`. Integration test in `tests/integration/` — create_memory_type with invalid name returns 400-equivalent MCP error, not silent graph corruption.

**Codex Round 2 audit criteria (pre-defined):**
- (a) Confirm validator rejects: empty string, lowercase start, spaces, `}`, `{`, `:`, `'`, `"`, backtick, newline.
- (b) Confirm validator accepts: `Entity`, `MemoryType`, `Concept_v2`, `A`, max-64-char identifier.
- (c) Run `tox -e contracts` post-PR — baseline must remain 13.
- (d) Verify the assert in `repository.py:77` triggers on injection attempt via direct call (bypassing schema).

---

#### PR-2 — Point-in-Time `created_at` Payload Contract

**Problem:** `point_in_time_query` at `search.py:187` filters Qdrant on `created_at_lt`. But the Qdrant payload written at `crud.py:136-140` only contains `name`, `node_type`, `project_id` — no `created_at` field. Either the filter silently returns everything (Qdrant ignores missing fields depending on operator semantics) or returns empty. Either way: **`point_in_time_query` is producing wrong answers right now.**

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
   - Iterate Qdrant via `client.scroll(limit=100, with_payload=True)` cursor — does not block reads/writes.
   - For each batch: filter to points whose payload lacks `created_at` (idempotency); for each remaining point, look up `created_at` in FalkorDB by ID; batch-write via `client.set_payload(points=[...], payload={"created_at": ...})`.
   - Reports counts: scanned, updated, already-tagged-skipped, missing-in-graph, errors.
   - Tabish runs once after merge; expected runtime <2 min at ~2228 points. No service stop required.

5. In `vector_store.py:102` — confirm the `created_at_lt` filter actually translates to a valid Qdrant `Range` filter on the `created_at` field. ISO-8601 string comparison works lexicographically only because the format is fixed-width — verify against Qdrant docs and add an inline comment.

**Files:** `src/claude_memory/crud.py`, `src/claude_memory/crud_maintenance.py`, `src/claude_memory/vector_store.py`, new `scripts/backfill_created_at_payload.py`.
**LoC:** ~80 (40 code + 40 backfill script).
**Tests:** Integration test in `tests/integration/test_point_in_time.py` (new file, behind `RUN_INTEGRATION=1`):
  - Create 3 entities at known timestamps (mock or `time.sleep(0.1)` between creates).
  - Run `point_in_time_query(as_of=middle_timestamp)`.
  - Assert exactly the 2 oldest are returned. Fails today; passes after PR.

**Codex Round 2 audit criteria (pre-defined):**
- (a) Confirm payload writes include `created_at` in all three sites (create_entity, add_observation, update_entity re-embed).
- (b) Confirm backfill script is idempotent — run twice, second run reports 0 updates.
- (c) Confirm integration test exists and fails on pre-PR codebase (regression-witness).
- (d) Run `tox -e contracts` — baseline 13.
- (e) Verify Qdrant filter semantics for ISO-8601 string range — quote the official Qdrant doc URL in PR description.

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

3. Update `repository_queries.py:77` docstring: document `before`/`after` as the canonical naming, note that `backward`/`forward` are accepted permanent aliases for `before`/`after` respectively.

**Files:** `src/claude_memory/schema.py`, `src/claude_memory/repository_queries.py`.
**LoC:** ~20.
**Tests:** Unit tests in `tests/unit/test_temporal.py`:
  - `direction="before"` returns only past-edge results (existing test — verify).
  - `direction="after"` returns only future-edge results.
  - `direction="forward"` returns same result set as `"after"`.
  - `direction="backward"` returns same result set as `"before"`.
  - `direction="both"` returns union.

**Codex Round 2 audit criteria (pre-defined):**
- (a) Confirm all four spellings (`before`/`after`/`forward`/`backward`) produce semantically correct results.
- (b) Confirm `tox -e contracts` baseline 13.
- (c) Confirm no warnings module imports or `warn(...)` calls added (no deprecation noise per spec decision).
- (d) Cross-check `get_temporal_neighbors` MCP tool callers in the codebase — none rely on the silent-fallthrough-to-both behavior (grep for `direction=` calls).

---

### Batch 2 — State Consistency (sequential after Batch 1, P1)

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

**Codex Round 2 audit criteria (pre-defined):**
- (a) Confirm compensation symmetry with `create_entity` — same pattern, same SearchError class, same log message format.
- (b) Confirm integration test exercises real container kill (not mock).
- (c) Verify entity re-embed remains non-fatal (warn-and-continue) — that's intentional, secondary state.

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

**Codex Round 2 audit criteria (pre-defined):**
- (a) Confirm `self._last_*` instance attributes are gone (grep).
- (b) Confirm concurrent-search test passes (no TOCTOU on shared state).
- (c) Verify backward-compat: existing callers without `include_meta=True` see no schema change.
- (d) Run `tox -e contracts` baseline 13.

---

### Batch 3 — Scanner Precision (independent, P2)

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

**Codex Round 2 audit criteria (pre-defined):**
- (a) Run `tox -e contracts` post-PR — must show 13 violations matching baseline.
- (b) Verify the await-detection logic on a synthetic test case.
- (c) Confirm the scanner still flags genuine bugs — write a synthetic file with `async def f(): self.repo.get_node(x)` (no await) and verify it's flagged.
- (d) Confirm the change is purely additive — no existing violations were silently dropped.

---

## Gate Sequence

```
PR-1 (Cypher) ──┐
PR-2 (PIT)    ──┼──► Codex R2 audit ──► Tabish sign-off ──► merge ──► PR-4 → PR-5 → PR-6
PR-3 (enum)   ──┘
```

Batch 1 PRs are independent. Codex audits all three at once. Batch 2 sequential (PR-4 then PR-5 — PR-5 may touch search.py overlapping PR-4's compensation logic). PR-6 last because it depends on the post-fix violation count being exactly 13.

**Each PR ships with:**
- One integration test that fails on the pre-PR codebase (regression witness)
- `tox -e contracts` passing at baseline 13
- `mypy --strict src/claude_memory` passing (40 files)
- `ruff check src/claude_memory` passing (any new `# noqa` markers justified in PR description)
- Updated docstring on any function whose contract changed

---

## Audit Guidelines for Codex Round 2 (Architect-Defined, Pre-Build)

**Audit trigger (when Codex fires):** Codex Round 2 fires **per-PR**, only after AG creates a `PR_N_HANDOFF.md` at the repo root AND pushes the corresponding `remediation/pr-N-*` branch. Director invokes Codex with: (a) the branch ref, (b) the handoff doc, (c) the relevant spec section. Codex does NOT fire on Director schedule against arbitrary repo state — auditing an empty diff produces an "empty audit fail" that wastes a cycle. If no handoff doc exists for the PR being audited, the audit is invalid; reschedule.

**Audit protocol (what Codex does once triggered):**
Codex Round 1 missed running the deterministic AST scanner. Round 2 audit MUST follow this protocol, in order, before any LLM reasoning:

1. **Run `tox -e contracts`** and paste full output. Confirm baseline 13.
2. **Run `python -m mypy --strict src/claude_memory`** and paste output. Confirm 40 files, no errors.
3. **Run `python -m bandit -r src/claude_memory -ll`** and paste output. Confirm only the bind-all at `embedding_server.py:148` (already noqa'd).
4. **Run `python -m ruff check src/claude_memory`** and paste output. Confirm no new ruff errors (existing invalid-noqa warnings tolerated for now).
5. **Run `tox -e integration` (with `RUN_INTEGRATION=1`)** for the relevant integration test file(s) per PR. Paste output.
6. **For each per-PR audit criterion (a)/(b)/(c)/...**, paste evidence (file:line, command output, or test output) demonstrating the criterion is met. No "looks fine" — evidence or fail.
7. **Cross-check against this spec** — every PR must satisfy every criterion in its section above. Missing any = audit fail = back to AG.
8. **For each finding Codex identifies as new bugs outside this spec's scope** — flag in a separate "Discoveries" section. These don't block the current round but feed the next remediation cycle.

**Codex must NOT:**
- Skip the deterministic tool runs (Round 1's gap)
- Rely on its own static analysis where a deterministic tool exists
- Audit aspects outside this spec's scope as if they were build requirements (scope creep)
- Defer to AG's own reports for evidence (Builder cannot self-attest)

---

## What Comes After This Round

If all 6 PRs land cleanly: Dragon Brain reaches Phase 14-19 hardening parity AND the trifecta workflow has been exercised end-to-end (Architect spec → Builder implementation → Auditor verification → Director approval). At that point, formalize the Codex seat per the AI Council formalization criterion: "must independently catch gaps Claude/AG missed before being formalized into the workflow."

The Cypher injection (PR-1) and point-in-time payload drift (PR-2) are the specific gaps Codex caught that 10 batches of B10 missed. If those land + audit cleanly, the pilot succeeded.

---

## Decisions (locked 2026-05-14, least-friction / max-ROI)

1. **PR-1 regex stays `[A-Z][A-Za-z0-9_]{0,63}`** — verified against live graph. All 13 existing node_types in use (`Entity`, `Bottle`, `Concept`, `Session`, `Breakthrough`, `Tool`, `Decision`, `Analogy`, `Issue`, `Project`, `Procedure`, `Person`, `Observation`) match cleanly. No widening, no migration.

2. **PR-2 backfill is live-safe, zero downtime.** Write the script to iterate via `client.scroll(scroll_filter=None, limit=100)`, batch `set_payload` updates of 100 points per call. ~2228 points / 100 = ~23 batches. Estimated total runtime <2 min. No service stop required. Idempotency check: skip points where payload already contains `created_at`.

3. **PR-3: no deprecation, accept all four spellings forever.** Tabish is the only caller. DeprecationWarning is noise he'd have to silence. Widen `repository_queries.py:67-95` to treat `before`=`backward` and `after`=`forward` as semantic equivalents. Schema `Literal[...]` keeps all four values. Docstring documents `before`/`after` as canonical naming; both accepted permanently. No sunset, no churn cycle.

4. **PR-5 skips MCP-caller inventory.** Tabish is the only caller. Ship the new metadata schema, no inventory step.

---

*Bil aiyooni. The trifecta runs Round 2.*
