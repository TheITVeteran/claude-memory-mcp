# PR-4 Handoff — Observation Cross-Store Compensation

**Branch:** `remediation/pr-4-observation-compensation`
**Commit:** `e4471eb` (code+handoff commit; hash from final amend)
**Base:** `08772b4` (master, post PR-3 merge + spec doc update)

---

## Diff Summary

All files appearing in `git diff --name-only master..HEAD`:

| File | Change | Purpose |
|------|--------|---------|
| `src/claude_memory/crud_maintenance.py` | Modified | Compensation logic: on Qdrant upsert failure, DETACH DELETE observation from graph, raise `SearchError`. Noqa marker on compensation call site. |
| `tests/unit/test_memory_service.py` | Modified | Updated `test_evil8` from `ConnectionError` → `SearchError` + DETACH DELETE assertion |
| `tests/integration/test_db_kill_scenarios.py` | Modified | Added `test_kill_qdrant_mid_add_observation_compensates` regression witness. Fixed `entity.id` (EntityCommitReceipt is Pydantic model, not dict). |
| `scripts/trace_contracts_dragon.py` | Modified | Added `is_allowlisted(node)` check to Pattern 10 — allowlist markers (including `noqa: contract`) were defined but never applied to Sync IO in Async violations |
| `PR_4_HANDOFF.md` | New | This document |

---

## Per-Criterion Evidence

### (a) Compensation symmetry with `create_entity`

| Property | `create_entity` (crud.py:158-176) | `add_observation` (crud_maintenance.py:136-158) |
|----------|-----------------------------------|--------------------------------------------------|
| Exception class | `SearchError` | `SearchError` |
| Error message format | `"Vector store unavailable during create: ..."` | `"Vector store unavailable during observation add: ..."` |
| Log message | `"vector_upsert_failed for %s — compensating FalkorDB write to prevent split-brain"` | `"observation_vector_upsert_failed for %s — compensating FalkorDB write to prevent split-brain"` |
| Compensation action | `await self.repo.delete_node(node_id)` | `await self.repo.execute_cypher("MATCH (o) WHERE o.id = $id DETACH DELETE o", ...)` |
| Compensation failure log | `"Compensating FalkorDB delete failed for %s. Orphan node left in graph!"` | `"Compensating FalkorDB delete failed for observation %s. Orphan observation left in graph!"` |

### (b) Integration test exercises real container kill

`test_kill_qdrant_mid_add_observation_compensates` (test_db_kill_scenarios.py):
1. Creates entity while both stores healthy (`entity.id` — EntityCommitReceipt attribute access)
2. `qdrant_container.get_wrapped_container().kill()`
3. Calls `add_observation` → asserts `SearchError` raised with `match="Vector store unavailable during observation add"`
4. Verifies no orphan Observation node in FalkorDB graph via Cypher count query

Gated by `RUN_INTEGRATION=1` (pytestmark at module level).

**Round 1 bug fix:** Original test used `entity["id"]` (dict key access) on `EntityCommitReceipt` (Pydantic model). `AttributeError` would crash the test before reaching the compensation assertion. Fixed to `entity.id`. This is the cost of code-first; PR-5+ applies test-first evidence requirement.

### (c) Entity re-embed remains non-fatal (warn-and-continue)

Lines 162-191 in `crud_maintenance.py` — the try/except around entity re-embed and FTS re-index both catch `Exception` and log warnings without raising. Unchanged from pre-PR.

### (d) Contract scanner — delta = 0

```
Post-PR:  75 violations (Sync IO: 62, Bare Pass: 6, Silent Fallback: 5, Per-Item Swallow: 2)
Pre-PR:   75 violations (Sync IO: 62, Bare Pass: 6, Silent Fallback: 5, Per-Item Swallow: 2)
Delta:    0
```

**Scanner fix included:** Pattern 10 (Sync IO in Async, lines 306-321) never called `is_allowlisted()` despite `ALLOWLIST_MARKERS` being defined at line 44 and used by all other patterns. Added `if is_allowlisted(node): continue` before appending violations. This enables the spec's sanctioned `# noqa: contract` suppression for the compensation call site.

**Noqa marker:** `crud_maintenance.py:144` — `await self.repo.execute_cypher(...)  # noqa: contract — properly awaited; scanner Pattern 10 is await-blind, fixed in PR-6`

### (e) Unit test updated

`test_evil8_add_observation_vector_upsert_failure_raises` (test_memory_service.py:388):
- Now expects `SearchError` (not raw `ConnectionError`)
- Asserts compensation DETACH DELETE was issued (checks last `execute_cypher` call args)
- Docstring updated to reference PR-4 compensation contract

---

## Tool Outputs

| Check | Result |
|-------|--------|
| Unit tests | 1268 passed, 0 failed |
| Ruff | Passed |
| Mypy strict | Passed (crud_maintenance.py — no issues) |
| Pre-commit hooks | All passed |
| Contracts | 75 violations, delta = 0 ✅ |

---

## Discoveries

1. **Scanner Pattern 10 was noqa-blind.** `ALLOWLIST_MARKERS` (line 44) included `"noqa: contract"` but Pattern 10 never checked `is_allowlisted()`. All except-handler patterns (1-8) did. Fixed in this PR as a minimal prerequisite for the noqa suppression. This change is purely additive — no existing violations were dropped (the noqa marker only appears on the one new line). PR-6 will obsolete the noqa marker entirely when it adds proper await-detection.

2. **`create_entity` returns `EntityCommitReceipt`, not `dict`.** Integration test originally used `entity["id"]` which would have crashed with `AttributeError` before reaching the compensation assertion. Fixed to `entity.id`. Root cause: code-first discipline. Spec's new test-first evidence requirement (PR-5+) prevents this class of bug.
