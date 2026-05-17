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

**Concrete fix (no inference allowed) — option A architecture: service always returns dict, MCP transforms for backward compat:**

1. In `search.py:615-650` (the search method of `MemoryService`): **always** return the dict shape. No conditional; service layer is the source of truth for channel metadata.

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

2. **Remove `self._last_*` instance attributes entirely** (including any commented-out references). Per-call return is the new contract; shared instance state is the bug.

3. In `server.py:300-320` (`server.search_memory` MCP tool wrapper): when `include_meta=True`, return the full dict. When `include_meta=False`, return just `result["results"]` as a plain list (backward compat at MCP boundary only — service layer no longer offers list-shape).

4. **Update all internal callers of `MemoryService.search()`** to access `result["results"]` instead of `result` directly. Run `rg "memory_service\.search\(|service\.search\(" --type py` to enumerate. Known caller sites (not exhaustive — verify with rg):
   - `tests/integration/test_db_kill_scenarios.py` (e.g., `test_kill_falkordb_mid_search_degrades_gracefully`)
   - `tests/e2e_functional.py`
   - `tests/unit/test_hybrid_search.py` (line 272 area — also remove `_last_temporal_exhausted` accesses)
   - `tests/unit/test_memory_service.py`
   - `tests/unit/test_router.py`
   - `tests/unit/test_server.py`
   - `tests/unit/test_channel_degradation.py` (any references already there)

5. Fix the mypy `[no-any-return]` errors at `router.py:199` and `router.py:243` introduced in the previous PR-5 attempt. Add explicit type annotation or cast. **Run `python -m mypy --strict src/claude_memory` and confirm 40 files, 0 errors before declaring done.**

6. **Remove the "No results found." string shortcut at `server.py:310`.** Currently `server.search_memory()` returns the string when results are empty, BEFORE checking `include_meta`. This hides metadata when degradation produces empty results — the exact failure mode this PR is supposed to surface. Replace with: always return the full result (list or dict per `include_meta`), even when empty. Callers handle empty-list display formatting themselves; the MCP layer doesn't synthesize messages. Verify by running `test_kill_embedding_mid_search` — it should propagate the infrastructure error correctly post-fix.

**Files:** `src/claude_memory/search.py`, `src/claude_memory/server.py`, `src/claude_memory/router.py`, multiple test files (per step 4 inventory).
**LoC:** ~60 production + ~30 test updates.

**Tests (3 evil + 1 sad + 1 neutral, test-first):**

| Test | Category | Scenario | Pre-PR | Post-PR |
|------|----------|----------|--------|---------|
| test_evil_kill_fts_mid_search | evil | testcontainers `container.kill()` on FTS DB mid-`search_memory` (via MCP, `include_meta=True`) | TEST FAILS (no metadata field in response; KeyError on `.channels.fts`) | TEST PASSES (response contains `metadata.channels.fts == "failed"`, partial results from other channels) |
| test_evil_kill_qdrant_mid_search | evil | testcontainers `container.kill()` on Qdrant mid-`search_memory` (via MCP, `include_meta=True`) | TEST FAILS (same — no metadata) | TEST PASSES (`metadata.channels.vector == "failed"`) |
| test_evil_concurrent_search_no_crosstalk | evil | Two parallel `MemoryService.search()` calls — one with FTS killed mid-flight, one with all healthy | TEST FAILS (shared `self._last_*` causes the healthy call to inherit the failed call's degradation metadata, or vice versa) | TEST PASSES (each call returns its own correct per-call metadata in its dict response, no shared-state crosstalk) |
| test_sad_include_meta_false_strips_metadata | sad | MCP `search_memory(query="x", include_meta=False)` against healthy infra | TEST PASSES (current MCP behavior already returns plain list — regression-prevention) | TEST PASSES (must remain plain list at MCP layer) |
| test_neutral_service_returns_dict_shape | neutral | `MemoryService.search(query="x")` direct call with all infra healthy | TEST FAILS (current returns plain list, no `metadata` field) | TEST PASSES (returns `{'results': [...], 'metadata': {'channels': {...all 6 healthy...}}}`) |

**The bar (Codex will verify):**
- All `self._last_*` instance attributes gone, including comments (`rg "self\._last_" src/claude_memory/` returns zero matches)
- All five tests have the documented pre-PR and post-PR behavior
- For tests marked "TEST FAILS" pre-PR (3 of 5: evil_kill_fts, evil_kill_qdrant, evil_concurrent, neutral_service_dict), handoff doc includes verbatim first-run failure output captured against pre-PR base
- `MemoryService.search()` always returns dict shape; MCP `server.search_memory()` strips to list when `include_meta=False`; all internal callers updated
- No mypy `[no-any-return]` errors in `router.py` (confirms the regression is fixed)
- `tox -e contracts` post-PR — delta = 0 (no NEW violations; if a new `await self.repo.X()` site is introduced, suppress with the documented `# noqa: contract` marker)

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

**Tests (3 evil + 1 sad + 1 neutral, test-first):**

Create `tests/unit/test_contract_scanner.py` (new file). Use synthetic-AST fixtures or temp .py files for each case.

| Test | Category | Scenario | Pre-PR | Post-PR |
|------|----------|----------|--------|---------|
| test_evil_awaited_self_repo_call_NOT_flagged | evil | Synthetic async function with `await self.repo.get_node(x)` | TEST FAILS (scanner flags it as Sync IO in Async — false positive) | TEST PASSES (scanner correctly skips awaited calls) |
| test_evil_unawaited_self_repo_call_IS_flagged | evil | Synthetic async function with bare `self.repo.get_node(x)` (no await) | TEST PASSES (scanner correctly flags it today — regression-prevention) | TEST PASSES (must remain flagged) |
| test_evil_sync_io_outside_async_def_NOT_flagged | evil | Synthetic regular `def` (not async) calling `self.repo.get_node(x)` | TEST PASSES (scanner correctly only fires inside async def — regression-prevention) | TEST PASSES (must remain not-flagged) |
| test_sad_malformed_python_file_handled | sad | Synthetic file with syntax error fed to scanner | TEST PASSES if scanner handles cleanly today; TEST FAILS if it crashes — verify which | Either way, post-PR must not crash; must report parse failure and exit cleanly |
| test_neutral_baseline_against_real_repo | neutral | Run scanner against current `src/claude_memory` directory | TEST FAILS (returns 75 violations) | TEST PASSES (returns exactly 13 violations matching absolute baseline) |

**The bar (Codex will verify):**
- `tox -e contracts` post-PR shows 13 violations matching absolute baseline (this is the only PR with absolute-baseline criterion; PR-1-5 are delta-based)
- All five tests have the documented pre-PR and post-PR behavior
- For tests marked "TEST FAILS" pre-PR (at least 2 of 5: `test_evil_awaited_NOT_flagged`, `test_neutral_baseline_against_real_repo`; possibly also `test_sad_malformed_python_file_handled` depending on current scanner robustness), handoff includes verbatim first-run failure output captured against pre-PR base
- Change is purely additive — no existing violations from the original 13 baseline categories (Bare Pass, Silent Fallback, Per-Item Swallow) were silently dropped
- Note: PR-4 already added `is_allowlisted(node)` honoring to Pattern 10 (out-of-scope scope-creep flagged in PR-4 audit). This PR's await-detection is the orthogonal automatic mechanism. Both should coexist.

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


**Pre-handoff sanity checklist (MANDATORY, run before writing `PR_N_HANDOFF.md`):**

Before declaring done, AG runs each of these in order and pastes evidence in a "Pre-handoff checklist" section at the top of the handoff doc. **If you can't paste evidence for any item, the PR isn't done — fix the gap before writing the handoff.** Codex independently verifies this section exists and is complete.

1. **Commit hash:** Write `**Commit:** <auto>` in the handoff doc's commit-hash field. The pre-commit hook at `scripts/hooks/inject_handoff_hash.py` will replace the placeholder with the actual HEAD hash (= the implementation commit being audited) at commit time. The handoff records the commit BEING AUDITED, not the handoff's own commit — this is the documented convention that resolves the chicken-and-egg hash-drift problem. **Do NOT manually edit the injected hash after commit.** If you amend the implementation commit, regenerate the handoff with `<auto>` and re-commit; the hook will re-inject.
2. **Diff inventory:** Run `git diff --name-only master..HEAD` — paste output. Every file in the diff MUST also appear in the handoff's "Diff summary" section. No surprise files.
3. **mypy --strict:** Run `python -m mypy --strict src/claude_memory` — paste output. MUST show "Success: no issues found in 40 source files." Zero errors. If errors appear, fix them; do not declare done with mypy failures.
4. **Contract scanner:** Run `tox -e contracts` — paste output. Confirm violation count delta = 0 vs pre-PR baseline (PRs 1-5) OR absolute baseline 13 (PR-6 only).
5. **Ruff:** Run `python -m ruff check src/claude_memory` — paste output. Note any new warnings (existing invalid-noqa for `# noqa: contract` markers tolerated).
6. **Bandit:** Run `python -m bandit -r src/claude_memory -ll` — paste output. Should show only the accepted `embedding_server.py:148` bind-all.
7. **Caller sweep (if API contract changed):** For any return type or signature change in this PR, run `rg "<old_pattern>" --type py` to find remaining old-shape callers. Paste the rg command run AND the result. Production code count must be 0; all test files must be updated to new shape. If your PR changed `MemoryService.search()` return type, the rg pattern is `memory_service\.search\(|service\.search\(`.
8. **Test-first evidence (PR-5+):** Count the rows in the spec's Tests table marked "TEST FAILS" pre-PR. The handoff's "Test-first evidence" section MUST contain captured failure output for that exact count of tests, organized per failing test. Mismatch = incomplete.
9. **Per-criterion evidence:** Read this PR's "The bar" section. For each bullet, write the evidence (file:line / command output / test output) in the handoff's "Evidence per audit criterion" section. Walk the bullets one by one — do not declare done if any bullet lacks evidence.

This checklist is your last line of defense before audit. Skipping it doesn't save time — it just shifts the work to a failed audit cycle, which costs more.

**Test-first evidence requirement (applies to PR-5 onwards):** Each PR's Tests section is a 5-row table: 3 evil / 1 sad / 1 neutral. Each test row marks expected pre-PR and post-PR behavior. For any test marked **"TEST FAILS"** on pre-PR (i.e., genuine TDD targets), AG MUST:
1. Check out the pre-PR base in a separate worktree (`git worktree add ../pre-pr-base <pre-pr-commit-hash>`)
2. Copy the new test file into that worktree
3. Run the test against the pre-PR base, capture verbatim failure output
4. Paste the captured failure output in the handoff under a "Test-first evidence" section, organized per failing test
5. Then implement the fix in the actual PR branch and verify all tests pass

Tests marked **"TEST PASSES"** on pre-PR (regression-prevention or already-correct-behavior verifications) are exempt from the failure-capture requirement — they pass on pre-PR by design.

The neutral (happy-path) test is also exempt; it's expected to pass post-implementation by definition.

This forces TDD ordering. Without test-first evidence, the test was written after the code (anti-pattern: tests-enforcing-bugs, Layer 3.5.16). Codex independently re-runs the test against the pre-PR commit and verifies the failure output matches your handoff claim.

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
