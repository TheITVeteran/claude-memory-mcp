# Issue #22e-bis — Migrate 2 Contract-Test Files to `make_mock_service()` (Build Spec)

**Issue:** parent #22 — sub-chunk 22e-bis (follow-up to 22e after Codex's additive-discovery investigation surfaced 2 more files carrying the bug class).
**Branch:** `issue-22e-bis/contract-tests-migration` (from current master HEAD, which must contain 22a/22b/22c/22d/22e)
**Pattern:** Topographical Forcing per `22e_BUILD_SPEC.md`. Two files, two distinct migration shapes.

---

## Target

Migrate the 2 remaining files carrying the hand-rolled `MemoryService` construction bug class. After 22e-bis merges, 22f's scanner Pattern 12 can start from **baseline 0** — no allowlist exceptions needed, no ratchet pattern required.

Discovered post-22e via Codex's additive `MemoryService(embedding_service=` grep (the wider check my fixture-name-scoped investigation missed). Of 8 files flagged, 6 are Category D (intentional patterns: real OntologyManager in test_dynamic_validation, mutant-testing factories in test_mutant_dict_*/test_mutant_temporal, integration-ish in test_full_workflow/test_temporal). 2 are Category A (this PR).

**Scope:** 2 files + handoff. Strict.

## Files in scope

- **Modify:** `tests/unit/test_batch3_contracts.py` (replace existing fixture)
- **Modify:** `tests/unit/test_batch5_contracts.py` (extract new fixture, eliminate 10 inline constructions with 20 duplicate-repo typos)
- **New:** `process/PR_ISSUE_22E_BIS_HANDOFF.md` (after the build)

Three-file diff.

## Per-file transformations

### File 1: `tests/unit/test_batch3_contracts.py`

**Single fixture migration.** Pattern matches 22e's File 1 (test_entity_channel).

**Pre-migration fixture (lines 71-95):**

```python
@pytest.fixture
def search_service():
    """Build a MemoryService with mocked infra for search testing."""
    with patch("claude_memory.repository.FalkorDB"):
        from claude_memory.tools import MemoryService

        embedder = MagicMock()
        embedder.encode.return_value = [0.1] * 1024
        vector_store = AsyncMock()
        vector_store.search.return_value = []

        service = MemoryService(embedding_service=embedder, vector_store=vector_store)
        service.repo = AsyncMock()
        service.repo.client = MagicMock()
        service.repo.client.select_graph.return_value = MagicMock()

        # FTS store
        fts_mock = MagicMock()
        fts_mock.search.return_value = []
        service.fts_store = fts_mock

        # Activation engine
        service.activation_engine = MagicMock()                  # ← BUG CLASS (loses helper introspection)

        yield service
```

**Post-migration:**

```python
@pytest.fixture
def search_service():
    """Build a MemoryService with mocked infra for search testing via mock_factory.

    Per process/issues/22e_bis_BUILD_SPEC.md.
    """
    embedder = MagicMock()
    embedder.encode.return_value = [0.1] * 1024
    service = make_mock_service(embedding_service=embedder)

    # Test-default returns on helper-built typed deps
    service.vector_store.search.return_value = []
    service.fts_store.search.return_value = []

    # Tests access service.repo.client.select_graph.return_value — preserve this access pattern
    # by configuring on the helper-built AsyncMock
    service.repo.client = MagicMock()
    service.repo.client.select_graph.return_value = MagicMock()

    yield service
```

Add import at top of file:
```python
from tests._helpers.mock_factory import make_mock_service
```

### File 2: `tests/unit/test_batch5_contracts.py`

**Fixture extraction + 10 inline-construction removal.** Significantly larger surgery than File 1, but mechanical pattern.

**Pre-migration state:**
- No shared `service` fixture exists
- 10 test methods (5 in `TestDeleteRelationshipLocking`, 5 in `TestAddObservationLocking`)
- Each method has inline construction:
  ```python
  with patch("claude_memory.repository.FalkorDB"):
      from claude_memory.tools import MemoryService

      svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
      svc.repo = AsyncMock()
      svc.repo = AsyncMock()      # ← DUPLICATE (20 total typo sites across 10 methods)
      # ... test-specific configuration ...
  ```

**Post-migration:**

Add a module-level fixture (after imports, before the first test class):

```python
from tests._helpers.mock_factory import make_mock_service

# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def service():
    """MemoryService with helper-typed mocks for contract testing.

    Per process/issues/22e_bis_BUILD_SPEC.md. Shared across both test classes
    (TestDeleteRelationshipLocking, TestAddObservationLocking) — both need a
    fresh MemoryService per test (pytest fixture scope=function default).
    """
    return make_mock_service()
```

**Transform each of the 10 test methods.** Pattern (illustrated with `test_evil1_delete_relationship_acquires_lock` at line 22, which currently looks like):

```python
async def test_evil1_delete_relationship_acquires_lock(self) -> None:
    """AUDIT-B5: delete_relationship acquires project lock from edge's project_id."""
    with patch("claude_memory.repository.FalkorDB"):
        from claude_memory.tools import MemoryService

        svc = MemoryService(embedding_service=MagicMock(), vector_store=AsyncMock())
        svc.repo = AsyncMock()
        svc.repo = AsyncMock()
        svc.repo.execute_cypher.return_value = MagicMock(result_set=[["test-project"]])
        svc.repo.delete_edge.return_value = True

        lock_ctx = AsyncMock()
        svc.lock_manager = MagicMock()
        svc.lock_manager.lock.return_value = lock_ctx

        params = RelationshipDeleteParams(relationship_id="test-rel", reason="cleanup")
        result = await svc.delete_relationship(params)

        assert result == {"status": "deleted", "id": "test-rel"}
        svc.lock_manager.lock.assert_called_once_with("test-project")
```

Becomes:

```python
async def test_evil1_delete_relationship_acquires_lock(self, service) -> None:
    """AUDIT-B5: delete_relationship acquires project lock from edge's project_id."""
    service.repo.execute_cypher.return_value = MagicMock(result_set=[["test-project"]])
    service.repo.delete_edge.return_value = True

    # Configure lock context manager on helper-built lock_manager
    # (do NOT replace lock_manager with bare MagicMock — that destroys helper introspection)
    lock_ctx = AsyncMock()
    service.lock_manager.lock.return_value = lock_ctx

    params = RelationshipDeleteParams(relationship_id="test-rel", reason="cleanup")
    result = await service.delete_relationship(params)

    assert result == {"status": "deleted", "id": "test-rel"}
    service.lock_manager.lock.assert_called_once_with("test-project")
```

**Apply this transform to all 10 methods at lines:** 22, 53, 75, 97, 115, 145, 195, 215, 253, 270.

For each method:
1. Add `service` fixture parameter (after `self`)
2. Delete the entire `with patch(...): from claude_memory.tools import MemoryService` block
3. Delete `svc = MemoryService(...)` line
4. Delete BOTH `svc.repo = AsyncMock()` lines (the duplicate typo)
5. Substitute `svc.` → `service.` throughout the method body
6. Replace any `svc.lock_manager = MagicMock()` lines (where present) with deletion — the helper-built lock_manager works, just configure `.lock.return_value` on it

**Critical:** do NOT do `service.lock_manager = MagicMock()` in any test body — same bug-class avoidance as 22e's File 4 transformation.

### Topographical forcing test (BOTH files)

Add to each file's fixtures section (after the fixture, before the first test class):

```python
def test_meta_fixture_topology_required(service) -> None:    # OR (search_service) for File 1
    """Topographical forcing: helper must produce type-correct deps.

    Added 22e-bis to extend forcing-test coverage to the contract-test files.
    DO NOT remove or weaken — guard against migrations that bypass
    make_mock_service() and reintroduce the hand-rolled bug class.

    Per process/issues/22e_bis_BUILD_SPEC.md.
    """
    from unittest.mock import AsyncMock, MagicMock

    assert isinstance(service.repo, AsyncMock), (
        "service.repo targets AsyncMemoryRepository (async) — must be AsyncMock"
    )
    assert isinstance(service.vector_store, AsyncMock), (
        "service.vector_store has async methods — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.spread, AsyncMock), (
        "ActivationEngine.spread is async — must be AsyncMock"
    )
    assert isinstance(service.activation_engine.activate, MagicMock), (
        "ActivationEngine.activate is sync — must be MagicMock"
    )
    assert not isinstance(service.activation_engine.activate, AsyncMock), (
        "Guard against bare AsyncMock — production does NOT await activate"
    )
```

**Adaptation for test_batch3_contracts.py:** the fixture name is `search_service` (not `service`). Substitute the test parameter and `service.` references accordingly.

### Async-method-replacement scan (per file)

Per Transformation discipline from 22d/22e:

```bash
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_batch3_contracts.py
grep -nE 'service\.\w+\.\w+ = (AsyncMock|MagicMock)\(' tests/unit/test_batch5_contracts.py
```

For each match: configure-on-existing-mock or escalate. Document in handoff Discoveries.

## Verification (multi-seed gate per file)

### Pre-PR baseline (Method B with explanatory note acceptable)

These files have NO `_drain_orphan_coroutines` suppression. Master-as-is likely shows clean output (bug class doesn't currently emit warnings because test code paths don't exercise wrong-type mocks in awaited contexts — same situation as 22e's 4 files).

```bash
git worktree add ../22e-bis-pre-pr master
cd ../22e-bis-pre-pr
for file in test_batch3_contracts test_batch5_contracts; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
cd - && git worktree remove --force ../22e-bis-pre-pr
```

Paste all 8 outputs verbatim (2 files × 4 seeds). Method B explanatory note: "Pre-PR baseline shows clean output — these files lack the `_drain_orphan_coroutines` suppression but their hand-rolled fixtures have bug-class patterns (test_batch3's `activation_engine = MagicMock()`, test_batch5's 20 duplicate `svc.repo = AsyncMock()` typos) that don't currently emit warnings because the test code paths don't exercise the bug class in awaited contexts. The migration replaces hand-rolled patterns with helper-introspected correct types AND adds forcing tests that would fail-loud on any regression."

### Post-PR multi-seed gate per file

```bash
git worktree add ../22e-bis-post-pr issue-22e-bis/contract-tests-migration
cd ../22e-bis-post-pr
for file in test_batch3_contracts test_batch5_contracts; do
  echo "######## ${file}.py ########"
  for seed in 1 2 3 4; do
    echo "=== seed=$seed ==="
    python -m pytest tests/unit/${file}.py -W error -p randomly --randomly-seed=$seed 2>&1 | tail -5
  done
done
```

**Required:** all 8 runs return zero RuntimeWarnings and all tests pass.

### Standard gates — SAME clean worktree

```bash
# Still in ../22e-bis-post-pr
python -m pytest tests/unit/test_batch3_contracts.py tests/unit/test_batch5_contracts.py -v --tb=short
python -m pytest tests/_helpers/test_mock_factory.py -v
tox -e contracts
python -m mypy --strict src/claude_memory
python -m ruff check src/claude_memory tests scripts          # CANONICAL — no --exclude
python -m bandit -r src/claude_memory -ll
cd - && git worktree remove ../22e-bis-post-pr
```

## The bar (Codex will verify)

- (a) Both files import `make_mock_service` from `tests._helpers.mock_factory`
- (b) test_batch3: `search_service` fixture uses `make_mock_service(...)`; no hand-rolled `service.activation_engine = MagicMock()` or `service.repo = AsyncMock()` or `with patch("claude_memory.repository.FalkorDB"):` survives in the fixture body
- (c) test_batch5: a module-level `service` fixture exists using `make_mock_service()`; **no inline `MemoryService(embedding_service=` constructions remain anywhere in the file** (grep must return empty); **no `svc.repo = AsyncMock()` lines remain** (grep must return empty — the 20 duplicate-typo sites are all gone)
- (d) test_batch5: all 10 test methods take `service` as a fixture parameter — verify by AST scan; no test method contains `with patch("claude_memory.repository.FalkorDB"):` block
- (e) Both files have `test_meta_fixture_topology_required` asserting helper-correct topology
- (f) **Multi-seed gate (4 seeds × 2 files = 8 runs) returns ZERO RuntimeWarnings** — load-bearing
- (g) All tests in both files pass; test count preserved per file against master baseline (+1 per file for the new forcing test)
- (h) `tox -e contracts`, mypy, CANONICAL ruff (no `--exclude`), bandit all unchanged from master baseline
- (i) Scope discipline: only `process/PR_ISSUE_22E_BIS_HANDOFF.md` + the 2 migrated test files in the diff
- (j) Pre-handoff checklist complete (9 items) with real evidence from a clean worktree; **pre-PR baseline shows all 4 seeds per file × 2 files = 8 seed outputs**; ruff command is canonical full-scope

## Out of scope (do NOT do in this PR)

- Do NOT modify `tests/_helpers/mock_factory.py`
- Do NOT migrate any of the 6 Category D files (test_dynamic_validation, test_full_workflow, test_mutant_dict_crud, test_mutant_dict_services, test_mutant_temporal, test_temporal) — architect investigation confirmed each uses an intentional pattern that helper would break
- Do NOT touch already-migrated files
- Do NOT add scanner Pattern 12 (that's 22f)
- Do NOT modify `tests/unit/conftest.py`, `tests/conftest.py`, `pytest.ini`, or any `src/claude_memory` file
- Do NOT modify any `process/*_SPEC.md` or `process/issues/22*_HARNESS.toml`

Write-guard via `process/issues/22_HARNESS.toml` enforces these physically.

## Round 5 discipline

Same as 22b/22c/22d/22e. If multi-seed gate fails, attribution-diagnose with `pytest --forked`. Fix underlying bug; do NOT add suppression.

**Specific to this PR:** test_batch5's 10-method transformation is mechanical but tedious. If any method's logic doesn't survive the substitution cleanly (e.g., test expects specific `svc.lock_manager` shape that helper-built mock doesn't provide), escalate to architect — do NOT silently re-add the bare-MagicMock lock_manager replacement.

## Hygiene (hardened per 22a-22e R1 pattern)

**Single fresh worktree for ALL evidence commands.** 22f's pre-commit hook will physically enforce this. For 22e-bis, manual discipline: single worktree, every command, canonical ruff, all 8 seed outputs in handoff.

Push with `--force-with-lease` not `--force`.
