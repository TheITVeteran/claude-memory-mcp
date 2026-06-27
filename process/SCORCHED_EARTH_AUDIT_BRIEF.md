# Scorched Earth Audit Brief — Dragon Brain Production Codebase

**Audit run:** TBD (queued — fires after B10.5 merges + ~1 week production soak)
**Auditor:** ChatGPT Codex 5.5 — **NEW session** (no context inheritance from #22 arc or B10.5)
**Director:** Tabish ("iikarus4")
**Architect:** Claude

---

## Mission

Run a comprehensive a-z audit of Dragon Brain production code (post-B10.5 stable state). Maximum surface, no scope reduction. Output is a raw finding list; Director + Architect triage jointly into actionable remediation batches.

**Why scorched earth:** the 14a-22f arc proved bug classes hide in adjacent surfaces. Focused work missed things that maximum-coverage would have caught. The 14a-e minefield was DISCOVERED through accident-surface exploration, not through planned audits. We're maximizing accident surface here.

## What we want from you (the Auditor)

This is **signal generation**, not remediation. We want findings flagged — even uncertain ones — so we can triage them ourselves with full domain context. Better to over-flag than to suppress.

You are an outside skeptic. Treat the codebase as if you have never seen it before. **Question intent.** Do not skip findings because "the existing tests look comprehensive" or "this seems intentional." The 14a-e bug class hid for months behind a `_drain_orphan_coroutines` autouse fixture that "was there for a reason." It wasn't.

## Surface boundaries

**In-scope:**
- `src/claude_memory/` — all production code (the main audit target)
- `scripts/` — operational tools (heal_graph, recover_graph, backfill_*, embed_observations, etc.) — EXCEPT `scripts/trace_contracts_dragon.py` (the AST scanner shipped 22f; not for audit)
- `pyproject.toml` — dependency surface
- `docker-compose.yml`, `Dockerfile`s (any `Dockerfile.*` variants) — infra contracts

**Out-of-scope (do not audit):**
- `tests/` — heavily audited in 14a-22f arc; diminishing returns. Exception: if you spot a test that *enforces a known bug* (the "tests-enforcing-bugs" anti-pattern), flag it.
- `process/` — process docs, not production behavior
- `benchmarks/` — research code, not production

## Audit dimensions (cover all eight, tag each finding by bucket)

1. **Correctness** — logic bugs, off-by-one errors, wrong return shapes, edge cases (empty inputs, `None` handling, Unicode, integer overflow, type coercion surprises). Anything where the code does the wrong thing.

2. **Security** — injection (Cypher, SQL, path traversal, shell), authorization bypass, secrets in logs / error messages / responses, schema validation gaps, deserialization risks (pickle, YAML, JSON with untrusted input). The MCP tool surface is the external interface — particular attention there.

3. **Async / concurrency** — race conditions, missing locks, unawaited coroutines, event-loop blocking calls, cancellation handling, connection pool starvation, async context manager misuse, `asyncio.gather` with `return_exceptions=True` that silently drops errors.

4. **Error handling + contracts** — swallowed exceptions, wrong error types raised, inconsistent error envelopes, fail-loud vs fail-silent boundaries that disagree across call sites, `except Exception` that should be narrower, missing `from e` on re-raises.

5. **Resource management** — connection leaks (FalkorDB / Qdrant / Redis), file handle leaks, memory growth patterns, cleanup paths that miss `try/finally`, retry-bomb risks (uncapped retry loops that hammer infra under failure), background tasks that don't get cancelled on shutdown.

6. **Cross-store consistency** — FalkorDB ↔ Qdrant ↔ SQLite FTS interaction failure modes, compensation completeness across ALL CRUD paths (B10 added entity + observation compensation; survey the rest), observable degradation in search responses, split-brain risk under partial failure.

7. **API / contract** — MCP tool surface contracts (do tool schemas match implementations?), schema drift between docs and code, deprecation handling, backward compatibility risks, semantic versioning concerns. The MCP boundary is what external clients depend on.

8. **Observability** — logging quality (right level? structured? scrubbed of secrets?), error message clarity (would a maintainer at 2am understand it?), debuggability under failure (can you reconstruct what happened from logs alone?), audit-log completeness (the embedding service has a client_id audit hook — is it consistently honored?).

## Output format (REQUIRED — keeps signal triagable)

Emit each finding in this exact format:

```
## Finding [N]: <Title>

- **Bucket:** [Correctness | Security | Async | Error | Resource | Consistency | API | Observability]
- **Severity (your first read):** [Critical | High | Medium | Low | Info]
- **Location:** path/to/file.py:LINE (or LINE-LINE range)
- **Behavior:** What actually happens (with quoted code if it clarifies)
- **Expected:** What should happen
- **Reproduction or proof:** AST scan / test path / argument that demonstrates the issue. If you can show it with a code snippet, do.
- **Suggested fix shape:** ONE OR TWO SENTENCES — not a complete patch. We scope remediation ourselves.
```

**Why "fix shape" not "patch":** we want you in audit-signal mode, not remediation-work mode. Generating patches dilutes the focus on finding issues. Architect drafts remediation specs after triage; you just point at problems.

## Severity rubric (your first read — Director adjusts in triage)

- **Critical** — production data loss, security breach surface, silent wrong-answer in a load-bearing path. Ship-blocker for any new feature.
- **High** — likely user-visible bug, real exception leak, observable degradation under realistic conditions.
- **Medium** — buggy edge case unlikely to hit in current usage but real if hit.
- **Low** — code smell or risk that compounds over time; not a current bug but a maturity gap.
- **Info** — low-confidence finding. You're not sure it's a bug, but it looked off enough to flag. Director decides.

**Over-flag with Info, do not suppress.** Better to give us 50 things to triage including 20 false positives than to filter out 5 real bugs.

## What NOT to do

1. **Do NOT skip findings because "the existing tests look comprehensive."** Tests can be wrong. Tests can enforce bugs. The 14a-e bug class had tests that PASSED while the underlying types were wrong.

2. **Do NOT skip findings because "this seems intentional."** Question intent. The previous developer's intent may have been wrong, or correct-at-the-time but stale now. If you cannot find documentation of WHY something was done a certain way, flag it.

3. **Do NOT produce complete patches.** Stay in audit mode. Suggested fix shape = 1-2 sentences max.

4. **Do NOT rank findings by your own priority across the full set.** Tag each by severity. Director + Architect rank globally during triage.

5. **Do NOT batch findings by file.** Emit them in discovery order (or by bucket, your choice). We resort during triage.

6. **Do NOT assume the trifecta enforcement infrastructure is sacred.** If `branch_write_guard.py`, `inject_handoff_hash.py`, `verify_handoff_completeness.py`, or the contract scanner have issues, flag them. They're production code too.

7. **Do NOT assume the 10 Category D allowlist files in `scripts/trace_contracts_dragon.py` are correct.** That allowlist was created by Architect investigation; if you spot something suspect about a file's pattern, flag it. The smuggling-check audit revealed Architect can miss things; you may too — different blind spots.

## Time / scope expectations

This is the kitchen sink. We are not optimizing for token cost. Take as long as you need to be thorough. We expect 50-200 findings as a reasonable range; if you find <20 the codebase is unusually clean (verify by going slower); if you find >300 the codebase is unusually rough (verify by spot-checking severity claims).

We do NOT expect you to fix anything. We do NOT expect remediation specs from you. We DO expect comprehensive coverage of the 8 dimensions across the in-scope surface.

## Downstream workflow (for your information — does not affect your output)

After you return findings:

1. Director forwards raw output to Architect in chunks (probably grouped by bucket)
2. Director + Architect score together — joint severity (Real-fix / Real-deferred / Not-real-with-note)
3. Real-fix findings cluster into remediation batches (natural PRs by file or area)
4. Architect drafts build + audit specs per batch following the calibrated trifecta pattern (same shape as 14a-22f arc)
5. AG implements per spec
6. **A NEW Codex session** audits each batch (so the auditor doesn't inherit context from this scorched earth pass — keeps each batch audit fresh)
7. Ship + cleanup

You will not audit the remediations from this brief — fresh Codex sessions handle that.

## Calibration reminder (verbatim — please internalize before starting)

> "This is a comprehensive audit, not a focused review. Surface findings even if you're not 100% sure they're real bugs — flag low-confidence findings with `Severity: Info` so we can decide. Better to over-flag and let us filter than to suppress and miss something. Adjacent to that — do NOT skip findings because 'the existing tests look comprehensive' or 'this seems intentional.' Question intent. Surface concerns. We'll judge."

## Context (for your situational awareness — not for filtering your audit)

- Dragon Brain is a persistent memory layer for AI agents (knowledge graph + vector search + MCP server)
- Current state: v1.2.1 + Issue #22 arc closed (test-suite mock architecture overhaul) + B10.5 just merged (native async migration)
- Original Audit Remediation Round 1 (May 2026) fixed 83 violations across 37 files via 10 batch PRs (B1-B10)
- Audit Remediation Round 2 (May 2026) added you (Codex) as the adversarial Auditor seat; you caught 3 production bugs the prior trifecta missed (Cypher injection at `repository.py:90`, point-in-time payload drift, temporal direction enum drift)
- 5 layers of physical enforcement now active: `branch_write_guard.py`, `inject_handoff_hash.py`, `verify_handoff_completeness.py`, `trace_contracts_dragon.py` Pattern 12, existing baseline ratchet at 13
- `process/ARC_22_CLOSE.md` is the most comprehensive public artifact if you want the WHY behind the enforcement layers

**Do not use this context to suppress findings.** Use it ONLY to understand what the code is supposed to do.

## Output cadence

You can deliver findings in a single comprehensive response OR streamed across multiple turns if your context budget requires it. Director prefers streamed (easier to start triage early) but defers to your judgment based on coverage quality.

If you stream, tag the final response with `[AUDIT COMPLETE]` so Director knows you've covered the full surface. If you stop mid-audit due to context exhaustion or other issues, tag with `[PARTIAL — RESUME NEEDED]` and indicate which files/dimensions remain to scan.

---

**Godspeed, Auditor.** The bug class that survived two years and ten remediation batches hid behind tests that "looked comprehensive." Find what's hiding now.
