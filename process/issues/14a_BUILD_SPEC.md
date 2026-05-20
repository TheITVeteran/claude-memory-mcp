# Issue #14a — `test_tools_coverage.py` Async Mock Cleanup (Pilot Build Spec)

**Issue:** [iikarus/Dragon-Brain#14](https://github.com/iikarus/Dragon-Brain/issues/14) — sub-issue 14a (per-file chunk)
**Pilot status:** First sub-chunk validating the Deepthink blueprint (Topographical Forcing).
**Branch:** `issue-14a/test-tools-coverage-async-mocks`
**Architect:** Claude
**Builder:** Antigravity (this is your spec)
**Auditor:** Codex (under `14a_AUDIT_SPEC.md`)

---

## Target

Eliminate `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` emissions when running `tests/unit/test_tools_coverage.py` under strict gate.

**Acceptance:**

```bash
python -m pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -v 2>&1 \
  | grep -E "RuntimeWarning: coroutine|PytestUnraisableExceptionWarning"
```

→ ZERO matches. That is the pilot's pass/fail.

## Files in scope

- `tests/unit/test_tools_coverage.py` — modify as needed
- `process/PR_ISSUE_14A_HANDOFF.md` — create after the fix

## Files OUT of scope (write-guard enforced)

The pre-commit hook `scripts/hooks/branch_write_guard.py` reads `process/issues/14_HARNESS.toml` and blocks commits touching:

- `tests/unit/conftest.py`
- `tests/conftest.py`
- `pytest.ini`

If you try to commit a change to these, the hook fails the commit with the rationale. Do not bypass.

## Async signature inventory (architect-provided)

`tests/unit/test_tools_coverage.py` uses a `mock_service` fixture (or equivalent) that mocks a `MemoryService`. The following methods on `MemoryService` and its dependencies are async:

```
MemoryService methods (async):
  search, get_neighbors, get_hologram, traverse_path, find_cross_domain_patterns,
  get_evolution, point_in_time_query, diff_knowledge_state, create_entity,
  update_entity, delete_entity, create_relationship, delete_relationship,
  add_observation, archive_entity, prune_stale, analyze_graph,
  get_stale_entities, consolidate_memories, query_timeline, get_temporal_neighbors,
  create_temporal_edge, get_bottles, get_graph_health, list_orphans

AsyncMemoryRepository (svc.repo) methods (async — all are):
  select_graph, ensure_indices, create_node, get_node, update_node, delete_node,
  create_edge, delete_edge, execute_cypher, query_timeline,
  get_temporal_neighbors, create_temporal_edge, get_bottles, get_graph_health,
  list_orphans, get_all_edges, get_all_node_ids, get_observations_for_entity,
  get_subgraph, get_all_nodes, get_total_node_count, increment_salience,
  get_most_recent_entity, shortest_path_length

VectorStore (svc.vector_store) methods (async):
  upsert, search, delete, count, set_payload, scroll, ensure_collection

LockManager (svc.lock_manager) methods/dunders (async):
  __aenter__, __aexit__, async_acquire, _async_acquire_redis, _async_acquire_file

EmbeddingService (svc.embedder) methods (sync):
  encode — synchronous HTTP call

FTSStore (svc.fts_store) methods (sync):
  search, index_entity, update_entity — sqlite-based, sync

Reranker (svc.reranker) methods:
  rerank — async

ActivationEngine (svc.activation_engine) methods (async):
  activate, spread, detect_weak_connections

ContextManager (svc.context_manager) methods (sync):
  optimize

Ontology (svc.ontology) methods (sync):
  validate_node_type, get_required_properties
```

Use this as your reference. ANY mock targeting a method on the LEFT side of the colon (async) must be `AsyncMock`. ANY mock targeting a method on the RIGHT side (sync) stays `MagicMock`.

## Initial source-pattern audit (architect-provided)

Architect ran `rg -n "MagicMock\(" tests/unit/test_tools_coverage.py` and reviewed all 25 sites. All 25 appear correctly classified as sync-target mocks per static reading:

| Lines | Pattern | Target | Verdict |
|-------|---------|--------|---------|
| 96, 117, 121 (overridden 122-123), 126-128, 141 | Fixture-internal | embedder, reranker (overridden async), activation_engine (overridden async), mock_lock + sync dunders, generic result | SYNC (correct as-is) |
| 108-110 | Fixture-internal | fts_store + sync, lock_manager (its `lock()` method is sync, returns mock_lock which has async dunders) | SYNC (correct as-is) |
| 319, 402-407, 431, 561-647, 769 | mock_node, mock_obs_node, mock_path | Graph query result objects with `.properties` attribute | SYNC (these represent Cypher query results, not method targets) |
| 682 | Positional `MagicMock()` | List element / side_effect | SYNC (context: result of a retry-success pattern) |
| 699, 714 | `service.ontology = MagicMock()` | Ontology — sync per inventory | SYNC (correct) |
| 757, 773 | mock_search_result, context_manager | Search result dict, ContextManager (sync) | SYNC (correct) |

**Architect honest finding:** Static analysis says this file should be clean. The fact that Codex's audit confirmed warnings STILL emit means there's a subtle non-static issue — possibly:

- An AsyncMock being called without await somewhere in the test bodies (not in the fixture setup)
- A side_effect pattern that creates implicit coroutines
- Test code that synchronously calls an async-mocked method without awaiting it

Architect cannot find this from static reading of 787 lines. Builder's job is the empirical discovery loop.

## Discovery loop (Builder execution)

1. **Run the strict gate and capture the first warning context:**

   ```bash
   python -m pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -v 2>&1 | tee /tmp/14a_strict.log
   ```

   Look for the test names that PASSED but emitted the warning afterward. The warning attribution is GC-nondeterministic (it fires whenever GC reaps the unawaited coroutine), but the test boundary visible in pytest's output narrows the scope.

2. **For each test that's a likely emission source, find AsyncMock calls without `await`:**

   ```bash
   # Within the test file, find async-target accesses without await
   rg -n "(mock_service|svc|service)\.(repo|vector_store|search|create_entity|update_entity|delete_entity|create_relationship|add_observation|archive_entity|query_timeline|traverse_path|reranker\.rerank|activation_engine\.(activate|spread)|lock_manager\.async_acquire)\.[a-z_]+\(" tests/unit/test_tools_coverage.py | grep -v "await\|assert_awaited\|assert_called"
   ```

   This catches calls to async-target methods that aren't preceded by `await` and aren't part of an assertion. Each match is a candidate.

3. **Fix each candidate site:** add `await` where the test body should be awaiting the result, OR change the test logic if it's intentionally creating-but-not-awaiting (rare; usually a bug).

4. **Re-run the strict gate. Iterate until zero matches.**

## Golden diff (architect-provided template)

Here is exactly what a fix looks like — copy the pattern:

```diff
 @pytest.mark.asyncio
 async def test_something(mock_service):
     mock_service.repo.get_node.return_value = {"id": "x"}

-    # BAD: creates coroutine, never awaits, GC reaps → warning
-    result = mock_service.repo.get_node("x")
+    # GOOD: awaits the AsyncMock-returned coroutine
+    result = await mock_service.repo.get_node("x")

     assert result["id"] == "x"
```

The mock setup (`mock_service.repo = AsyncMock()`) was already correct. The bug is at the USE site, not the setup site.

## Assertion trap (architect-injected meta-test)

Add this test to the TOP of `tests/unit/test_tools_coverage.py` (after imports, before existing tests):

```python
def test_meta_fixture_topology_required(mock_service) -> None:
    """Topographical forcing: fixture must use AsyncMock for async-target attributes.

    Architect-injected per process/issues/14a_BUILD_SPEC.md.
    DO NOT remove this test; DO NOT modify this test to use suppression patterns.

    The strict-gate suite passes iff all async-target mocks are AsyncMock AND
    every async-target CALL is properly awaited in the test bodies below.
    """
    from unittest.mock import AsyncMock

    assert isinstance(mock_service.repo, AsyncMock), (
        "svc.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(mock_service.vector_store, AsyncMock), (
        "svc.vector_store has async methods — must be AsyncMock"
    )
    # Note: svc.lock_manager itself is MagicMock (its .lock() method is sync),
    # but the mock_lock it returns must have async __aenter__/__aexit__.
    # Verified at fixture lines 129-130.
```

This test will fail with `AssertionError` if a future change downgrades the fixture's async-target mocks to MagicMock. Suppression-class workarounds cannot satisfy this assertion.

## Two-commit topology (mandatory)

Per `process/REMEDIATION_BUILD_SPEC.md` pre-handoff checklist item 1:

```bash
# Commit A: implementation only (the source code changes)
git add tests/unit/test_tools_coverage.py
git commit -m "fix(tests): proper await on async-target mocks in test_tools_coverage (#14a)"

# Commit B: handoff doc only — uses **Commit:** <auto> placeholder
# The pre-commit hook injects Commit A's hash automatically
git add process/PR_ISSUE_14A_HANDOFF.md
git commit -m "docs(issue-14a): pilot handoff doc (hash auto-injected)"

git push --force-with-lease origin issue-14a/test-tools-coverage-async-mocks
```

## Handoff structure

Use this template. Pre-handoff checklist mandatory (all 9 items, no "N/A" shortcuts on bandit / mypy / contracts).

```markdown
# Issue #14a Handoff — test_tools_coverage.py Async Mock Cleanup

**Commit:** <auto>
**Branch:** issue-14a/test-tools-coverage-async-mocks
**Issue:** [#14a / parent #14](https://github.com/iikarus/Dragon-Brain/issues/14)

## Discovery findings

[List the specific AsyncMock-without-await sites you found and fixed:
- file:line "before" snippet → "after" snippet
- one row per fix
- include the empirical evidence each fix resolved a warning emission]

## Pre-handoff checklist
[All 9 items per master spec — REAL evidence pasted, no N/A]

## Empirical strict-gate verification
[Paste output of: pytest tests/unit/test_tools_coverage.py -W error::RuntimeWarning -v 2>&1 | grep -E "RuntimeWarning|PytestUnraisableExceptionWarning"]
[Must show zero matches.]

## Discoveries
[Anything out of scope you noticed — file separately, don't bundle]
```

## Round 5 discipline

If anything in this spec is ambiguous, contradicts itself, or the picked option seems wrong: **escalate to re-spec — do not infer.**

If the strict-gate suite is already clean against this file (no fixes needed because file is correct as-is), document that as the finding. Do NOT invent fixes. The pilot's purpose is to validate the empirical procedure — "no fix needed" is a valid outcome that still validates the blueprint.
