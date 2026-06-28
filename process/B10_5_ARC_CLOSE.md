# Arc Close: B10.5 — Native Async Migration (June 2026)

This document captures the WHY behind the B10.5 native async migration and the
trifecta-calibration lessons from the 7-round arc. The HOW lives in
`process/issues/B10_5_BUILD_SPEC.md` and `process/issues/B10_5_AUDIT_SPEC.md`.
This is the narrative connecting them — specifically the lessons about
production-code arcs that don't apply to the test-hygiene arc shape of #22.

## What was deferred

The original Audit Remediation Round 1 (May 2026) — see `process/ARC_22_CLOSE.md`
predecessor + Dragon Brain Audit Remediation history — explicitly deferred
B10.5 as a future epic:

> B10.5 (native async via `falkordb.asyncio.FalkorDB`) deferred as future epic
> — current `asyncio.to_thread` wrapper is a correct intermediate state;
> FalkorDB v1.4.0 ships native async support, future epic will swap the
> wrapper out.

The wrapper at `src/claude_memory/repository_async.py` worked. It used
`asyncio.to_thread()` to defer every sync FalkorDB call to the default
thread-pool executor — unblocking the event loop but limiting concurrency to
the thread-pool size (`min(32, os.cpu_count() + 4)` workers by default). The
docstring noted: "This wrapper is the correct intermediate state."

**Why now (June 2026):** the #22 arc closed with the trifecta calibrated and
warm. Brain is the core of every other project. Closing the deferred epic
eliminated a recurring "mental tax" line from MEMORY.md and removed wrapper
indirection that costs in stack trace depth, async debugging difficulty, and
mental overhead reading the code — even if there's no measured performance
change.

## What we built

Single-PR Pattern A migration, 14 files, ~600 lines of substantive change:

1. **`src/claude_memory/cypher_queries.py`** (NEW) — extracted Cypher templates
   as module-level constants. ~30 constants covering CRUD, query, traversal,
   temporal, analysis surfaces. Eliminates query divergence risk between sync
   and async implementations.

2. **`src/claude_memory/repository_async.py`** (REWRITE) — `AsyncMemoryRepository`
   now uses `falkordb.asyncio.FalkorDB` directly via `from falkordb.asyncio
   import FalkorDB`. All 26 `asyncio.to_thread` wrapper sites eliminated. Same
   public API (mixin code unchanged). `@wrap_db_exceptions` decorator added
   with `ParamSpec` + `TypeVar` type preservation. Async retry logic mirrors
   sync's exact semantics (5 attempts, exponential backoff `2**attempt`,
   `await asyncio.sleep()`, same `ConnectionError("FalkorDB connection
   exhausted retries")` final exception).

3. **`src/claude_memory/repository.py`** (PRESERVED + DOCSTRING UPDATE) — sync
   `MemoryRepository` kept as diagnostic / CLI ops fallback (Director's
   "x-ray vision" call). Docstring explains its post-B10.5 role: used by
   `scripts/heal_graph.py`, `scripts/recover_graph.py`, and other operational
   scripts. Production async path goes through `AsyncMemoryRepository`. Both
   share Cypher templates via `cypher_queries.py`.

4. **`src/claude_memory/repository_queries.py`** + **`repository_traversal.py`**
   (MINIMAL TOUCH) — switched to use extracted Cypher constants.

5. **`src/claude_memory/tools.py`** (line 82 UPDATE) — construction simplified
   to `self.repo = AsyncMemoryRepository(host, port, password)`. No more
   wrapping a sync repo. `MemoryRepository` still imported in `tools.py` as a
   backward-compat re-export for tests that patch at that location.

6. **`src/claude_memory/retry.py`** (UPDATE) — `retry_on_transient` decorator
   rewritten with `ParamSpec` + `TypeVar` to preserve method signatures
   through the wrapper. The original `Callable[..., Any]` signature erased
   return types when applied at scale to `AsyncMemoryRepository` methods,
   causing `[no-any-return]` errors in mixin call sites.

7. **Test infrastructure** (`tests/_helpers/mock_factory.py` + 3 mutant test
   factory files) — patched to intercept the new production construction
   path. The 22-arc helper originally patched
   `claude_memory.repository.FalkorDB` (sync); now also patches
   `claude_memory.repository_async.FalkorDB` (the actual native async
   construction). Mutant test `_build()` factories updated for the same
   reason.

8. **`tests/unit/test_repository_async.py`** (REWRITE) — from 26
   parameterized delegation tests (verifying `asyncio.to_thread` calls
   correctly) to 38 behavioral tests mocking `falkordb.asyncio.FalkorDB`
   directly.

9. **`pyproject.toml`** (UPDATE) — `falkordb>=1.4.0,<2.0.0` (lower bound
   tightened from 1.0.0 to make native async explicit) + `redis>=7.1.0,<8.0.0`
   (transitive dependency cascade from the falkordb bump).

10. **`process/PR_B10_5_HANDOFF.md`** (NEW) — handoff doc with full audit
    evidence, integration test outputs, deterministic gates, oracle correction
    discoveries.

## The 14-file scope story (oracle corrections)

The initial spec scoped 9 files. The final scope was 14. Two oracle
corrections expanded the scope mid-arc — both passing the substance test for
spec-patch discipline:

**Expansion 1 (9 → 13 files) — Test infrastructure dependency.** Audit round 2
found 50 unit tests failing with `TypeError: object MagicMock can't be used in
'await' expression`. Root cause: the production construction path moved from
`claude_memory.repository.FalkorDB` (sync, which the 22-arc helper patches)
to `claude_memory.repository_async.FalkorDB` (async, which nothing patched).
The 22-arc helper at `tests/_helpers/mock_factory.py` and 3 mutant test
factory files (`test_mutant_dict_crud.py`, `test_mutant_dict_services.py`,
`test_mutant_temporal.py`) needed updating to patch the new path.

**Substance test:** would Builder have to do something WORSE to satisfy the
original 9-file scope? Yes — `# type: ignore[no-any-return]` annotations
across 50+ test sites (touches out-of-scope files), or some kind of
production-path backward-compat shim that defeats the migration. Direction:
spec scope expansion captures the migration's "no test regression" intent
more precisely. Oracle correction, not goalposts.

**Expansion 2 (13 → 14 files) — Decorator type erasure.** Audit round 3
escalation from Builder: applying `@wrap_db_exceptions` and `@retry_on_transient()`
decorators to `AsyncMemoryRepository`'s methods caused mypy strict failures
in three mixin files (`temporal.py`, `crud.py`, `analysis.py`) with
`[no-any-return]` errors. Both decorators had `Callable[..., Any]` signatures
that erased return types; the cascade hit any caller using `return await
self.repo.X()`.

**Substance test:** would Builder have to do something WORSE? Yes — `# type:
ignore[no-any-return]` across 7 mixin sites (out-of-scope), or weaken the
audit's "mypy strict clean" criterion to accept the errors. Both worse.
Direction: rewriting the two decorators with `ParamSpec + TypeVar` actually
satisfies the intent. Oracle correction.

## The architect-branch-guard origin story (6th enforcement layer)

I fell into the architect-on-AG-branch trap (committing architect-owned specs
on builder branches by accident) **5 times across the B10.5 arc**. Each time
needed cherry-pick + branch-reset cleanup. Verbal discipline ("always check
`git branch --show-current` before commit") was demonstrably insufficient.

**Mid-arc fix:** shipped `scripts/hooks/architect_branch_guard.py` as the
**6th physical enforcement layer**. Pre-commit hook that REFUSES commits
including architect-owned files (specs, hooks, scanner, CLAUDE.md,
ARCHITECTURE.md, process docs) on non-master branches.

**The hook validated itself by refusing my own commit attempt the same turn
it shipped.** I tried to commit a B10.5 spec patch while accidentally still
on the AG branch; the hook caught it; I followed the hook's own recovery
instructions (`git checkout master`); commit landed cleanly on master.

**Same lesson as 22f's `verify_handoff_completeness.py`:** when verbal
discipline fails 3+ times in different specific ways, switch to physical
enforcement. The discipline applies to Architect too, not just Builder.

The lockdown stack is now:

| Layer | Mechanism | Catches |
|-------|-----------|---------|
| 1. `branch_write_guard.py` | Per-issue path denylists | Architect spec edits on builder branches; conftest sneak-arounds; src/ scope creep |
| 2. `inject_handoff_hash.py` | Auto-inject Commit A's hash into handoff `<auto>` placeholder | Hand-edited / fabricated hashes |
| 3. `verify_handoff_completeness.py` | Validate handoff structure (4-seed evidence, canonical ruff, no `N/A`) | Single-seed baseline drift; `--exclude` flag; N/A shortcuts. **Patched twice during B10.5** — config regex too narrow + script internal filter bypass. |
| 4. `trace_contracts_dragon.py` Pattern 12 | AST scan for hand-rolled `MemoryService(embedding_service=...)` outside 17-entry allowlist | Bug class reintroduction via new test files |
| 5. Existing scanner Patterns 1-11 | Baseline 13 ratcheting toward zero | Original audit-remediation contract violations |
| **6. `architect_branch_guard.py`** | **Refuse architect-owned file commits on non-master branches** | **Architect-on-AG-branch trap (5 occurrences across B10.5 arc)** |

## Trifecta calibration lessons (5 new Codex catches)

B10.5 was the first arc to test the calibrated trifecta on production code.
The discipline scales — but production-code arcs have second-order
consequences test-hygiene arcs don't. Codex caught 5 additional failure
modes; 4 of 5 were Architect-side spec gaps:

1. **Test infrastructure dependency** (R2) — Architect spec missed
   helper/factory updates → expanded scope 9→13.
2. **Decorator type erasure** (R3 Builder escalation → R5) — Architect spec
   missed decorator type safety → expanded scope 13→14.
3. **Hook regex too narrow** (R4) — Architect-infrastructure gap from 22f →
   patched `.pre-commit-config.yaml`.
4. **Hook script internal filter bypass** (R5) — Same hook, second layer the
   first patch missed → patched the script's internal filter to match. This
   is **exactly the failure mode Dimension 9 of the scorched-earth brief was
   designed to surface** — defense-in-depth that doesn't share intent across
   layers creates bypass gaps.
5. **Handoff hash topology drift in amend cycles** (R6) — Builder amend
   hygiene; manually edited `**Commit:**` to a prior handoff commit hash
   instead of letting `inject_handoff_hash.py` refresh the `<auto>`
   placeholder.

The arc's PRODUCTION CODE was clean from round 1 (integration tests passed).
Rounds 2-7 caught specification + infrastructure gaps, not implementation
bugs.

## Production-code arc discipline (the meta-lesson)

B10.5 took 7 audit rounds vs the #22 arc's typical 1-2 rounds per sub-PR.
Why: production-code changes have SECOND-ORDER CONSEQUENCES that
test-hygiene arcs don't. Architect pre-flight should explicitly enumerate the
consequence chain BEFORE drafting initial spec, not discover them through
audit rounds.

Documented in operator's auto-memory feedback file
`feedback_production_arc_pre_flight.md` (5 consequence-chain categories to
enumerate: mock coverage, decorator types, hook/scanner coverage, dependency
cascade, cross-cutting type inference). Future production-code arcs should
walk this checklist as part of architect pre-flight investigation.

## Final state

- **Native async path** uses `falkordb.asyncio.FalkorDB` directly (no
  wrapper indirection); load-bearing integration tests (6 testcontainers
  scenarios) pass on native async
- **Sync `MemoryRepository` preserved** as diagnostic / CLI fallback —
  importable + instantiable, used by `scripts/heal_graph.py`,
  `scripts/recover_graph.py`, and other ops tools
- **Canonical Cypher templates** in `cypher_queries.py` shared by sync +
  async impls — eliminates query divergence risk
- **Decorators type-safe** (`ParamSpec` + `TypeVar`) — no more `[no-any-return]`
  cascades into mixin call sites
- **`tox -e contracts` baseline still 13** (Pattern 12 contribution 0)
- **Mypy strict clean** across 41 source files
- **1300 unit tests pass** + 8 helper tests + 38 behavioral tests for the new
  `AsyncMemoryRepository`
- **6 layers of physical enforcement** active (5 from 22 arc + architect_branch_guard
  shipped during B10.5)
- **Last deferred epic from Audit Remediation Round 1 closed.** No more
  outstanding architectural debt items from the original B10 series.

## For future maintainers

**Adding a new async repository method?** Add the Cypher template as a
constant in `cypher_queries.py` first. Then call it from both `repository.py`
(sync) and `repository_async.py` (native async) as needed. Mixin code uses
`await self.repo.method_name(...)`.

**Touching a decorator that gets applied to many methods?** Use `ParamSpec`
+ `TypeVar` to preserve method signatures. `Callable[..., Any]` decorators
erase types and cascade `[no-any-return]` errors into all caller files. See
`src/claude_memory/retry.py` for the canonical pattern.

**Adding a new pre-commit hook or scanner?** Beware double-filter layers.
If the hook has BOTH a `files:` regex in `.pre-commit-config.yaml` AND an
internal filter in the script, they MUST share intent (ideally a single
source-of-truth regex). Otherwise patching one creates silent bypass via the
other.

**Doing handoff amend cycles?** Revert the `**Commit:**` line to `<auto>`
before each amend; let `inject_handoff_hash.py` refresh it to the current
HEAD~1. Manually editing the literal hash leads to staleness across amend
cycles.

**Starting a production-code arc?** Read
`feedback_production_arc_pre_flight.md` first. Enumerate the consequence
chain (mock coverage, decorator types, hook/scanner coverage, dependency
cascade, cross-cutting type inference) BEFORE drafting initial spec.
Test-hygiene arc pattern doesn't apply.
