# Dragon Brain Remediation — Audit Spec (for Codex)

**Date:** 2026-05-13 (split from merged spec 2026-05-14)
**Architect:** Claude (defines audit criteria)
**Auditor:** ChatGPT Codex 5.5 (this is your spec)
**Builder:** Antigravity (under separate build spec — you do not see their implementation recipe)
**Director:** Tabish

This is the audit-side document. The build spec for AG lives in a separate `REMEDIATION_BUILD_SPEC.md` — you do not need to read it. Auditing the recipe biases you toward verifying recipe-following instead of outcome-achievement. **Audit outcomes, not recipes.**

---

## What You're Auditing

Six PRs land fixes for known production wrong-answer bugs and state-consistency gaps in Dragon Brain v1.2.0. Each PR has pre-defined audit criteria below. Your job: verify those criteria are met, against ground truth (the diff, the actual code, command outputs, test results).

**Pilot status:** Codex Round 1 found gaps that 10 batches of B10 remediation missed (Cypher injection, point-in-time payload drift, temporal direction enum drift). The adversarial seat has demonstrated value. Round 2 is the operational shakedown.

---

## Audit Trigger (When You Fire)

You audit **per-PR**, only after AG creates `PR_N_HANDOFF.md` at the repo root AND pushes the corresponding `remediation/pr-N-*` branch. Director invokes you with: (a) the branch ref, (b) the handoff doc path, (c) this audit spec.

You do NOT fire on Director schedule against arbitrary repo state. Auditing an empty diff produces an "empty audit fail" that wastes a cycle. If no handoff doc exists for the PR being audited, the audit is invalid; reschedule.

---

## Audit Scope (What You Audit)

You audit **only the single PR named in the invocation**, not the whole spec batch. Other PRs in the spec are out of scope for this round — they will get their own audit invocations when their respective handoff docs are committed.

**Do not mark a per-PR criterion as failed because a later PR hasn't shipped.** Specifically: criterion (c) on PRs 1-5 is **"delta = 0"** (no new violations introduced — regression-prevention). The absolute contract-scanner baseline of 13 returns only after PR-6 ships its scanner fix. If you're auditing PR-3 and the scanner reports 75 violations, that's correct as long as the count is unchanged from pre-PR-3 state. Verify the delta, not the absolute.

---

## Handoff Doc Semantics

`PR_N_HANDOFF.md` is the AG-prepared **structured input** that points you at the evidence to verify. It is NOT builder self-attestation.

**You MUST:**
- Read the handoff doc
- Independently verify each claim in it against ground truth (file:line in the diff, command output, test result)
- Treat the handoff as a navigation aid: it tells you where to look, you confirm what's there

**You MUST NOT:**
- Refuse to inspect the handoff because "the builder prepared it" — that's the same as a financial auditor refusing to read the balance sheet. Read it, then verify against bank statements.
- Accept the handoff's claims without ground-truth verification. Trust nothing without independent check.

The two errors are symmetric: ignoring the handoff slows you down without making you more rigorous; trusting it without verifying defeats the audit.

---

## Audit Protocol (Run This, In Order)

Before any LLM reasoning, run the deterministic tools:

1. **Run `tox -e contracts`** and paste full output.
   - For PRs 1-5: confirm **delta = 0** vs the pre-PR violation count (no new violations introduced; absolute count remains 75 until PR-6 ships)
   - For PR-6: confirm absolute baseline 13

2. **Run `python -m mypy --strict src/claude_memory`** and paste output. Confirm 40 files, no errors.

3. **Run `python -m bandit -r src/claude_memory -ll`** and paste output. Confirm only the bind-all at `embedding_server.py:148` (already noqa'd, accepted).

4. **Run `python -m ruff check src/claude_memory`** and paste output. Confirm no new ruff errors (existing invalid-noqa warnings tolerated for now).

5. **Run `RUN_INTEGRATION=1 tox -e integration -- tests/integration/<relevant_file>.py`** for the integration test file the PR adds or modifies. Paste output.

6. **For each per-PR audit criterion** (a)/(b)/(c)/..., paste evidence (file:line reference, command output, or test output) demonstrating the criterion is met. No "looks fine" — evidence or fail.

7. **Cross-check against this spec's per-PR section.** Every listed criterion must be satisfied. Missing any = audit fail = back to AG.

8. **Pre-handoff checklist verification.** Confirm `PR_N_HANDOFF.md` includes a "Pre-handoff checklist" section near the top with all 9 items present and evidence pasted (commit hash, diff inventory, mypy, contracts, ruff, bandit, caller sweep, test-first evidence count, per-criterion walkthrough). If the section is missing OR any item lacks evidence OR an item shows a failure that wasn't resolved before handoff was written, mark as PARTIAL PASS with a Discovery: "Pre-handoff checklist incomplete — AG declared done without running the sanity gate. Specific gaps: [list each missing/incomplete item]." This is additive signal, not a primary blocking criterion (the per-PR criteria below take precedence) — but a clean audit with a missing checklist signals AG drift and should be flagged for the next round.

9. **Test-first evidence verification (PR-5 onwards only).** For PRs that include a Tests-as-table section in the build spec (PR-5 and PR-6 of this batch), each test row marks expected pre-PR behavior. For any test marked **"TEST FAILS"** on pre-PR:
   - The handoff doc MUST include verbatim first-run failure output for that test, captured against the pre-PR base commit
   - You MUST independently verify the failure by checking out the pre-PR commit in a worktree (`git worktree add ../audit-base <pre-pr-commit>`), copying the new test file in, and running it. The actual failure output must match the handoff's claim.
   - If the test passes on pre-PR base when the spec says it should fail: the test isn't testing what the spec wants. Mark as PARTIAL PASS with a Discovery: "tests-enforcing-bugs anti-pattern — test design did not lead implementation; rewrite tests with adversarial framing."
   - Tests marked **"TEST PASSES"** on pre-PR are regression-prevention and exempt — do not require failure capture for those.
   - PRs without the Tests-as-table format (PR-1 through PR-4) skip this step.

10. **Discoveries section.** For each finding you identify as a new bug outside this spec's scope — flag in a separate "Discoveries" section in your audit response. These don't block the current round but feed the next remediation cycle.

11. **Strict-gate multi-seed protocol (PR-5 onwards, for any RuntimeWarning-class audit).** When a per-PR audit criterion involves running pytest with `-W error::RuntimeWarning` or similar warning escalations, the canonical gate MUST be a multi-seed sweep — NOT a single run, NOT `-p no:randomly`. Single runs are seed-flaky (pytest-randomly is active by default; emission rate measured at ~25-33% across seeds on Dragon Brain's suite). The `-p no:randomly` shortcut freezes one lexical ordering — masks bugs at other orderings while passing deterministically. Canonical pattern:

    ```bash
    for seed in 1 7 12345 4231726796; do
      result=$(python -m pytest <target> -W error::RuntimeWarning --randomly-seed=$seed -q --tb=no 2>&1 \
        | grep -E "RuntimeWarning|PytestUnraisableExceptionWarning" | wc -l)
      echo "seed=$seed matches=$result"
    done
    ```
    All seeds must report `matches=0`. Any non-zero = FAIL. Seed values are illustrative; per-PR spec may specify different seeds.

12. **Subprocess-per-test attribution (warning-class failures only).** If a multi-seed sweep emits warnings, BEFORE marking the audit as FAIL, run subprocess-per-test on the failing file at the failing seed to confirm attribution:

    ```bash
    python -m pytest <failing-file> --forked -W error::RuntimeWarning --randomly-seed=$failing_seed -v 2>&1
    ```

    (Requires `pytest-forked`; install if missing.) Subprocess isolation per test eliminates cross-test GC bleed — the warning's attribution becomes deterministic. The test that emits in its own subprocess IS the source. Report the confirmed attribution in your audit. This protocol prevents wasted trifecta cycles on misattributed sites — three prior cycles in Issue #14's arc burned on GC-misattribution before this rule existed.

---

## Constraints (Codex Must NOT)

- Skip the deterministic tool runs (Round 1's gap)
- Rely on your own static analysis where a deterministic tool exists
- Audit aspects outside this spec's scope as if they were build requirements (scope creep)
- Treat the handoff doc as builder self-attestation (refusing to read it)
- Mark a per-PR criterion as failed because a different PR hasn't shipped
- Audit recipe-following instead of outcome-achievement (you don't see the recipe; this constraint is structural)

---

## Per-PR Audit Sections

Each section below tells you the bug being fixed (so you understand what outcome to verify) and the criteria you check.

---

### PR-1 — Cypher Label Injection Guard

**Bug being fixed:** `repository.py:90` interpolates a label string into a Cypher MERGE without validation. The label flows from `create_memory_type(name: str)` → ontology → here. Malformed memory type names corrupt the graph schema silently. Single-user threat model = graph-corruption-from-typo, not CVE-class, but real.

**Criteria:**
- (a) Validator rejects: empty string, lowercase start, spaces, `}`, `{`, `:`, `'`, `"`, backtick, newline. Each rejection raises `ValueError` (or equivalent Pydantic `ValidationError`).
- (b) Validator accepts: `Entity`, `MemoryType`, `Concept_v2`, `A`, max-64-char identifier. Each acceptance returns the value unchanged.
- (c) `tox -e contracts` post-PR shows **delta = 0** (no new violations introduced; absolute count unchanged from pre-PR baseline).
- (d) A direct call to `create_node` bypassing the schema validator with an injection payload (e.g., `"Entity { x: 1}"` as label) triggers a defensive `AssertionError` before the Cypher query is constructed.

---

### PR-2 — Point-in-Time `created_at` Payload Contract

**Bug being fixed:** `point_in_time_query` at `search.py:187` filters Qdrant on `created_at_lt`. Qdrant payloads written at `crud.py:136-140` only contain `name`, `node_type`, `project_id` — no `created_at` field. The filter returns wrong answers right now. Fix: add `created_at` to payload at all write sites + backfill existing points.

**Criteria:**
- (a) Qdrant payload writes include `created_at` in all three sites: `create_entity`, `add_observation`, `update_entity` re-embed.
- (b) The backfill script is idempotent — running it twice in succession reports 0 updates on the second run.
- (c) Integration test exists at `tests/integration/test_point_in_time.py`, demonstrably fails on the pre-PR codebase (regression-witness — must exhibit the wrong answer when the payload lacks `created_at`).
- (d) `tox -e contracts` post-PR — delta = 0 (no NEW violations introduced).
- (e) Qdrant filter semantics for ISO-8601 string range verified — the PR description quotes the official Qdrant documentation URL confirming lexicographic comparison works on fixed-width ISO-8601 timestamps.

---

### PR-3 — Temporal Direction Enum Drift

**Bug being fixed:** `schema.py:338` accepts `Literal["forward", "backward", "both"]`. `repository_queries.py:82` checks for `"before"` / `"after"` / fallthrough. Calling with `direction="forward"` falls through to default-"both" silently. Wrong answer, no error. Fix: accept all four spellings as semantic equivalents permanently. NO deprecation warning per spec decision (single-user system, warning noise is friction).

**Criteria:**
- (a) All four spellings (`before`/`after`/`forward`/`backward`) produce semantically correct results: `before`=`backward` (past-edge), `after`=`forward` (future-edge), `both`=union.
- (b) `tox -e contracts` post-PR — delta = 0 (no NEW violations introduced).
- (c) No `warnings` module import or `warn(...)` call added to the repository or schema code (confirms the no-deprecation-noise decision was honored).
- (d) Cross-check `get_temporal_neighbors` callers in the codebase — none rely on the silent-fallthrough-to-both behavior (grep for `direction=` calls, confirm the fix doesn't regress existing usage).

---

### PR-4 — Observation Cross-Store Compensation

**Bug being fixed:** `crud_maintenance.py:90-139` writes Observation to graph first, then Qdrant. On Qdrant failure, current behavior raises but doesn't roll back the graph write — leaving graph-only observations on infrastructure failure. `crud.py:142-159` (`create_entity`) DOES have proper compensation. Fix: mirror the entity-creation compensation pattern for observation creation.

**Criteria:**
- (a) Compensation symmetry with `create_entity` — same structural pattern (try Qdrant, on failure delete graph node and raise SearchError), same SearchError class, similar log message format. Read both code paths and confirm structural parity.
- (b) Integration test exists in `tests/integration/test_db_kill_scenarios.py` that uses real `container.kill()` on Qdrant mid-`add_observation` (not a mock), and asserts no orphan Observation node exists in the graph post-failure.
- (c) Entity re-embed (the secondary derived state, `crud_maintenance.py:141-169`) remains warn-and-continue, NOT fatal. Verify this — the secondary state must not be promoted to a hard failure.
- (d) `tox -e contracts` post-PR — delta = 0 (no NEW violations introduced).

---

### PR-5 — Channel Degradation Surfaced Through MCP

**Bug being fixed:** `search.py:615` tracks per-channel degradation; `server.py:311` exposes only temporal-exhaustion metadata. Channel health is computed and discarded. Caller can't tell if a result set is partial due to FTS being down. Fix uses **option A architecture**: `MemoryService.search()` always returns dict shape `{'results': [...], 'metadata': {...}}`; MCP `server.search_memory()` strips metadata and returns plain list when `include_meta=False`; all internal callers updated to access `result['results']`.

**Criteria:**
- (a) `self._last_*` instance attributes are gone (`rg "self\._last_" src/claude_memory/` returns zero matches, including comments).
- (b) Concurrent-search test passes — two parallel `MemoryService.search()` calls (one with FTS killed mid-flight, one healthy) both return correct per-call metadata in their dict responses with no cross-talk via shared state.
- (c) **Service-level always returns dict; MCP-level transforms to list when `include_meta=False`.** Verify: `MemoryService.search()` direct call returns `{'results': [...], 'metadata': {...}}`. `server.search_memory(include_meta=False)` returns plain list (backward compat at MCP boundary only). All internal callers of `MemoryService.search()` access `result["results"]` — verify with `rg "memory_service\.search\(|service\.search\(" --type py` and check each call site updated.
- (d) `tox -e contracts` post-PR — delta = 0 (no NEW violations introduced).

---

### PR-6 — Contract Scanner Precision Fix

**Bug being fixed:** `scripts/trace_contracts_dragon.py:288-319` flags `self.repo.<method>` inside async defs as Sync-IO-in-Async without checking for the `await` keyword. Result: 62 false positives on properly-migrated B10 call sites where `self.repo` is the `AsyncMemoryRepository` wrapper. CI gate has been silently failing since B10. Fix: add await-keyword detection to Pattern 10.

**Important context for this audit:** PR-6 is the only PR where the criterion is **absolute baseline 13**, not delta. PR-6 IS the fix that brings the absolute count to 13.

**Criteria:**
- (a) `tox -e contracts` post-PR shows **13 violations matching absolute baseline** (not delta — this is the PR that achieves baseline).
- (b) Unit test at `tests/unit/test_contract_scanner.py` exists with synthetic AST cases verifying await-detection logic: `await self.repo.get_node(...)` inside `async def` is NOT flagged; bare `self.repo.get_node(...)` inside `async def` IS flagged.
- (c) Scanner still flags genuine bugs — verify by reading the test for the bare (un-awaited) case.
- (d) Change is purely additive — no existing violations from the original 13 baseline categories (Bare Pass, Silent Fallback, Per-Item Swallow) were silently dropped. Compare pre-PR and post-PR `contract_violations_report.md` to confirm the 13 real violations all still appear.

---

## Important Context for All Audits

**The 62 sync-IO-in-async violations in pre-PR-6 scans are scanner false positives.** They come from properly-migrated B10 async wrapper calls. Do not flag them as real bugs in any PR audit — they are tracked for fix in PR-6 specifically.

**The 13 baseline violations** (in `lock_memory.py`, `retry.py`, `server.py`) are documented legitimate fallback paths under quarterly review per CLAUDE.md. Do not flag these in any audit — they are explicitly out of scope.

**The bind-all on `embedding_server.py:148`** has `# noqa: S104` and is accepted (containerized service binding inside Docker network). Do not flag this in any audit.

**`embedding_server.py` having zero internal importers** is intentional (it's a microservice in its own container). Do not flag this as dead code.

**Tabish is the only MCP caller of all six tools.** Some of the spec's "concrete fix" decisions (which you don't see) explicitly skip backward-compat shims, deprecation warnings, and caller-inventory steps because of this. If you see what looks like missing backward-compat protection, check whether the spec decision was to skip it for single-user reasons before flagging.

---

## Output Format

When you complete an audit, produce:

```markdown
# PR-N Audit Result

**Verdict:** PASS | FAIL | PARTIAL PASS

## Tool outputs (verbatim)
[paste outputs from steps 1-5 of the protocol]

## Per-criterion evidence
### (a) [criterion text]
**Status:** PASS | FAIL
**Evidence:** [file:line / command output / test output]

### (b) [criterion text]
[...]

## Discoveries (out-of-scope findings)
[any net-new bugs not covered by this PR's criteria — flag for next remediation cycle, do not fail current PR on these]

## Cross-check verdict
[summary: all criteria met = PASS; any criterion missed = FAIL]
```

If verdict is FAIL or PARTIAL PASS, name the failing criteria precisely. Don't bury the lede.

*Audit outcomes, not recipes. The deterministic tools are your floor; the per-PR criteria are your ceiling. Stay in the box.*
